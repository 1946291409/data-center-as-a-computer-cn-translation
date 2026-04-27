from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REVIEWED_DIR = ROOT / "reviewed_content"
IMAGES_DIR = ROOT / "build" / "images"
TERMS_CSV = ROOT / "terminology" / "terms.csv"
SITE_DIR = ROOT / "site"
SITE_DOCS_DIR = SITE_DIR / "docs"
SITE_PUBLIC_IMAGES_DIR = SITE_DOCS_DIR / "public" / "images"
SITE_DATA_FILE = SITE_DOCS_DIR / ".vitepress" / "site-data.mjs"

CHAPTER_TITLE_MAP = {
    1: "第 1 章 引言",
    2: "第 2 章 WSC 架构概览",
    3: "第 3 章 WSC 工作负载概览",
    4: "第 4 章 WSC 软件：分布式系统基础设施",
    5: "第 5 章 WSC 硬件：数据中心基础设施",
    6: "第 6 章 WSC 硬件：计算构件",
    7: "第 7 章 软件定义基础设施",
    8: "第 8 章 性能与成本",
    9: "第 9 章 能源与可持续性",
    10: "第 10 章 可信计算：可靠性、可用性、安全性与隐私",
    11: "第 11 章 25 年 WSC 之旅",
    12: "第 12 章 WSC 25 年 25 篇精选论文",
}

CHAPTER_DESCRIPTION_MAP = {
    1: "介绍云计算与仓库规模计算机的背景、动因与整体问题空间。",
    2: "概览 WSC 的物理组成、园区布局、计算与网络构件。",
    3: "总结 WSC 中的核心工作负载、服务模型与典型应用形态。",
    4: "梳理支撑 WSC 的分布式系统软件基础设施。",
    5: "介绍数据中心基础设施，包括供电、制冷与建筑层面设计。",
    6: "介绍服务器、加速器、网络与存储等核心计算构件。",
    7: "讨论软件定义基础设施的抽象层、优化手段与调度能力。",
    8: "从性能与成本角度分析 WSC 设计中的关键权衡。",
    9: "讨论能耗、功率管理与可持续性相关的系统设计问题。",
    10: "讨论可靠性、可用性、安全与隐私相关的可信计算主题。",
    11: "回顾 WSC 在 Google 的长期演进历程与关键里程碑。",
    12: "整理 25 篇代表性论文，并给出简要说明与阅读理由。",
}

IMAGE_PATTERN = re.compile(r"\((\.\./\.\./build/images/chapter_(\d+)/([^)]+))\)")
SECTION_FILE_PATTERN = re.compile(r"section_(\d+)_(\d+)\.md$")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def reset_generated_dirs() -> None:
    ensure_dir(SITE_DOCS_DIR)
    ensure_dir(SITE_PUBLIC_IMAGES_DIR)
    generated_dirs = [p for p in SITE_DOCS_DIR.glob("chapter-*") if p.is_dir()]
    for path in generated_dirs:
        shutil.rmtree(path)
    if SITE_PUBLIC_IMAGES_DIR.exists():
        for path in SITE_PUBLIC_IMAGES_DIR.glob("chapter-*"):
            if path.is_dir():
                shutil.rmtree(path)


