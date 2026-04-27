#!/usr/bin/env python3
"""Arbitrate review issues and auto-apply accepted fixes to reviewed_content."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from translate_modelscope import build_client, load_json, load_priority_terms, load_terms, render_termbase, select_terms


def section_number(path: Path) -> str:
    match = re.fullmatch(r"section_(\d+)_(\d+)\.md", path.name)
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)}"


def read_issues(path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not path.exists():
        return issues
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            issues.append(json.loads(line))
    return issues


def read_model_reviews(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    if raw.startswith("["):
        data = json.loads(raw)
        return {str(item.get("section", "")): item for item in data if item.get("section")}
    reviews: dict[str, Any] = {}
    for line in raw.splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("section"):
                reviews[str(item["section"])] = item
    return reviews


def parse_review_content(review_entry: dict[str, Any]) -> dict[str, Any]:
    content = str(review_entry.get("content", "")).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.S)
    if fence:
        content = fence.group(1).strip()
    try:
        return json.loads(content)
    except Exception:
        return {"issues": [], "summary": "Failed to parse review JSON."}


def normalize_issue(issue: dict[str, Any]) -> str:
    text = json.dumps(issue, ensure_ascii=False, sort_keys=True)
    return text


def build_issue_block(issue: dict[str, Any], index: int) -> str:
    lines = [f"- issue_index: {index}"]
    lines.append(f"  priority: {issue.get('priority')}")
    lines.append(f"  type: {issue.get('type')}")
    lines.append(f"  message: {issue.get('message')}")
    if issue.get("suggestion"):
        lines.append(f"  suggestion: {issue.get('suggestion')}")
    if issue.get("source_excerpt"):
        lines.append(f"  source_excerpt: {issue.get('source_excerpt')}")
    if issue.get("translation_excerpt"):
        lines.append(f"  translation_excerpt: {issue.get('translation_excerpt')}")
    return "\n".join(lines)


def review_issue_excerpt(review_data: dict[str, Any], issue: dict[str, Any]) -> str:
    matches: list[dict[str, Any]] = []
    source_excerpt = issue.get("source_excerpt", "")
    translation_excerpt = issue.get("translation_excerpt", "")
    for item in review_data.get("issues", []):
        if source_excerpt and source_excerpt[:40] in str(item.get("source_excerpt", "")):
            matches.append(item)
        elif translation_excerpt and translation_excerpt[:40] in str(item.get("translation_excerpt", "")):
            matches.append(item)
        elif issue.get("message") and issue["message"][:30] in str(item.get("reason", "")):
            matches.append(item)
    if not matches:
        return "- none"
    lines: list[str] = []
    for item in matches[:3]:
        lines.append(
            f"- [{item.get('priority')}] {item.get('type')}: reason={item.get('reason')} suggestion={item.get('suggestion')}"
        )
    return "\n".join(lines)


def build_client_for_arbiter(config: dict[str, Any]):
    client_cfg = {
        "base_url": config["base_url"],
        "api_key_env": config["api_key_env"],
        "model": config["arbiter"]["model"],
        "timeout_seconds": config.get("timeout_seconds", 600),
    }
    return build_client(client_cfg)


def run_arbiter_prompt(
    config: dict[str, Any],
    chapter: int,
    section: str,
    source: str,
    translated: str,
    issue: dict[str, Any],
    review_data: dict[str, Any],
    termbase_block: str,
) -> dict[str, Any]:
    client = build_client_for_arbiter(config)
    system_prompt = Path(config["arbiter"]["system_prompt_file"]).read_text(encoding="utf-8")
    user_template = Path(config["arbiter"]["user_prompt_template_file"]).read_text(encoding="utf-8")
    user_prompt = (
        user_template.replace("{chapter}", str(chapter))
        .replace("{section}", section)
        .replace("{termbase_block}", termbase_block)
        .replace("{source_fragment}", source)
        .replace("{translated_fragment}", translated)
        .replace("{issue_block}", build_issue_block(issue, 1))
        .replace("{model_review_block}", review_issue_excerpt(review_data, issue))
    )
    response = client.chat.completions.create(
        model=config["arbiter"]["model"],
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        stream=False,
        temperature=0.0,
        extra_body={"enable_thinking": True, "thinking_budget": int(config["arbiter"].get("thinking_budget", 4096))},
    )
    text = response.choices[0].message.content or "{}"
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def apply_replacement(text: str, issue: dict[str, Any], replacement: str) -> str:
    old = issue.get("translation_excerpt", "")
    if old and old in text:
        return text.replace(old, replacement, 1)
    suggestion = issue.get("suggestion", "")
    if suggestion and suggestion in text:
        return text.replace(suggestion, replacement, 1)
    return text


def is_actionable_replacement(replacement: str) -> bool:
    stripped = replacement.strip()
    if not stripped:
        return False
    if stripped in {"无需修改", "无", "none", "None"}:
        return False
    # Reject explanatory sentences that are not literal replacements.
    noisy_markers = ["例如：", "建议改为", "建议：", "说明："]
    if any(marker in stripped for marker in noisy_markers):
        return False
    return True


def render_arbiter_md(chapter: int, decisions: list[dict[str, Any]]) -> str:
    lines = [f"# Chapter {chapter} Arbiter Summary", ""]
    counts = {"accept": 0, "reject": 0, "defer": 0}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    for key in ["accept", "reject", "defer"]:
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines.extend(["", "## Decisions", ""])
    for d in decisions:
        lines.append(f"- [{d['decision']}] {d['section']} {d['message']}")
        lines.append(f"  理由：{d['reason']}")
        if d.get("replacement"):
            lines.append(f"  替换：{d['replacement']}")
    return "\n".join(lines) + "\n"


def update_applied_fixes(path: Path, lines_to_add: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Applied Fixes\n\n"
    if "## Arbiter Applied" not in existing:
        existing += "\n## Arbiter Applied\n\n"
    existing += "\n".join(lines_to_add) + "\n"
    path.write_text(existing, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Arbitrate review issues and auto-apply accepted fixes.")
    parser.add_argument("--config", default="configs/modelscope.example.json")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_json(Path(args.config))
    chapter = args.chapter
    source_dir = Path(config["translation"]["source_directory"]) / f"chapter_{chapter}"
    translated_dir = Path(config["translation"]["output_directory"]) / f"chapter_{chapter}"
    reviewed_dir = Path(config["review"]["reviewed_output_directory"]) / f"chapter_{chapter}"
    report_dir = Path(config["review"]["output_directory"]) / f"chapter_{chapter}"
    report_dir.mkdir(parents=True, exist_ok=True)
    arbiter_jsonl = report_dir / "arbiter.jsonl"
    arbiter_md = report_dir / "arbiter.md"
    applied_fixes = report_dir / "applied_fixes.md"

    if args.force and arbiter_jsonl.exists():
        arbiter_jsonl.unlink()

    all_terms = load_terms(Path(config["translation"]["termbase_csv"]))
    priority_terms = load_priority_terms(Path(config["translation"]["termbase_json"]))
    issues = read_issues(report_dir / "issues.jsonl")
    model_reviews = {k: parse_review_content(v) for k, v in read_model_reviews(report_dir / "model_review.jsonl").items()}
    existing_sections: set[str] = set()
    if arbiter_jsonl.exists() and not args.force:
        for line in arbiter_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_sections.add(json.loads(line).get("section", ""))

    decisions: list[dict[str, Any]] = []
    applied_lines: list[str] = []

    for issue in issues:
        section = str(issue["section"])
        if section in existing_sections and args.resume:
            continue
        src = source_dir / f"section_{section.replace('.', '_')}.md"
        tgt = translated_dir / src.name
        rev = reviewed_dir / src.name
        if not (src.exists() and tgt.exists() and rev.exists()):
            continue
        source = src.read_text(encoding="utf-8")
        translated = tgt.read_text(encoding="utf-8")
        reviewed = rev.read_text(encoding="utf-8")
        terms = select_terms(source + "\n" + translated, all_terms, priority_terms, 80)
        result = run_arbiter_prompt(
            config,
            chapter,
            section,
            source,
            translated,
            issue,
            model_reviews.get(section, {}),
            render_termbase(terms),
        )
        decision = {
            "chapter": chapter,
            "section": section,
            "issue": issue,
            "decision": result["decisions"][0]["decision"],
            "reason": result["decisions"][0]["reason"],
            "replacement": result["decisions"][0].get("replacement", ""),
            "message": issue["message"],
        }
        with arbiter_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(decision, ensure_ascii=False) + "\n")
        decisions.append(decision)
        if decision["decision"] == "accept" and is_actionable_replacement(decision["replacement"]):
            new_text = apply_replacement(reviewed, issue, decision["replacement"])
            rev.write_text(new_text, encoding="utf-8")
            applied_lines.append(
                f"- `{src.name}` line {issue['line']}: {issue['message']} -> {decision['replacement']}"
            )
        existing_sections.add(section)

    arbiter_md.write_text(render_arbiter_md(chapter, decisions), encoding="utf-8")
    if applied_lines:
        update_applied_fixes(applied_fixes, applied_lines)
    print(f"chapter {chapter}: arbiter decisions {len(decisions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
