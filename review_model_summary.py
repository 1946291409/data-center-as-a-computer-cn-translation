#!/usr/bin/env python3
"""Render ModelScope review JSON into a readable Markdown summary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_review_entries(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        return json.loads(stripped)
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def parse_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return {"has_issue": True, "issues": [], "summary": "Failed to parse model JSON.", "raw": content}


def render(chapter: int, entries: list[dict[str, Any]]) -> str:
    lines = [f"# Chapter {chapter} Model Review Summary", ""]
    total = 0
    by_priority: dict[str, int] = {}
    parsed_entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in entries:
        parsed = parse_content(entry.get("content", ""))
        parsed_entries.append((entry, parsed))
        for issue in parsed.get("issues", []):
            total += 1
            priority = str(issue.get("priority", "P?"))
            by_priority[priority] = by_priority.get(priority, 0) + 1
    lines.append(f"- Entries: {len(entries)}")
    lines.append(f"- Issues: {total}")
    for priority in ["P0", "P1", "P2", "P3", "P?"]:
        if priority in by_priority:
            lines.append(f"- {priority}: {by_priority[priority]}")
    lines.extend(["", "## Issues", ""])
    for entry, parsed in parsed_entries:
        section = entry.get("section", "")
        lines.append(f"### Section {section}")
        summary = parsed.get("summary", "")
        if summary:
            lines.append("")
            lines.append(str(summary))
        issues = parsed.get("issues", [])
        if not issues:
            lines.append("")
            lines.append("- None")
            continue
        for idx, issue in enumerate(issues, start=1):
            priority = issue.get("priority", "P?")
            issue_type = issue.get("type", "unknown")
            lines.append("")
            lines.append(f"{idx}. [{priority}] {issue_type}")
            if issue.get("source_excerpt"):
                lines.append(f"   原文：{issue['source_excerpt']}")
            if issue.get("translation_excerpt"):
                lines.append(f"   译文：{issue['translation_excerpt']}")
            if issue.get("reason"):
                lines.append(f"   理由：{issue['reason']}")
            if issue.get("suggestion"):
                lines.append(f"   建议：{issue['suggestion']}")
            if issue.get("confidence") is not None:
                lines.append(f"   置信度：{issue['confidence']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize ModelScope review output.")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input or f"review_reports/chapter_{args.chapter}/model_review.jsonl")
    output_path = Path(args.output or f"review_reports/chapter_{args.chapter}/model_review.md")
    entries = load_review_entries(input_path)
    output_path.write_text(render(args.chapter, entries), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
