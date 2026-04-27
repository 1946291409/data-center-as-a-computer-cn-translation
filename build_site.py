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
    1: (
        "本章说明仓库规模计算机（WSC）为何成为现代互联网服务和云计算的基础形态。"
        "阅读重点是理解单台服务器、传统数据中心与 WSC 之间的尺度差异，以及这些差异如何改变系统设计目标。"
        "它也为后续章节中的硬件、软件、成本和可靠性讨论建立共同背景。"
    ),
    2: (
        "本章从整体架构角度介绍 WSC 的主要组成，包括园区、建筑、服务器、存储、网络和能源使用。"
        "阅读时可以把它看作全书的地图：后续章节会分别展开这些组件的设计约束和工程权衡。"
        "本章尤其适合用来建立对 WSC 物理形态与系统边界的直观认识。"
    ),
    3: (
        "本章讨论运行在 WSC 上的主要工作负载，从在线服务、数据处理到人工智能应用。"
        "这些工作负载的规模、交互模式和资源需求决定了基础设施必须如何设计和调度。"
        "理解本章有助于把后续的软件系统、硬件选择和成本优化放回真实应用场景中。"
    ),
    4: (
        "本章梳理支撑 WSC 的软件基础设施，包括集群管理、存储、通信和服务运维相关系统。"
        "阅读重点是理解这些软件层如何把大量不可靠的硬件组织成可编程、可运维的平台。"
        "它连接了前面的工作负载需求和后面的软件定义基础设施讨论。"
    ),
    5: (
        "本章介绍数据中心基础设施本身，重点包括供电、制冷、建筑空间和运维安全。"
        "这些设施并不直接执行计算，但决定了 WSC 能否在高功率密度和高可用性要求下持续运行。"
        "阅读本章时可以关注物理基础设施如何与计算系统设计相互约束。"
    ),
    6: (
        "本章转向 WSC 内部的计算构件，包括服务器、处理器、加速器、网络接口和存储设备。"
        "阅读重点是理解单个硬件构件的选择如何影响大规模系统的性能、成本、能效和可靠性。"
        "它也为后续关于软件定义基础设施和资源调度的章节提供硬件背景。"
    ),
    7: (
        "本章讨论软件定义基础设施如何抽象和管理底层硬件资源。"
        "重点在于理解控制平面、资源隔离、调度和自动化机制如何提高 WSC 的利用率与可操作性。"
        "本章把前面介绍的硬件资源转化为可以由软件持续优化的平台能力。"
    ),
    8: (
        "本章从性能与成本角度分析 WSC 的设计取舍。"
        "阅读重点是理解延迟、吞吐、利用率、资本支出和运营支出之间的关系，而不是孤立地追求单项指标。"
        "它为后续能源、可靠性和安全等主题提供经济约束视角。"
    ),
    9: (
        "本章讨论 WSC 的能源使用、功率管理和可持续性问题。"
        "随着计算规模扩大，能源效率、碳影响和电力基础设施不再是外围问题，而是系统设计的核心约束。"
        "阅读本章时可以关注技术演进、运营策略和环境目标之间的相互影响。"
    ),
    10: (
        "本章围绕可信计算展开，覆盖可靠性、可用性、安全和隐私等主题。"
        "WSC 的规模会放大故障、攻击面和数据保护挑战，因此需要从硬件、软件和组织流程多个层面共同设计。"
        "本章适合与前面的基础设施和调度章节对照阅读。"
    ),
    11: (
        "本章回顾 WSC 在 Google 内部长期演进的关键阶段。"
        "它从历史角度展示许多架构选择并非一次性完成，而是在业务规模、硬件能力和运维经验变化中逐步形成。"
        "阅读本章有助于理解前面各章技术主题背后的实践路径。"
    ),
    12: (
        "本章整理与 WSC 发展相关的 25 篇代表性论文，并给出简要说明和选择理由。"
        "它不是普通章节式叙述，而是面向进一步阅读的文献索引。"
        "读者可以用它回溯全书涉及的关键系统、设计思想和研究脉络。"
    ),
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
