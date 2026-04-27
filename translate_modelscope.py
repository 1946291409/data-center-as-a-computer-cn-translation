#!/usr/bin/env python3
"""Translate cleaned Markdown sections through ModelScope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from openai import APIConnectionError, OpenAI
except ImportError:
    APIConnectionError = Exception  # type: ignore
    OpenAI = None  # type: ignore


DEFAULT_CONFIG = "configs/modelscope.example.json"
STATE_ROOT = Path("translation_state") / "modelscope"


@dataclass
class Term:
    source: str
    target: str
    category: str = ""
    status: str = "draft"
    first_use: str = ""
    notes: str = ""


@dataclass
class Chunk:
    chapter: int
    section: str
    index: int
    total_in_section: int
    source_path: Path
    output_path: Path
    part_path: Path
    state_key: str
    text: str
    source_hash: str
    char_count: int
    estimated_tokens: int
    termbase: list[Term] = field(default_factory=list)


@dataclass
class ErrorInfo:
    status: str
    message: str
    retry_after: float | None = None
    headers: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def section_to_filename(section: str) -> str:
    return f"section_{section.replace('.', '_')}.md"


def parse_section_from_filename(path: Path) -> str:
    match = re.fullmatch(r"section_(\d+)_(\d+)\.md", path.name)
    if not match:
        raise ValueError(f"Cannot parse section number from {path}")
    return f"{match.group(1)}.{match.group(2)}"


def discover_source_sections(config: dict[str, Any], chapter: int, section: str | None = None) -> list[Path]:
    source_root = Path(config["translation"]["source_directory"]) / f"chapter_{chapter}"
    if section:
        path = source_root / section_to_filename(section)
        if not path.exists():
            raise FileNotFoundError(f"Source section not found: {path}")
        return [path]
    paths = sorted(source_root.glob(f"section_{chapter}_*.md"), key=lambda p: parse_section_from_filename(p))
    if not paths:
        raise FileNotFoundError(f"No section files found under {source_root}")
    return paths


def split_markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line == "":
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def is_image_block(block: str) -> bool:
    return block.startswith("![") and "](" in block


def merge_image_captions(blocks: list[str]) -> list[str]:
    merged: list[str] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if is_image_block(block) and i + 1 < len(blocks) and re.match(r"^(Fig\.|图)\s+\d+\.", blocks[i + 1]):
            merged.append(block + "\n\n" + blocks[i + 1])
            i += 2
        else:
            merged.append(block)
            i += 1
    return merged


def chunk_section(source_path: Path, chapter: int, max_chars: int, output_root: Path) -> list[Chunk]:
    section = parse_section_from_filename(source_path)
    blocks = merge_image_captions(split_markdown_blocks(source_path.read_text(encoding="utf-8")))
    grouped: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in blocks:
        block_len = len(block)
        if current and current_len + block_len + 2 > max_chars:
            grouped.append("\n\n".join(current))
            current = [block]
            current_len = block_len
        else:
            current.append(block)
            current_len += block_len + (2 if current_len else 0)
    if current:
        grouped.append("\n\n".join(current))

    chunks_dir = output_root / f"chapter_{chapter}" / ".chunks" / section.replace(".", "_")
    chunks: list[Chunk] = []
    for idx, chunk_text in enumerate(grouped, start=1):
        output_path = chunks_dir / f"chunk_{idx:03d}.md"
        chunks.append(
            Chunk(
                chapter=chapter,
                section=section,
                index=idx,
                total_in_section=len(grouped),
                source_path=source_path,
                output_path=output_path,
                part_path=output_path.with_suffix(".md.part"),
                state_key=f"{section}:{idx:03d}",
                text=chunk_text,
                source_hash=sha256_text(chunk_text),
                char_count=len(chunk_text),
                estimated_tokens=estimate_tokens(chunk_text),
            )
        )
    return chunks


def load_terms(csv_path: Path) -> list[Term]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = csv.DictReader(fh)
        return [
            Term(
                source=(row.get("source") or "").strip(),
                target=(row.get("target") or "").strip(),
                category=(row.get("category") or "").strip(),
                status=(row.get("status") or "").strip() or "draft",
                first_use=(row.get("first_use") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
            for row in rows
            if (row.get("source") or "").strip() and (row.get("target") or "").strip()
        ]


def load_priority_terms(json_path: Path) -> list[Term]:
    data = load_json(json_path)
    terms: list[Term] = []
    for row in data.get("priority_terms", []):
        terms.append(
            Term(
                source=str(row.get("source", "")).strip(),
                target=str(row.get("target", "")).strip(),
                category="priority",
                status="priority",
                notes=str(row.get("note", "")).strip(),
            )
        )
    return [term for term in terms if term.source and term.target]


def term_matches(text_lower: str, source: str) -> bool:
    source_lower = source.lower()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+.-]*", source):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(source_lower)}(?![A-Za-z0-9])", text_lower) is not None
    return source_lower in text_lower


def select_terms(
    chunk_text: str,
    all_terms: list[Term],
    priority_terms: list[Term],
    max_entries: int,
) -> list[Term]:
    selected: dict[str, Term] = {term.source.lower(): term for term in priority_terms}
    text_lower = chunk_text.lower()
    matches = [term for term in all_terms if term_matches(text_lower, term.source)]
    matches.sort(key=lambda t: (0 if t.status == "approved" else 1, -len(t.source), t.source.lower()))
    for term in matches:
        key = term.source.lower()
        if key not in selected or selected[key].status != "approved":
            selected[key] = term
        if len(selected) >= max_entries:
            break
    return list(selected.values())[:max_entries]


def render_termbase(terms: list[Term]) -> str:
    lines = ["| source | target | notes |", "|---|---|---|"]
    for term in terms:
        lines.append(f"| {term.source} | {term.target} | {term.notes.replace('|', '/')} |")
    return "\n".join(lines)


def render_user_prompt(template: str, termbase_block: str, markdown_fragment: str) -> str:
    return template.replace("{termbase_block}", termbase_block).replace("{markdown_fragment}", markdown_fragment)


def build_chunks(
    config: dict[str, Any],
    chapter: int,
    section: str | None,
    all_terms: list[Term],
    priority_terms: list[Term],
) -> list[Chunk]:
    output_root = Path(config["translation"]["output_directory"])
    max_chars = int(config["translation"]["max_input_chars_per_request"])
    max_terms = int(config["translation"].get("max_termbase_entries_per_request", 80))
    chunks: list[Chunk] = []
    for source_path in discover_source_sections(config, chapter, section):
        for chunk in chunk_section(source_path, chapter, max_chars, output_root):
            chunk.termbase = select_terms(chunk.text, all_terms, priority_terms, max_terms)
            chunks.append(chunk)
    return chunks


def state_dir(chapter: int) -> Path:
    return STATE_ROOT / f"chapter_{chapter}"


def state_paths(chapter: int) -> dict[str, Path]:
    base = state_dir(chapter)
    return {
        "dir": base,
        "state": base / "state.json",
        "chunks": base / "chunks.jsonl",
        "usage": base / "raw_usage.jsonl",
    }


def load_chunk_records(chapter: int) -> dict[str, dict[str, Any]]:
    path = state_paths(chapter)["chunks"]
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                records[row["state_key"]] = row
    return records


def chunk_done(chunk: Chunk, records: dict[str, dict[str, Any]]) -> bool:
    record = records.get(chunk.state_key)
    return (
        bool(record)
        and record.get("status") == "done"
        and record.get("source_hash") == chunk.source_hash
        and chunk.output_path.exists()
    )


def chunk_record(chunk: Chunk, status: str, **extra: Any) -> dict[str, Any]:
    data = {
        "state_key": chunk.state_key,
        "chapter": chunk.chapter,
        "section": chunk.section,
        "chunk_index": chunk.index,
        "total_in_section": chunk.total_in_section,
        "source_path": str(chunk.source_path),
        "output_path": str(chunk.output_path),
        "source_hash": chunk.source_hash,
        "char_count": chunk.char_count,
        "estimated_tokens": chunk.estimated_tokens,
        "termbase_entries": len(chunk.termbase),
        "status": status,
        "updated_at": now_iso(),
    }
    data.update(extra)
    return data


def write_state(
    chapter: int,
    status: str,
    chunks: list[Chunk],
    records: dict[str, dict[str, Any]],
    last_error: dict[str, Any] | None = None,
) -> None:
    done = sum(1 for chunk in chunks if chunk_done(chunk, records))
    failed = sum(1 for rec in records.values() if rec.get("status") in {"failed", "quota_exhausted", "auth_error", "bad_request"})
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for rec in records.values():
        usage = rec.get("usage") or {}
        for key in usage_totals:
            usage_totals[key] += int(usage.get(key) or 0)
    sections = sorted({chunk.section for chunk in chunks})
    if len(sections) == 1:
        suggestion = f"python translate_modelscope.py --section {sections[0]} --resume"
    else:
        suggestion = f"python translate_modelscope.py --chapter {chapter} --resume"
    data = {
        "chapter": chapter,
        "status": status,
        "updated_at": now_iso(),
        "total_chunks": len(chunks),
        "done_chunks": done,
        "pending_chunks": max(0, len(chunks) - done),
        "failed_records": failed,
        "usage": usage_totals,
        "last_error": last_error,
        "suggested_resume_command": suggestion,
    }
    write_json(state_paths(chapter)["state"], data)


def extract_headers(exc: BaseException) -> dict[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return {}
    wanted: dict[str, str] = {}
    for key, value in dict(headers).items():
        lower = key.lower()
        if (
            lower == "retry-after"
            or lower.startswith("x-ratelimit")
            or lower.startswith("x-request")
            or lower.startswith("x-modelscope")
            or lower.startswith("x-dashscope")
            or lower.startswith("x-acs")
        ):
            wanted[lower] = str(value)
    return wanted


def error_body(exc: BaseException) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    if response is None:
        return {}
    try:
        return response.json()
    except Exception:
        return {"text": getattr(response, "text", "")}


def classify_exception(exc: BaseException) -> ErrorInfo:
    headers = extract_headers(exc)
    body = error_body(exc)
    message = json.dumps(body, ensure_ascii=False) if body else str(exc)
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    retry_after = None
    if "retry-after" in headers:
        try:
            retry_after = float(headers["retry-after"])
        except ValueError:
            retry_after = None
    lower = message.lower()
    if status_code == 401:
        return ErrorInfo("auth_error", message, headers=headers, raw=body)
    if status_code == 400:
        return ErrorInfo("bad_request", message, headers=headers, raw=body)
    if status_code == 429:
        quota_words = ["quota", "current quota", "billing", "insufficient", "余额", "额度", "欠费"]
        if any(word in lower for word in quota_words):
            return ErrorInfo("quota_exhausted", message, retry_after, headers, body)
        return ErrorInfo("rate_limited", message, retry_after, headers, body)
    if status_code in {500, 503}:
        return ErrorInfo("server_retryable", message, retry_after, headers, body)
    if isinstance(exc, APIConnectionError):
        return ErrorInfo("network_retryable", message, headers=headers, raw=body)
    return ErrorInfo("failed", message, headers=headers, raw=body)


def backoff_seconds(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return max(0.0, retry_after)
    return min(120.0, (2 ** max(0, attempt - 1)) + random.random())


def validate_translation(source: str, translated: str) -> list[str]:
    errors: list[str] = []
    source = source.lstrip("\ufeff")
    translated = translated.lstrip("\ufeff")
    source_heading_nums = re.findall(r"^#{1,6}\s+(\d+(?:\.\d+)*)\b", source, flags=re.MULTILINE)
    target_heading_nums = re.findall(r"^#{1,6}\s+(\d+(?:\.\d+)*)\b", translated, flags=re.MULTILINE)
    if source_heading_nums != target_heading_nums:
        errors.append(f"heading numbers mismatch: {source_heading_nums} != {target_heading_nums}")

    source_citations = re.findall(r"\[\d+(?:,\s*\d+)*\]", source)
    target_citations = re.findall(r"\[\d+(?:,\s*\d+)*\]", translated)
    if source_citations != target_citations:
        errors.append("citation markers mismatch")

    source_paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", source)
    target_paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", translated)
    expected_target_paths = [translated_image_path(path) for path in source_paths]
    if expected_target_paths != target_paths:
        errors.append("image paths mismatch")

    source_fig_captions = len(re.findall(r"^Fig\.\s+\d+\.\d+\s+", source, flags=re.MULTILINE))
    target_fig_captions = len(re.findall(r"^(?:Fig\.|图)\s*\d+\.\d+\s+", translated, flags=re.MULTILINE))
    if source_fig_captions != target_fig_captions:
        errors.append(f"visible figure caption count mismatch: {source_fig_captions} != {target_fig_captions}")

    # Repeated prose references can cross chunk boundaries. Enforce figure
    # numbers only when the chunk carries the image/caption itself.
    source_fig_numbers = sorted(set(re.findall(r"^Fig\.\s+(\d+\.\d+)\s+", source, flags=re.MULTILINE)))
    for number in source_fig_numbers:
        if not re.search(rf"(?:图\s*|Fig\.\s*){re.escape(number)}\b", translated):
            errors.append(f"figure number missing or corrupted: {number}")

    stripped = translated.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        errors.append("whole output is wrapped in a fenced code block")

    for line_no, line in enumerate(translated.splitlines(), start=1):
        if not line.strip():
            continue
        if line.startswith(("#", "-", "*", "!", "|", ">", "```")):
            continue
        if re.match(r"^\d+\.\s+", line):
            continue
        if re.match(r"^(?:Fig\.|图)\s*\d+\.\d+\s+", line):
            continue
        if re.match(r"^\s*\$.*\$\s*$", line):
            continue
        if re.search(r"[\u4e00-\u9fff]", line) and not line.startswith("　　"):
            errors.append(f"Chinese prose line missing full-width indent at line {line_no}")
            break
    return errors


def normalize_translation_markdown(text: str) -> str:
    """Apply mechanical formatting rules that do not change translation text."""
    text = text.lstrip("\ufeff")
    normalized: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            normalized.append("")
            continue
        if stripped.startswith("　　"):
            normalized.append(stripped)
            continue
        if stripped.startswith(("#", "-", "*", "!", "|", ">", "```")):
            normalized.append(stripped)
            continue
        if re.match(r"^\d+\.\s+", stripped):
            normalized.append(stripped)
            continue
        if re.match(r"^(?:Fig\.|图)\s*\d+\.\d+\s+", stripped):
            normalized.append(stripped)
            continue
        if re.match(r"^\s*\$.*\$\s*$", stripped):
            normalized.append(stripped)
            continue
        if re.search(r"[\u4e00-\u9fff]", stripped):
            normalized.append("　　" + stripped)
        else:
            normalized.append(stripped)
    result = "\n".join(normalized).rstrip() + "\n"
    return rewrite_image_paths_for_translation(result)


def translated_image_path(path: str) -> str:
    if path.startswith("../../images/"):
        return "../../build/images/" + path[len("../../images/") :]
    return path


def rewrite_image_paths_for_translation(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return match.group(1) + translated_image_path(match.group(2)) + match.group(3)

    return re.sub(r"(!\[[^\]]*\]\()([^)]+)(\))", replace, text)


def normalize_usage(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    elif isinstance(usage, dict):
        raw = usage
    else:
        raw = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
    return {k: v for k, v in raw.items() if v is not None}


def build_client(config: dict[str, Any]) -> OpenAI:
    if OpenAI is None:
        raise RuntimeError("openai package is not installed")
    api_key_env = config["api_key_env"]
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API token environment variable: {api_key_env}")
    return OpenAI(base_url=config["base_url"], api_key=api_key, timeout=float(config.get("timeout_seconds", 600)))


def call_modelscope(
    client: OpenAI,
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    chunk: Chunk,
    save_reasoning: bool,
) -> tuple[str, dict[str, Any]]:
    request_cfg = config["request"]
    response = client.chat.completions.create(
        model=config["model"],
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        stream=True,
        stream_options={"include_usage": True},
        temperature=request_cfg.get("temperature", 0.2),
        top_p=request_cfg.get("top_p", 0.9),
        max_tokens=request_cfg.get("max_tokens", 4096),
        extra_body=dict(request_cfg.get("extra_body") or {}),
    )

    chunk.output_path.parent.mkdir(parents=True, exist_ok=True)
    if chunk.part_path.exists():
        chunk.part_path.unlink()
    reasoning_parts: list[str] = []
    answer_parts: list[str] = []
    usage: dict[str, Any] = {}
    finish_reason = None
    request_id = None
    with chunk.part_path.open("w", encoding="utf-8") as out:
        for part in response:
            request_id = request_id or getattr(part, "id", None)
            if getattr(part, "usage", None):
                usage = normalize_usage(part.usage)
            if not getattr(part, "choices", None):
                continue
            choice = part.choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            reasoning = getattr(delta, "reasoning_content", "") or ""
            answer = getattr(delta, "content", "") or ""
            if reasoning:
                reasoning_parts.append(reasoning)
            if answer:
                answer_parts.append(answer)
                out.write(answer)
                out.flush()
    answer_text = "".join(answer_parts)
    if save_reasoning and reasoning_parts:
        chunk.part_path.with_suffix(".reasoning.txt").write_text("".join(reasoning_parts), encoding="utf-8")
    return answer_text, {"usage": usage, "finish_reason": finish_reason, "request_id": request_id}


def combine_section(chapter: int, section: str, chunks: list[Chunk], records: dict[str, dict[str, Any]]) -> bool:
    section_chunks = [chunk for chunk in chunks if chunk.section == section]
    if not section_chunks or any(not chunk_done(chunk, records) for chunk in section_chunks):
        return False
    output_root = Path("translated_content") / f"chapter_{chapter}"
    output_root.mkdir(parents=True, exist_ok=True)
    final_path = output_root / section_to_filename(section)
    final_text = "\n\n".join(chunk.output_path.read_text(encoding="utf-8").rstrip() for chunk in section_chunks)
    final_path.write_text(final_text.rstrip() + "\n", encoding="utf-8")
    return True


def estimate(chunks: list[Chunk]) -> None:
    by_section: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_section.setdefault(chunk.section, []).append(chunk)
    print("ModelScope translation estimate")
    total_tokens = 0
    for section, section_chunks in by_section.items():
        chars = sum(chunk.char_count for chunk in section_chunks)
        tokens = sum(chunk.estimated_tokens for chunk in section_chunks)
        total_tokens += tokens
        print(f"- section {section}: {len(section_chunks)} chunks, {chars} chars, ~{tokens} input tokens")
        for chunk in section_chunks:
            print(f"  - {chunk.state_key}: {chunk.char_count} chars, ~{chunk.estimated_tokens} input tokens, {len(chunk.termbase)} terms")
    print(f"Total: {len(chunks)} chunks, ~{total_tokens} input tokens before prompts/termbase")


def run_translation(
    config: dict[str, Any],
    chunks: list[Chunk],
    resume: bool,
    force: bool,
    no_thinking: bool,
    max_retries: int,
) -> int:
    if no_thinking:
        config["request"].setdefault("extra_body", {})["enable_thinking"] = False
        config["request"]["extra_body"].pop("thinking_budget", None)

    chapter = chunks[0].chapter
    paths = state_paths(chapter)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    records = load_chunk_records(chapter)
    try:
        client = build_client(config)
    except Exception as exc:
        error = {"status": "auth_error", "message": str(exc), "updated_at": now_iso()}
        write_state(chapter, "auth_error", chunks, records, error)
        print(f"Auth error: {exc}", file=sys.stderr)
        print(f"Set token and retry: {load_json(paths['state'])['suggested_resume_command']}")
        return 2

    system_prompt = Path(config["prompts"]["system_prompt_file"]).read_text(encoding="utf-8")
    user_template = Path(config["prompts"]["user_prompt_template_file"]).read_text(encoding="utf-8")
    save_reasoning = bool(config.get("streaming", {}).get("save_reasoning_trace", False))
    write_state(chapter, "running", chunks, records)

    for chunk in chunks:
        records = load_chunk_records(chapter)
        if not force and resume and chunk_done(chunk, records):
            print(f"skip done {chunk.state_key}")
            continue
        if not force and chunk.part_path.exists():
            recovered = normalize_translation_markdown(chunk.part_path.read_text(encoding="utf-8"))
            recovery_errors = validate_translation(chunk.text, recovered)
            if not recovery_errors:
                chunk.output_path.parent.mkdir(parents=True, exist_ok=True)
                chunk.output_path.write_text(recovered, encoding="utf-8")
                chunk.part_path.unlink()
                record = chunk_record(chunk, "done", attempts=0, recovered_from_part=True)
                append_jsonl(paths["chunks"], record)
                records[chunk.state_key] = record
                for section in sorted({c.section for c in chunks}):
                    combine_section(chapter, section, chunks, records)
                write_state(chapter, "running", chunks, records)
                print(f"recovered done {chunk.state_key} from .part")
                continue
        termbase_block = render_termbase(chunk.termbase)
        user_prompt = render_user_prompt(user_template, termbase_block, chunk.text)
        print(f"translate {chunk.state_key}: {chunk.char_count} chars, {len(chunk.termbase)} terms")

        for attempt in range(1, max_retries + 1):
            append_jsonl(paths["chunks"], chunk_record(chunk, "running", attempts=attempt))
            try:
                answer_text, meta = call_modelscope(client, config, system_prompt, user_prompt, chunk, save_reasoning)
                answer_text = normalize_translation_markdown(answer_text)
                validation_errors = validate_translation(chunk.text, answer_text)
                if validation_errors:
                    append_jsonl(
                        paths["usage"],
                        {
                            "state_key": chunk.state_key,
                            "updated_at": now_iso(),
                            "usage": meta.get("usage") or {},
                            "finish_reason": meta.get("finish_reason"),
                            "request_id": meta.get("request_id"),
                            "validation_errors": validation_errors,
                        },
                    )
                    raise RuntimeError("; ".join(validation_errors))
                chunk.output_path.parent.mkdir(parents=True, exist_ok=True)
                chunk.output_path.write_text(answer_text.rstrip() + "\n", encoding="utf-8")
                if chunk.part_path.exists():
                    chunk.part_path.unlink()
                record = chunk_record(
                    chunk,
                    "done",
                    attempts=attempt,
                    usage=meta.get("usage") or {},
                    finish_reason=meta.get("finish_reason"),
                    request_id=meta.get("request_id"),
                )
                append_jsonl(paths["chunks"], record)
                append_jsonl(paths["usage"], {"state_key": chunk.state_key, "updated_at": now_iso(), **meta})
                records[chunk.state_key] = record
                for section in sorted({c.section for c in chunks}):
                    combine_section(chapter, section, chunks, records)
                write_state(chapter, "running", chunks, records)
                break
            except Exception as exc:
                err = classify_exception(exc)
                if isinstance(exc, RuntimeError) and err.status == "failed":
                    err.status = "validation_error"
                append_jsonl(paths["chunks"], chunk_record(chunk, err.status, attempts=attempt, error=err.message, headers=err.headers))
                if err.status in {"quota_exhausted", "auth_error", "bad_request", "validation_error"}:
                    write_state(chapter, err.status, chunks, load_chunk_records(chapter), {"state_key": chunk.state_key, "status": err.status, "message": err.message, "headers": err.headers})
                    if err.status == "quota_exhausted":
                        print("Quota exhausted. Resume after quota refresh:")
                        print(f"python translate_modelscope.py --chapter {chapter} --resume")
                        return 3
                    print(f"{err.status}: {err.message}", file=sys.stderr)
                    return 1
                if attempt >= max_retries:
                    write_state(chapter, "paused_retryable_error", chunks, load_chunk_records(chapter), {"state_key": chunk.state_key, "status": err.status, "message": err.message, "headers": err.headers})
                    print(f"Paused after retryable error: {err.message}", file=sys.stderr)
                    print(f"Resume with: python translate_modelscope.py --chapter {chapter} --resume")
                    return 4
                sleep_for = backoff_seconds(attempt, err.retry_after)
                print(f"{err.status}, retry in {sleep_for:.1f}s")
                time.sleep(sleep_for)

    write_state(chapter, "completed", chunks, load_chunk_records(chapter))
    print("Translation completed.")
    return 0


def print_status(chapter: int | None) -> int:
    chapters = [chapter] if chapter else []
    if not chapters and STATE_ROOT.exists():
        for path in sorted(STATE_ROOT.glob("chapter_*")):
            match = re.fullmatch(r"chapter_(\d+)", path.name)
            if match:
                chapters.append(int(match.group(1)))
    if not chapters:
        print("No translation state found.")
        return 0
    for ch in chapters:
        path = state_paths(ch)["state"]
        if not path.exists():
            print(f"chapter {ch}: no state")
            continue
        data = load_json(path)
        print(f"chapter {ch}: {data.get('status')} {data.get('done_chunks')}/{data.get('total_chunks')} done, pending {data.get('pending_chunks')}")
        if data.get("last_error"):
            print(f"  last_error: {data['last_error'].get('status')} {data['last_error'].get('message')}")
        print(f"  resume: {data.get('suggested_resume_command')}")
    return 0


def smoke_test(config: dict[str, Any], no_thinking: bool) -> int:
    try:
        client = build_client(config)
    except Exception as exc:
        print(f"Auth error: {exc}", file=sys.stderr)
        return 2
    if no_thinking:
        config["request"].setdefault("extra_body", {})["enable_thinking"] = False
        config["request"]["extra_body"].pop("thinking_budget", None)
    response = client.chat.completions.create(
        model=config["model"],
        messages=[{"role": "user", "content": "9.9和9.11谁大"}],
        stream=True,
        stream_options={"include_usage": True},
        extra_body=config["request"].get("extra_body") or {},
    )
    done_thinking = False
    usage: dict[str, Any] = {}
    for chunk in response:
        if getattr(chunk, "usage", None):
            usage = normalize_usage(chunk.usage)
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        thinking_chunk = getattr(delta, "reasoning_content", "") or ""
        answer_chunk = getattr(delta, "content", "") or ""
        if thinking_chunk:
            print(thinking_chunk, end="", flush=True)
        elif answer_chunk:
            if not done_thinking:
                print("\n\n=== Final Answer ===\n")
                done_thinking = True
            print(answer_chunk, end="", flush=True)
    if usage:
        print(f"\n\nusage: {json.dumps(usage, ensure_ascii=False)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate Markdown sections through ModelScope.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--chapter", type=int)
    parser.add_argument("--section", help="Section number, for example 5.2")
    parser.add_argument("--estimate", action="store_true", help="Estimate chunks and tokens without API calls")
    parser.add_argument("--resume", action="store_true", help="Run or resume translation")
    parser.add_argument("--force", action="store_true", help="Redo selected chunks even if already done")
    parser.add_argument("--status", action="store_true", help="Show translation status")
    parser.add_argument("--no-thinking", action="store_true", help="Disable Qwen thinking mode")
    parser.add_argument("--smoke-test", action="store_true", help="Run the small ModelScope API smoke test")
    parser.add_argument("--max-retries", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_json(Path(args.config))
    if args.status:
        return print_status(args.chapter)
    if args.smoke_test:
        return smoke_test(config, args.no_thinking)

    all_terms = load_terms(Path(config["translation"]["termbase_csv"]))
    priority_terms = load_priority_terms(Path(config["translation"]["termbase_json"]))
    chapter = args.chapter or 5
    chunks = build_chunks(config, chapter, args.section, all_terms, priority_terms)

    if args.estimate or not args.resume:
        estimate(chunks)
        if not args.resume:
            print("\nNo API call was made. Run with --resume to translate.")
            return 0

    return run_translation(
        config=config,
        chunks=chunks,
        resume=args.resume,
        force=args.force,
        no_thinking=args.no_thinking,
        max_retries=args.max_retries,
    )


if __name__ == "__main__":
    raise SystemExit(main())
