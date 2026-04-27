#!/usr/bin/env python3
"""Extract clean Markdown drafts from the Springer EPUB.

The first production target is chapter 5 of "The Data Center as a Computer".
This script intentionally uses only the Python standard library so it can run
in the current workspace without installing parser dependencies.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import posixpath
import re
import shutil
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


EPUB_NS = "http://www.idpf.org/2007/opf"
XHTML_NS = "http://www.w3.org/1999/xhtml"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

NS = {
    "opf": EPUB_NS,
    "xhtml": XHTML_NS,
    "container": CONTAINER_NS,
}


@dataclass
class Figure:
    fig_id: str
    number: str
    caption: str
    src: str
    epub_path: str
    output_file: str
    markdown_path: str
    copied: bool = False
    inserted: bool = False
    first_reference_found: bool = False


@dataclass
class RenderStats:
    paragraphs: int = 0
    lists: int = 0
    list_items: int = 0
    headings: int = 0
    formulas: int = 0
    inserted_figures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    chapter_number: int
    chapter_file: str
    chapter_title: str
    chapter_markdown: str
    section_markdown: dict[str, str]
    figures: dict[str, Figure]
    report: dict
    errors: list[str]
    warnings: list[str]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def has_class(elem: ET.Element, class_name: str) -> bool:
    classes = elem.attrib.get("class", "").split()
    return class_name in classes


def class_contains(elem: ET.Element, token: str) -> bool:
    return token in elem.attrib.get("class", "")


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\u00a0", " ")
    value = value.replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"(\$[^$]+\$)\(", r"\1 (", value)
    return value.strip()


def safe_filename_text(value: str, max_len: int = 70) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "Figure"
    return value[:max_len].rstrip("_")


def parse_xml_bytes(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def read_rootfile_path(epub: zipfile.ZipFile) -> str:
    container = parse_xml_bytes(epub.read("META-INF/container.xml"))
    rootfile = container.find(".//container:rootfile", NS)
    if rootfile is None or not rootfile.attrib.get("full-path"):
        raise ValueError("Could not locate rootfile in META-INF/container.xml")
    return rootfile.attrib["full-path"]


def read_spine(epub: zipfile.ZipFile, opf_path: str) -> list[str]:
    root = parse_xml_bytes(epub.read(opf_path))
    opf_dir = posixpath.dirname(opf_path)

    manifest: dict[str, str] = {}
    for item in root.findall(".//opf:manifest/opf:item", NS):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if item_id and href:
            manifest[item_id] = posixpath.normpath(posixpath.join(opf_dir, href))

    spine_paths: list[str] = []
    for itemref in root.findall(".//opf:spine/opf:itemref", NS):
        idref = itemref.attrib.get("idref")
        if idref in manifest:
            spine_paths.append(manifest[idref])
    return spine_paths


def find_chapter_file(epub: zipfile.ZipFile, spine_paths: list[str], chapter: int) -> str:
    target_prefix = f"{chapter}."
    href_hint = f"_En_{chapter}_Chapter.xhtml"
    for path in spine_paths:
        if path.endswith(href_hint):
            return path

    for path in spine_paths:
        if not path.endswith(".xhtml"):
            continue
        try:
            root = parse_xml_bytes(epub.read(path))
        except ET.ParseError:
            continue
        title = find_chapter_title(root)
        if title.startswith(target_prefix):
            return path

    raise ValueError(f"Could not find chapter {chapter} in EPUB spine")


def iter_descendants(elem: ET.Element, name: str | None = None) -> Iterable[ET.Element]:
    for child in elem.iter():
        if name is None or local_name(child.tag) == name:
            yield child


def find_chapter_title(root: ET.Element) -> str:
    titles: list[str] = []
    for elem in iter_descendants(root, "h1"):
        if has_class(elem, "ChapterTitle"):
            titles.append(inline_text(elem, RenderStats()))
    if not titles:
        for elem in iter_descendants(root, "h1"):
            titles.append(inline_text(elem, RenderStats()))
    return normalize_text(titles[0]) if titles else ""


def count_chapter_titles(root: ET.Element) -> int:
    count = sum(1 for elem in iter_descendants(root, "h1") if has_class(elem, "ChapterTitle"))
    if count == 0:
        count = sum(1 for elem in iter_descendants(root, "h1"))
    return count


def find_fulltext(root: ET.Element) -> ET.Element:
    for elem in iter_descendants(root, "div"):
        if has_class(elem, "Fulltext"):
            return elem
    raise ValueError("Could not locate div.Fulltext in chapter XHTML")


def heading_level(elem: ET.Element) -> int | None:
    name = local_name(elem.tag)
    if re.fullmatch(r"h[1-6]", name):
        return int(name[1])
    return None


def is_heading(elem: ET.Element) -> bool:
    return heading_level(elem) is not None and has_class(elem, "Heading")


def is_section(elem: ET.Element) -> bool:
    return local_name(elem.tag) == "section" and class_contains(elem, "Section")


def is_para(elem: ET.Element) -> bool:
    return local_name(elem.tag) in {"p", "div"} and has_class(elem, "Para")


def is_list_container(elem: ET.Element) -> bool:
    return has_class(elem, "UnorderedList") or has_class(elem, "OrderedList") or local_name(elem.tag) in {
        "ul",
        "ol",
    }


def is_figure(elem: ET.Element) -> bool:
    return local_name(elem.tag) == "figure" and has_class(elem, "Figure")


def math_text(elem: ET.Element) -> str:
    alt = elem.attrib.get("alttext", "")
    if not alt:
        return ""
    text = html.unescape(alt).strip()
    display = elem.attrib.get("display", "inline")
    if text.startswith("$$") and text.endswith("$$"):
        inner = text[2:-2].strip()
        inner = clean_tex_fragment(inner)
        if display == "inline":
            return f"${inner}$"
        return f"$${inner}$$"
    return text


def clean_tex_fragment(value: str) -> str:
    value = html.unescape(value).strip()
    value = re.sub(r"\\text\s*\{([^{}]*)\}", r"\1", value)
    value = value.replace(r"\ ", " ")
    value = re.sub(r"\\+$", "", value).strip()
    value = re.sub(r"\\left\s*([\(\[\{])", r"\1", value)
    value = re.sub(r"\\right\s*([\)\]\}])", r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    simple_wrapped = re.fullmatch(r"\(([^(){}\\]+)\)", value)
    if simple_wrapped:
        value = simple_wrapped.group(1).strip()
    return value


def inline_text(elem: ET.Element, stats: RenderStats, skip_blocks: bool = True) -> str:
    pieces: list[str] = []

    def walk(node: ET.Element) -> None:
        if local_name(node.tag) == "math":
            formula = math_text(node)
            if formula:
                pieces.append(formula)
                stats.formulas += 1
            if node.tail:
                pieces.append(node.tail)
            return

        if skip_blocks and (is_figure(node) or is_list_container(node)) and node is not elem:
            if node.tail:
                pieces.append(node.tail)
            return

        if node.text:
            pieces.append(node.text)
        for child in list(node):
            walk(child)
        if node is not elem and node.tail:
            pieces.append(node.tail)

    walk(elem)
    return normalize_text("".join(pieces))


def find_first_descendant(elem: ET.Element, tag: str, class_name: str | None = None) -> ET.Element | None:
    for child in iter_descendants(elem, tag):
        if class_name is None or has_class(child, class_name):
            return child
    return None


def collect_figures(
    epub: zipfile.ZipFile,
    chapter_file: str,
    fulltext: ET.Element,
    chapter_number: int,
) -> dict[str, Figure]:
    figures: dict[str, Figure] = {}
    chapter_dir = posixpath.dirname(chapter_file)

    for figure in iter_descendants(fulltext, "figure"):
        if not is_figure(figure):
            continue

        fig_id = figure.attrib.get("id", "")
        if not fig_id:
            continue

        caption_number_elem = find_first_descendant(figure, "span", "CaptionNumber")
        caption_text_elem = find_first_descendant(figure, "p", "SimplePara")
        img_elem = find_first_descendant(figure, "img")
        if caption_number_elem is None or caption_text_elem is None or img_elem is None:
            continue

        number = inline_text(caption_number_elem, RenderStats())
        caption = inline_text(caption_text_elem, RenderStats())
        src = img_elem.attrib.get("src", "")
        if not src:
            continue

        epub_path = posixpath.normpath(posixpath.join(chapter_dir, src))
        ext = Path(posixpath.basename(epub_path)).suffix
        fig_match = re.search(r"(\d+)\.(\d+)", number)
        if fig_match:
            file_base = f"chapter_{fig_match.group(1)}_fig_{fig_match.group(2)}"
        else:
            file_base = f"chapter_{chapter_number}_{fig_id.lower()}"
        output_file = f"{file_base}_{safe_filename_text(caption)}{ext}"
        markdown_path = f"../../images/chapter_{chapter_number}/{output_file}"

        figures[fig_id] = Figure(
            fig_id=fig_id,
            number=number,
            caption=caption,
            src=src,
            epub_path=epub_path,
            output_file=output_file,
            markdown_path=markdown_path,
        )

    return figures


def copy_figures(epub: zipfile.ZipFile, figures: dict[str, Figure], output_dir: Path, chapter_number: int) -> None:
    image_dir = output_dir / "images" / f"chapter_{chapter_number}"
    image_dir.mkdir(parents=True, exist_ok=True)
    for old_file in image_dir.glob(f"chapter_{chapter_number}_fig_*"):
        if old_file.is_file():
            try:
                old_file.unlink()
            except PermissionError:
                pass

    used_names: set[str] = set()
    for figure in figures.values():
        name = figure.output_file
        if name in used_names:
            stem = Path(name).stem
            suffix = Path(name).suffix
            i = 2
            while f"{stem}_{i}{suffix}" in used_names:
                i += 1
            name = f"{stem}_{i}{suffix}"
            figure.output_file = name
            figure.markdown_path = f"../../images/chapter_{chapter_number}/{name}"
        used_names.add(name)

        target = image_dir / name
        with epub.open(figure.epub_path) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        figure.copied = target.exists() and target.stat().st_size > 0


def build_figure_lookup(figures: dict[str, Figure]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for fig_id, figure in figures.items():
        match = re.search(r"(\d+\.\d+)", figure.number)
        if match:
            lookup[match.group(1)] = fig_id
    return lookup


def render_figure(figure: Figure, stats: RenderStats) -> str:
    figure.inserted = True
    stats.inserted_figures.append(figure.number)
    alt = f"{figure.number} {figure.caption}".strip()
    return f"![{alt}]({figure.markdown_path})\n\n{alt}"


def referenced_figures(text: str, figure_lookup: dict[str, str], chapter_number: int) -> list[str]:
    refs: list[str] = []
    pattern = re.compile(
        rf"\b(?:Figure|Figures|Fig\.|Figs\.)\s+{chapter_number}\.\d+"
        rf"(?:\s*(?:,|and|or)\s*{chapter_number}\.\d+)*\b"
    )
    for match in pattern.finditer(text):
        for number in re.findall(rf"{chapter_number}\.\d+", match.group(0)):
            fig_id = figure_lookup.get(number)
            if fig_id and fig_id not in refs:
                refs.append(fig_id)
    return refs


class MarkdownRenderer:
    def __init__(
        self,
        figures: dict[str, Figure],
        chapter_number: int,
        scope: ET.Element,
        fallback_reference_scope: ET.Element | None = None,
    ) -> None:
        self.figures = figures
        self.chapter_number = chapter_number
        self.figure_lookup = build_figure_lookup(figures)
        reference_scope = fallback_reference_scope if fallback_reference_scope is not None else scope
        self.fallback_references = collect_scope_referenced_figure_ids(
            reference_scope,
            self.figure_lookup,
            chapter_number,
        )
        self.inserted: set[str] = set()
        self.stats = RenderStats()

    def render_section(self, section: ET.Element) -> list[str]:
        blocks: list[str] = []
        for child in list(section):
            if is_heading(child):
                level = heading_level(child)
                if level is None:
                    continue
                hashes = "#" * level
                text = inline_text(child, self.stats)
                if text:
                    self.stats.headings += 1
                    blocks.append(f"{hashes} {text}")
            elif is_para(child):
                blocks.extend(self.render_para(child))
            elif is_list_container(child):
                blocks.extend(self.render_list(child))
            elif is_figure(child):
                blocks.extend(self.render_fallback_figure(child))
            elif is_section(child):
                blocks.extend(self.render_section(child))
        return blocks

    def render_para(self, para: ET.Element) -> list[str]:
        blocks: list[str] = []
        text = inline_text(para, self.stats)
        if text:
            self.stats.paragraphs += 1
            blocks.append(text)
            for fig_id in referenced_figures(text, self.figure_lookup, self.chapter_number):
                if fig_id not in self.inserted:
                    figure = self.figures[fig_id]
                    figure.first_reference_found = True
                    blocks.append(render_figure(figure, self.stats))
                    self.inserted.add(fig_id)

        for child in list(para):
            if is_list_container(child):
                blocks.extend(self.render_list(child))

        for child in list(para):
            if is_figure(child):
                fig_id = child.attrib.get("id", "")
                if fig_id and fig_id not in self.inserted:
                    if fig_id in self.fallback_references:
                        continue
                    self.stats.warnings.append(
                        f"{fig_id} had no recognized first reference; inserted after containing paragraph"
                    )
                    blocks.extend(self.render_fallback_figure(child))

        return blocks

    def render_fallback_figure(self, figure_elem: ET.Element) -> list[str]:
        fig_id = figure_elem.attrib.get("id", "")
        if not fig_id or fig_id not in self.figures or fig_id in self.inserted:
            return []
        if fig_id in self.fallback_references:
            return []
        figure = self.figures[fig_id]
        self.inserted.add(fig_id)
        return [render_figure(figure, self.stats)]

    def render_list(self, list_elem: ET.Element) -> list[str]:
        list_node = list_elem
        if local_name(list_elem.tag) not in {"ul", "ol"}:
            found_list = find_first_descendant(list_elem, "ul")
            if found_list is None:
                found_list = find_first_descendant(list_elem, "ol")
            list_node = found_list if found_list is not None else list_elem

        ordered = local_name(list_node.tag) == "ol" or has_class(list_elem, "OrderedList")
        items: list[str] = []
        index = 1
        for child in list_node:
            if local_name(child.tag) != "li":
                continue
            item_text = inline_text(child, self.stats)
            if not item_text:
                continue
            marker = f"{index}." if ordered else "-"
            items.append(f"{marker} {item_text}")
            index += 1

        if items:
            self.stats.lists += 1
            self.stats.list_items += len(items)
            return ["\n".join(items)]
        return []


def collect_scope_referenced_figure_ids(
    scope: ET.Element,
    figure_lookup: dict[str, str],
    chapter_number: int,
) -> set[str]:
    refs: set[str] = set()
    for elem in iter_descendants(scope):
        if not is_para(elem):
            continue
        text = inline_text(elem, RenderStats())
        refs.update(referenced_figures(text, figure_lookup, chapter_number))
    return refs


def render_markdown(blocks: list[str]) -> str:
    cleaned = [block.strip() for block in blocks if block and block.strip()]
    text = "\n\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def direct_section1(fulltext: ET.Element) -> list[ET.Element]:
    sections: list[ET.Element] = []
    for child in list(fulltext):
        if is_section(child) and class_contains(child, "Section1"):
            sections.append(child)
    return sections


def section_number(section: ET.Element) -> str:
    for child in list(section):
        if is_heading(child):
            text = inline_text(child, RenderStats())
            match = re.match(r"(\d+\.\d+)", text)
            if match:
                return match.group(1)
    return ""


def collect_section_numbers(sections: list[ET.Element]) -> list[str]:
    return [num for section in sections if (num := section_number(section))]


def count_fulltext_math(fulltext: ET.Element) -> int:
    return sum(1 for elem in iter_descendants(fulltext, "math"))


def count_all_section_headings(fulltext: ET.Element) -> int:
    return sum(1 for elem in iter_descendants(fulltext) if is_heading(elem))


def write_outputs(
    output_dir: Path,
    chapter_number: int,
    chapter_markdown: str,
    section_markdown: dict[str, str],
    report: dict,
) -> dict[str, str]:
    chapter_dir = output_dir / "original_text" / f"chapter_{chapter_number}"
    report_dir = output_dir / "reports"

    chapter_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    for old_file in chapter_dir.glob("*.md"):
        try:
            old_file.unlink()
        except PermissionError:
            pass

    chapter_path = chapter_dir / f"chapter_{chapter_number}.md"
    chapter_path.write_text(chapter_markdown, encoding="utf-8")

    section_paths: dict[str, str] = {}
    for number, markdown in section_markdown.items():
        suffix = number.replace(".", "_")
        section_path = chapter_dir / f"section_{suffix}.md"
        section_path.write_text(markdown, encoding="utf-8")
        section_paths[number] = str(section_path)

    json_path = report_dir / f"chapter_{chapter_number}_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = report_dir / f"chapter_{chapter_number}_report.md"
    md_path.write_text(report_to_markdown(report), encoding="utf-8")

    return {
        "chapter": str(chapter_path),
        "report_json": str(json_path),
        "report_md": str(md_path),
        **{f"section_{number}": path for number, path in section_paths.items()},
    }


def report_to_markdown(report: dict) -> str:
    lines: list[str] = [
        f"# Chapter {report['chapter']} Extraction Report",
        "",
        f"- Source XHTML: `{report['source_chapter_file']}`",
        f"- Chapter title: `{report['chapter_title']}`",
        f"- Section1 numbers: {', '.join(report['section1_numbers'])}",
        f"- Paragraphs: {report['counts']['paragraphs']}",
        f"- Lists: {report['counts']['lists']}",
        f"- List items: {report['counts']['list_items']}",
        f"- Headings rendered: {report['counts']['headings_rendered']}",
        f"- Math formulas in source: {report['counts']['math_formulas_in_source']}",
        f"- Figures copied: {report['counts']['figures_copied']} / {report['counts']['figures_total']}",
        f"- Figures inserted: {report['counts']['figures_inserted']} / {report['counts']['figures_total']}",
        "",
        "## Figures",
        "",
    ]

    for figure in report["figures"]:
        lines.append(
            f"- {figure['number']}: `{figure['output_file']}` "
            f"(first reference: {'yes' if figure['first_reference_found'] else 'no'})"
        )

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- None")

    lines.extend(["", "## Errors", ""])
    if report["errors"]:
        lines.extend(f"- {error}" for error in report["errors"])
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def validate(
    chapter_number: int,
    chapter_title: str,
    chapter_title_count: int,
    section1_numbers: list[str],
    figures: dict[str, Figure],
    chapter_markdown: str,
    section_markdown: dict[str, str],
    report_warnings: list[str],
) -> list[str]:
    errors: list[str] = []

    if chapter_title_count != 1:
        errors.append(f"Chapter title count mismatch: expected 1, got {chapter_title_count}")

    if not chapter_title.startswith(f"{chapter_number}."):
        errors.append(f"Chapter title does not start with '{chapter_number}.': {chapter_title!r}")

    if not section1_numbers:
        errors.append("No top-level numbered sections were rendered")
    for number in section1_numbers:
        if not re.fullmatch(rf"{chapter_number}\.\d+", number):
            errors.append(f"Section number does not belong to chapter {chapter_number}: {number}")

    expected_fig_numbers = [f"Fig. {chapter_number}.{i}" for i in range(1, len(figures) + 1)]
    actual_fig_numbers = [fig.number for fig in sorted(figures.values(), key=figure_sort_key)]
    if actual_fig_numbers != expected_fig_numbers:
        errors.append(f"Figure numbers mismatch: expected {expected_fig_numbers}, got {actual_fig_numbers}")

    missing_copies = [fig.number for fig in figures.values() if not fig.copied]
    if missing_copies:
        errors.append(f"Missing copied image files: {missing_copies}")

    missing_insertions = [fig.number for fig in figures.values() if not fig.inserted]
    if missing_insertions:
        errors.append(f"Missing Markdown image insertions: {missing_insertions}")

    for fig in figures.values():
        alt = f"{fig.number} {fig.caption}".strip()
        if f"![{alt}](" not in chapter_markdown:
            errors.append(f"Missing Markdown image reference for {fig.number}")
        if re.search(rf"!\[{re.escape(alt)}\]\([^)]+\)\n\n{re.escape(alt)}", chapter_markdown) is None:
            errors.append(f"Missing visible caption for {fig.number}")

    bad_literal_patterns = ["data centersdata centers", "Open Access", "&lt;", "<math"]
    for pattern in bad_literal_patterns:
        if pattern in chapter_markdown:
            errors.append(f"Bad pattern remained in chapter Markdown: {pattern}")

    if re.search(r"^#+\s+References\s*$", chapter_markdown, flags=re.MULTILINE):
        errors.append("References heading remained in chapter Markdown")

    for number, markdown in section_markdown.items():
        match = re.fullmatch(rf"{chapter_number}\.(\d+)", number)
        if not match:
            continue
        own_section = match.group(1)
        for heading in re.finditer(rf"^##\s+{chapter_number}\.(\d+)\b", markdown, flags=re.MULTILINE):
            if heading.group(1) != own_section:
                errors.append(f"section_{number.replace('.', '_')}.md contains content from {chapter_number}.{heading.group(1)}")

    if not report_warnings:
        pass

    return errors


def figure_sort_key(figure: Figure) -> tuple[int, int]:
    match = re.search(r"(\d+)\.(\d+)", figure.number)
    if not match:
        return (9999, 9999)
    return (int(match.group(1)), int(match.group(2)))


def extract_chapter(epub_path: Path, chapter_number: int, output_dir: Path) -> ExtractionResult:
    with zipfile.ZipFile(epub_path, "r") as epub:
        opf_path = read_rootfile_path(epub)
        spine_paths = read_spine(epub, opf_path)
        chapter_file = find_chapter_file(epub, spine_paths, chapter_number)
        root = parse_xml_bytes(epub.read(chapter_file))

        chapter_title = find_chapter_title(root)
        chapter_title_count = count_chapter_titles(root)
        fulltext = find_fulltext(root)
        sections = direct_section1(fulltext)
        section1_numbers = collect_section_numbers(sections)

        figures = collect_figures(epub, chapter_file, fulltext, chapter_number)
        copy_figures(epub, figures, output_dir, chapter_number)

        chapter_renderer = MarkdownRenderer(figures, chapter_number, fulltext)
        chapter_blocks = [f"# {chapter_title}"]
        for section in sections:
            chapter_blocks.extend(chapter_renderer.render_section(section))
        chapter_markdown = render_markdown(chapter_blocks)

        section_markdown: dict[str, str] = {}
        section_stats: dict[str, dict] = {}
        for section in sections:
            number = section_number(section)
            if not number:
                continue
            section_figures = fresh_figures(figures)
            renderer = MarkdownRenderer(section_figures, chapter_number, section, fulltext)
            markdown = render_markdown(renderer.render_section(section))
            section_markdown[number] = markdown
            section_stats[number] = {
                "paragraphs": renderer.stats.paragraphs,
                "lists": renderer.stats.lists,
                "list_items": renderer.stats.list_items,
                "headings": renderer.stats.headings,
                "figures_inserted": renderer.stats.inserted_figures,
                "warnings": renderer.stats.warnings,
            }

        warnings = list(chapter_renderer.stats.warnings)
        for number, stats in section_stats.items():
            for warning in stats["warnings"]:
                warnings.append(f"section {number}: {warning}")

        errors = validate(
            chapter_number,
            chapter_title,
            chapter_title_count,
            section1_numbers,
            figures,
            chapter_markdown,
            section_markdown,
            warnings,
        )

        report = {
            "chapter": chapter_number,
            "source_epub": str(epub_path),
            "source_chapter_file": chapter_file,
            "chapter_title": chapter_title,
            "section1_numbers": section1_numbers,
            "skipped_blocks": [
                "Chapter metadata outside div.Fulltext",
                "License block after div.Fulltext sections",
                "Bibliography/References after div.Fulltext sections",
            ],
            "counts": {
                "section1": len(sections),
                "chapter_title_count": chapter_title_count,
                "headings_in_source": count_all_section_headings(fulltext),
                "headings_rendered": chapter_renderer.stats.headings,
                "paragraphs": chapter_renderer.stats.paragraphs,
                "lists": chapter_renderer.stats.lists,
                "list_items": chapter_renderer.stats.list_items,
                "math_formulas_in_source": count_fulltext_math(fulltext),
                "math_formulas_rendered": chapter_renderer.stats.formulas,
                "figures_total": len(figures),
                "figures_copied": sum(1 for fig in figures.values() if fig.copied),
                "figures_inserted": sum(1 for fig in figures.values() if fig.inserted),
            },
            "sections": section_stats,
            "figures": [
                {
                    "id": fig.fig_id,
                    "number": fig.number,
                    "caption": fig.caption,
                    "source": fig.epub_path,
                    "output_file": fig.output_file,
                    "markdown_path": fig.markdown_path,
                    "copied": fig.copied,
                    "inserted": fig.inserted,
                    "first_reference_found": fig.first_reference_found,
                }
                for fig in sorted(figures.values(), key=figure_sort_key)
            ],
            "warnings": warnings,
            "errors": errors,
        }

        return ExtractionResult(
            chapter_number=chapter_number,
            chapter_file=chapter_file,
            chapter_title=chapter_title,
            chapter_markdown=chapter_markdown,
            section_markdown=section_markdown,
            figures=figures,
            report=report,
            errors=errors,
            warnings=warnings,
        )


def available_chapters(epub_path: Path) -> list[int]:
    with zipfile.ZipFile(epub_path, "r") as epub:
        opf_path = read_rootfile_path(epub)
        spine_paths = read_spine(epub, opf_path)

    chapters: list[int] = []
    for path in spine_paths:
        match = re.search(r"_En_(\d+)_Chapter\.xhtml$", path)
        if match:
            chapters.append(int(match.group(1)))
    return chapters


def fresh_figures(figures: dict[str, Figure]) -> dict[str, Figure]:
    return {
        key: Figure(
            fig_id=value.fig_id,
            number=value.number,
            caption=value.caption,
            src=value.src,
            epub_path=value.epub_path,
            output_file=value.output_file,
            markdown_path=value.markdown_path,
            copied=value.copied,
        )
        for key, value in figures.items()
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract clean Markdown from a Springer EPUB chapter.")
    parser.add_argument("--epub", required=True, help="Path to the EPUB file")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--chapter", type=int, help="Chapter number to extract")
    target.add_argument("--all", action="store_true", help="Extract all numbered chapters in EPUB spine order")
    parser.add_argument("--out", default="build", help="Output directory")
    parser.set_defaults(strict=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when validation errors are found (default)",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Write reports but do not fail the command on validation errors",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    epub_path = Path(args.epub)
    output_dir = Path(args.out)

    if not epub_path.exists():
        print(f"EPUB not found: {epub_path}", file=sys.stderr)
        return 2

    chapter_numbers = available_chapters(epub_path) if args.all else [args.chapter]

    failures: list[tuple[int, list[str]]] = []
    summaries: list[dict] = []
    for chapter_number in chapter_numbers:
        assert chapter_number is not None
        try:
            result = extract_chapter(epub_path, chapter_number, output_dir)
            output_paths = write_outputs(
                output_dir,
                result.chapter_number,
                result.chapter_markdown,
                result.section_markdown,
                result.report,
            )
        except Exception as exc:
            print(f"Chapter {chapter_number} extraction failed: {exc}", file=sys.stderr)
            failures.append((chapter_number, [str(exc)]))
            continue

        summaries.append(
            {
                "chapter": result.chapter_number,
                "title": result.chapter_title,
                "chapter_file": output_paths["chapter"],
                "report": output_paths["report_md"],
                "sections": len(result.section_markdown),
                "figures": result.report["counts"]["figures_total"],
                "warnings": len(result.warnings),
                "errors": len(result.errors),
            }
        )

        print(f"Extracted chapter {result.chapter_number}: {result.chapter_title}")
        print(f"  Chapter file: {output_paths['chapter']}")
        print(f"  Report: {output_paths['report_md']}")
        print(
            "  Figures: "
            f"{result.report['counts']['figures_inserted']}/"
            f"{result.report['counts']['figures_total']} inserted"
        )
        if result.warnings:
            print(f"  Warnings: {len(result.warnings)}")
        if result.errors:
            print("  Validation errors:", file=sys.stderr)
            for error in result.errors:
                print(f"  - {error}", file=sys.stderr)
            failures.append((result.chapter_number, result.errors))

    if args.all:
        write_summary_reports(output_dir, summaries, failures)

    if failures and args.strict:
        return 1
    return 0


def write_summary_reports(output_dir: Path, summaries: list[dict], failures: list[tuple[int, list[str]]]) -> None:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "chapters": summaries,
        "failures": [{"chapter": chapter, "errors": errors} for chapter, errors in failures],
    }
    (report_dir / "all_chapters_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = ["# All Chapters Extraction Summary", ""]
    lines.append("| Chapter | Sections | Figures | Warnings | Errors |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for summary in summaries:
        lines.append(
            f"| {summary['chapter']} | {summary['sections']} | {summary['figures']} | "
            f"{summary['warnings']} | {summary['errors']} |"
        )

    lines.extend(["", "## Failures", ""])
    if failures:
        for chapter, errors in failures:
            lines.append(f"- Chapter {chapter}: {'; '.join(errors)}")
    else:
        lines.append("- None")
    lines.append("")

    (report_dir / "all_chapters_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