def extract_first_heading(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            heading = match.group(2)
            lines[idx] = f"# {heading}"
            return heading, "\n".join(lines).rstrip() + "\n"
    raise ValueError("No markdown heading found")


def rewrite_image_paths(text: str, chapter_number: int) -> str:
    chapter_slug = f"chapter-{chapter_number:02d}"

    def repl(match: re.Match[str]) -> str:
        filename = match.group(3)
        return f"(/images/{chapter_slug}/{filename})"

    return IMAGE_PATTERN.sub(repl, text)


def copy_chapter_images(chapter_number: int) -> None:
    src = IMAGES_DIR / f"chapter_{chapter_number}"
    dst = SITE_PUBLIC_IMAGES_DIR / f"chapter-{chapter_number:02d}"
    ensure_dir(dst)
    for image in sorted(src.glob("*")):
        if image.is_file():
            shutil.copy2(image, dst / image.name)


def load_terms() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with TERMS_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def build_glossary_md() -> str:
    rows = sorted(load_terms(), key=lambda row: (row["category"], row["source"].lower()))
    header = [
        "# 术语表",
        "",
        "本页整理当前译文中已经固定使用或优先采用的主要术语，便于阅读时统一理解英文原词与中文译法。",
        "",
        "> 说明：页面只展示术语、译法与必要备注，不展示内部流程字段。",
        "",
        "| English | 中文译法 | 说明 |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        note = row["notes"].strip() or "—"
        header.append(f"| {row['source']} | {row['target']} | {note} |")
    return "\n".join(header).rstrip() + "\n"


def build_home_md(chapters: list[dict[str, object]]) -> str:
    lines = [
        "# The Data Center as a Computer",
        "",
        "这个站点用于在线浏览《The Data Center as a Computer》的中文译文，当前正文来源于项目内的二阶段稳定稿 `reviewed_content/`。",
        "",
        "## 站点说明",
        "",
        "- 正文以当前中文译文定稿为准。",
        "- 章节、小节、图片、图注与公式结构尽量保持原书组织方式。",
        "- 术语表与译者说明可作为辅助阅读入口。",
        "",
        "## 阅读入口",
        "",
    ]
    for chapter in chapters:
        lines.append(f"- [{chapter['title']}](./{chapter['slug']}/index.md)")
    lines.extend(
        [
            "",
            "## 辅助入口",
            "",
            "- [译者说明](./preface.md)",
            "- [术语表](./glossary.md)",
            "",
            "## 边界",
            "",
            "- 审计报告、初译稿和内部工具产物不在站点中公开展示。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_preface_md() -> str:
    return (
        "# 译者说明\n\n"
        "本项目用于整理英文技术书《The Data Center as a Computer》的中文译文，并在尽量保留原书技术表达、结构层次和术语一致性的前提下完成校审与发布整理。\n\n"
        "当前网页版本基于项目中的二阶段校订稿生成。正文保留原有段落划分、图片、图注、引用与公式结构；术语、数字、图片路径和关键技术表述均经过结构校验与重点章节复核。\n\n"
        "站点发布目标是提供稳定、可浏览、可持续修订的阅读版本，而不是公开展示内部翻译流水线本身。初译稿、审计报告、状态文件与中间产物不作为站点内容公开呈现。\n\n"
        "如原书或相关材料涉及版权限制，本仓库与站点内容仅用于个人学习、研究与翻译校对整理，不用于商业传播。\n"
    )


def build_chapter_index_md(chapter_title: str, description: str, section_items: list[dict[str, str]]) -> str:
    lines = [
        f"# {chapter_title}",
        "",
        description,
        "",
        "## 本章目录",
        "",
    ]
    for item in section_items:
        lines.append(f"- [{item['title']}](./{item['file_name']})")
    return "\n".join(lines).rstrip() + "\n"


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def render_site_data(chapters: list[dict[str, object]]) -> str:
    payload = json.dumps(chapters, ensure_ascii=False, indent=2)
    return (
        f"export const chapters = {payload};\n\n"
        "export const sidebar = chapters.map((chapter) => ({\n"
        "  text: chapter.title,\n"
        "  items: chapter.sections.map((section) => ({\n"
        "    text: section.title,\n"
        "    link: `/${chapter.slug}/${section.file_name}`,\n"
        "  })),\n"
        "}));\n"
    )


def generate_site_docs() -> list[dict[str, object]]:
    reset_generated_dirs()
    chapters: list[dict[str, object]] = []
    for chapter_dir in sorted(REVIEWED_DIR.glob("chapter_*"), key=lambda p: int(p.name.split("_")[1])):
        match = re.match(r"chapter_(\d+)$", chapter_dir.name)
        if not match:
            continue
        chapter_number = int(match.group(1))
        chapter_slug = f"chapter-{chapter_number:02d}"
        chapter_title = CHAPTER_TITLE_MAP[chapter_number]
        section_entries: list[dict[str, str]] = []

        copy_chapter_images(chapter_number)
        out_chapter_dir = SITE_DOCS_DIR / chapter_slug
        ensure_dir(out_chapter_dir)

        section_paths = sorted(
            chapter_dir.glob("section_*.md"),
            key=lambda p: tuple(int(x) for x in SECTION_FILE_PATTERN.search(p.name).groups()),
        )
        for idx, src_path in enumerate(section_paths, start=1):
            text = src_path.read_text(encoding="utf-8")
            title, body = extract_first_heading(text)
            body = rewrite_image_paths(body, chapter_number)
            file_name = f"{idx:02d}-section.md"
            write_text(out_chapter_dir / file_name, body)
            section_entries.append({"title": title, "file_name": file_name})

        index_md = build_chapter_index_md(
            chapter_title,
            CHAPTER_DESCRIPTION_MAP[chapter_number],
            section_entries,
        )
        write_text(out_chapter_dir / "index.md", index_md)
        chapters.append(
            {
                "number": chapter_number,
                "slug": chapter_slug,
                "title": chapter_title,
                "sections": section_entries,
            }
        )

    write_text(SITE_DOCS_DIR / "index.md", build_home_md(chapters))
    write_text(SITE_DOCS_DIR / "preface.md", build_preface_md())
    write_text(SITE_DOCS_DIR / "glossary.md", build_glossary_md())
    write_text(SITE_DATA_FILE, render_site_data(chapters))
    return chapters


if __name__ == "__main__":
    chapters = generate_site_docs()
    print(f"Generated {len(chapters)} chapters into {SITE_DOCS_DIR}")
