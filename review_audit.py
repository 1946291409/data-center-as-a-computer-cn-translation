#!/usr/bin/env python3
"""Second-phase audit and targeted ModelScope review for translated Markdown."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from translate_modelscope import (
    build_client,
    load_json,
    load_priority_terms,
    load_terms,
    render_termbase,
    select_terms,
    validate_translation,
)


DEFAULT_CONFIG = "configs/modelscope.example.json"


@dataclass
class Issue:
    priority: str
    type: str
    chapter: int
    section: str
    file: str
    line: int
    message: str
    suggestion: str = ""
    source_file: str = ""
    source_line: int = 1
    source_excerpt: str = ""
    translation_excerpt: str = ""


def issue_dict(issue: Issue) -> dict[str, Any]:
    return {
        "priority": issue.priority,
        "type": issue.type,
        "chapter": issue.chapter,
        "section": issue.section,
        "file": issue.file,
        "line": issue.line,
        "message": issue.message,
        "suggestion": issue.suggestion,
        "source_file": issue.source_file,
        "source_line": issue.source_line,
        "source_excerpt": issue.source_excerpt,
        "translation_excerpt": issue.translation_excerpt,
    }


def existing_model_review_sections(path: Path) -> set[str]:
    sections: set[str] = set()
    if not path.exists():
        return sections
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        section = str(item.get("section", "")).strip()
        if section:
            sections.add(section)
    return sections


def chapter_dirs(root: Path, chapter: int | None) -> list[Path]:
    if chapter is not None:
        return [root / f"chapter_{chapter}"]
    return sorted(root.glob("chapter_*"), key=lambda p: int(p.name.split("_")[1]))


def section_number(path: Path) -> str:
    match = re.fullmatch(r"section_(\d+)_(\d+)\.md", path.name)
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)}"


def line_no(text: str, needle: str) -> int:
    idx = text.find(needle)
    if idx < 0:
        return 1
    return text[:idx].count("\n") + 1


def blocks_with_lines(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    start_line = 1
    for line_no_, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "":
            if current:
                blocks.append((start_line, "\n".join(current).strip()))
                current = []
            start_line = line_no_ + 1
            continue
        if not current:
            start_line = line_no_
        current.append(line)
    if current:
        blocks.append((start_line, "\n".join(current).strip()))
    return blocks


def excerpt(text: str, max_len: int = 260) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def block_containing(blocks: list[tuple[int, str]], needle: str) -> tuple[int, str]:
    for line, block in blocks:
        if needle in block:
            return line, block
    return (blocks[0] if blocks else (1, ""))


def aligned_target_block(
    source_blocks: list[tuple[int, str]],
    target_blocks: list[tuple[int, str]],
    source_line: int,
) -> tuple[int, str]:
    source_idx = 0
    for idx, (line, _) in enumerate(source_blocks):
        if line <= source_line:
            source_idx = idx
        else:
            break
    if not target_blocks:
        return 1, ""
    return target_blocks[min(source_idx, len(target_blocks) - 1)]


def audit_pair(chapter: int, src: Path, tgt: Path, config: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    section = section_number(src)
    source = src.read_text(encoding="utf-8")
    translated = tgt.read_text(encoding="utf-8") if tgt.exists() else ""
    source_blocks = blocks_with_lines(source)
    target_blocks = blocks_with_lines(translated)

    if not tgt.exists():
        return [
            Issue(
                "P0",
                "missing_translation",
                chapter,
                section,
                str(tgt),
                1,
                "Translated section file is missing",
                source_file=str(src),
            )
        ]

    for error in validate_translation(source, translated):
        issues.append(
            Issue(
                "P0",
                "structure",
                chapter,
                section,
                str(tgt),
                1,
                error,
                source_file=str(src),
                source_excerpt=excerpt(source_blocks[0][1] if source_blocks else ""),
                translation_excerpt=excerpt(target_blocks[0][1] if target_blocks else ""),
            )
        )

    source_numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", source)
    target_numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", translated)
    ignored_numbers = {str(chapter), section.split(".")[0], section.split(".")[-1]}
    for number in sorted(set(source_numbers) - set(target_numbers)):
        if len(number) > 0 and number not in ignored_numbers:
            src_line, src_block = block_containing(source_blocks, number)
            tgt_line, tgt_block = aligned_target_block(source_blocks, target_blocks, src_line)
            issues.append(
                Issue(
                    "P1",
                    "number",
                    chapter,
                    section,
                    str(tgt),
                    tgt_line,
                    f"Number appears in source but not translated text: {number}",
                    "Check whether this number was mistranslated, omitted, or reformatted.",
                    source_file=str(src),
                    source_line=src_line,
                    source_excerpt=excerpt(src_block),
                    translation_excerpt=excerpt(tgt_block),
                )
            )

    for pattern, message in [
        (r"^\s*Fig\. ", "Visible figure caption should use Chinese 图 prefix."),
        (r"\]\(\.\./\.\./images/", "Translated image path should point to ../../build/images/."),
        (r"iig\.", "Likely corrupted Fig. prefix."),
        (r"fig\d+_\d+", "Likely hallucinated or raw figure filename in prose."),
        (r"^\s*\d+\.\s+\d+\.", "Duplicated ordered-list number."),
    ]:
        for match in re.finditer(pattern, translated, flags=re.MULTILINE | re.IGNORECASE):
            tgt_line = line_no(translated, match.group(0))
            _, tgt_block = block_containing(target_blocks, match.group(0).strip())
            if "Duplicated ordered-list" in message:
                source_list_match = re.search(r"^\s*\d+\.\s+\d+\.", source, flags=re.MULTILINE)
                if source_list_match:
                    src_line, src_block = block_containing(source_blocks, source_list_match.group(0).strip())
                else:
                    src_line, src_block = aligned_target_block(target_blocks, source_blocks, tgt_line)
            else:
                src_line, src_block = aligned_target_block(target_blocks, source_blocks, tgt_line)
            issues.append(
                Issue(
                    "P1",
                    "format",
                    chapter,
                    section,
                    str(tgt),
                    tgt_line,
                    message,
                    source_file=str(src),
                    source_line=src_line,
                    source_excerpt=excerpt(src_block),
                    translation_excerpt=excerpt(tgt_block),
                )
            )

    for line in translated.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "-", "*", "!", "|", ">", "```")):
            continue
        if re.match(r"^\d+\.\s+", stripped):
            continue
        if re.match(r"^(?:图|Fig\.)\s*\d+\.\d+", stripped):
            continue
        if re.search(r"[\u4e00-\u9fff]", stripped) and not line.startswith("　　"):
            tgt_line = line_no(translated, line)
            _, src_block = aligned_target_block(target_blocks, source_blocks, tgt_line)
            issues.append(
                Issue(
                    "P2",
                    "indent",
                    chapter,
                    section,
                    str(tgt),
                    tgt_line,
                    "Chinese prose line is missing two full-width spaces.",
                    source_file=str(src),
                    source_excerpt=excerpt(src_block),
                    translation_excerpt=excerpt(line),
                )
            )
            break

    return issues


def mechanical_fix(text: str) -> str:
    lines: list[str] = []
    for line in text.lstrip("\ufeff").splitlines():
        line = line.replace("](../../images/", "](../../build/images/")
        line = re.sub(r"^Fig\. (\d+\.)", r"图\1", line)
        line = re.sub(r"^(\s*)(\d+\.)\s+\2\s*", r"\1\2 ", line)
        line = line.replace("Why we picked this paper：", "我们选择这篇论文的原因：")
        line = line.replace("Why we picked this paper:", "我们选择这篇论文的原因：")
        stripped = line.strip()
        if re.match(r"^\s*\d+\.\s+", line):
            lines.append(line)
            continue
        if (
            stripped
            and not stripped.startswith(("　　", "#", "-", "*", "!", "|", ">", "```"))
            and not re.match(r"^(?:图|Fig\.)\s*\d+\.\d+", stripped)
            and re.search(r"[\u4e00-\u9fff]", stripped)
        ):
            line = "　　" + stripped
        lines.append(line)
    result = "\n".join(lines).rstrip() + "\n"
    result = re.sub(r"(\[\d+\])(?=\S)", r"\1\n\n　　", result)
    return result


def write_reviewed_copy(chapter: int, translated_dir: Path, reviewed_dir: Path) -> list[str]:
    src_dir = translated_dir / f"chapter_{chapter}"
    dst_dir = reviewed_dir / f"chapter_{chapter}"
    dst_dir.mkdir(parents=True, exist_ok=True)
    changes: list[str] = []
    for src in sorted(src_dir.glob("section_*.md")):
        original = src.read_text(encoding="utf-8")
        fixed = mechanical_fix(original)
        (dst_dir / src.name).write_text(fixed, encoding="utf-8")
        if fixed != original:
            diff = list(
                difflib.unified_diff(
                    original.splitlines(),
                    fixed.splitlines(),
                    fromfile=str(src),
                    tofile=str(dst_dir / src.name),
                    lineterm="",
                )
            )
            changes.append(f"## {src.name}\n\n```diff\n" + "\n".join(diff[:120]) + "\n```\n")
    return changes


def is_high_risk(source: str, translated: str, keywords: list[str]) -> bool:
    lower = (source + "\n" + translated).lower()
    if re.search(r"\d+(?:\.\d+)?%|\$.*?\$|\[\d+", source):
        return True
    return any(keyword.lower() in lower for keyword in keywords)


def model_review_section(
    config: dict[str, Any],
    chapter: int,
    section: str,
    source: str,
    translated: str,
    termbase_block: str,
) -> dict[str, Any]:
    client = build_client({**config, "model": config["review"]["model"]})
    system_prompt = Path(config["review"]["system_prompt_file"]).read_text(encoding="utf-8")
    user_template = Path(config["review"]["user_prompt_template_file"]).read_text(encoding="utf-8")
    user_prompt = (
        user_template.replace("{termbase_block}", termbase_block)
        .replace("{source_fragment}", source)
        .replace("{translated_fragment}", translated)
        .replace("{chapter}", str(chapter))
        .replace("{section}", section)
    )
    response = client.chat.completions.create(
        model=config["review"]["model"],
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        stream=False,
        temperature=0.1,
        extra_body={"enable_thinking": True, "thinking_budget": int(config["review"].get("thinking_budget", 4096))},
    )
    content = response.choices[0].message.content or ""
    return {"chapter": chapter, "section": section, "model": config["review"]["model"], "content": content}


def render_audit_md(chapter: int, issues: list[Issue], model_reviews: int) -> str:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.priority] = counts.get(issue.priority, 0) + 1
    lines = [f"# Chapter {chapter} Review Audit", ""]
    lines.append(f"- Issues: {len(issues)}")
    lines.append(f"- Model review entries: {model_reviews}")
    lines.append("- `reviewed_content` is a mechanically normalized copy, not a human-approved final revision.")
    for priority in ["P0", "P1", "P2", "P3"]:
        lines.append(f"- {priority}: {counts.get(priority, 0)}")
    lines.extend(["", "## Issues", ""])
    if not issues:
        lines.append("- None")
    for issue in issues:
        lines.append(
            f"- [{issue.priority}] {issue.type} `{issue.file}:{issue.line}`: {issue.message}"
        )
        if issue.source_file:
            lines.append(f"  Source: `{issue.source_file}:{issue.source_line}`")
        if issue.source_excerpt:
            lines.append(f"  原文：{issue.source_excerpt}")
        if issue.translation_excerpt:
            lines.append(f"  译文：{issue.translation_excerpt}")
        if issue.suggestion:
            lines.append(f"  建议：{issue.suggestion}")
    return "\n".join(lines) + "\n"


def run_audit(args: argparse.Namespace) -> int:
    config = load_json(Path(args.config))
    source_root = Path(config["translation"]["source_directory"])
    translated_root = Path(config["translation"]["output_directory"])
    report_root = Path(config["review"]["output_directory"])
    reviewed_root = Path(config["review"]["reviewed_output_directory"])
    all_terms = load_terms(Path(config["translation"]["termbase_csv"]))
    priority_terms = load_priority_terms(Path(config["translation"]["termbase_json"]))

    for chapter_dir in chapter_dirs(source_root, args.chapter):
        if not chapter_dir.exists():
            continue
        chapter = int(chapter_dir.name.split("_")[1])
        chapter_report = report_root / f"chapter_{chapter}"
        chapter_report.mkdir(parents=True, exist_ok=True)
        issues: list[Issue] = []
        model_reviews = 0
        model_review_path = chapter_report / "model_review.jsonl"
        if args.model_review and model_review_path.exists() and args.force:
            model_review_path.unlink()
        reviewed_sections = existing_model_review_sections(model_review_path)

        for src in sorted(chapter_dir.glob("section_*.md"), key=lambda p: section_number(p)):
            tgt = translated_root / f"chapter_{chapter}" / src.name
            issues.extend(audit_pair(chapter, src, tgt, config))
            if args.model_review and tgt.exists():
                sec_no = section_number(src)
                if sec_no in reviewed_sections:
                    model_reviews += 1
                    continue
                source = src.read_text(encoding="utf-8")
                translated = tgt.read_text(encoding="utf-8")
                if is_high_risk(source, translated, config["review"].get("high_risk_keywords", [])):
                    terms = select_terms(source + "\n" + translated, all_terms, priority_terms, 80)
                    review = model_review_section(
                        config, chapter, sec_no, source, translated, render_termbase(terms)
                    )
                    with model_review_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(review, ensure_ascii=False) + "\n")
                    model_reviews += 1
                    reviewed_sections.add(sec_no)

        changes = write_reviewed_copy(chapter, translated_root, reviewed_root)
        with (chapter_report / "issues.jsonl").open("w", encoding="utf-8") as fh:
            for issue in issues:
                fh.write(json.dumps(issue_dict(issue), ensure_ascii=False) + "\n")
        (chapter_report / "audit.md").write_text(render_audit_md(chapter, issues, model_reviews), encoding="utf-8")
        (chapter_report / "changes.md").write_text(
            "# Mechanical Changes\n\n"
            + (
                "\n".join(changes)
                if changes
                else "No mechanical changes were applied to reviewed_content.\n"
            ),
            encoding="utf-8",
        )
        print(f"chapter {chapter}: {len(issues)} issues, reviewed copy written")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit translated Markdown and prepare reviewed copies.")
    parser.add_argument("--config", default="configs/modelscope.example.json")
    parser.add_argument("--chapter", type=int)
    parser.add_argument("--model-review", action="store_true", help="Call review_model for high-risk sections")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    return run_audit(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
