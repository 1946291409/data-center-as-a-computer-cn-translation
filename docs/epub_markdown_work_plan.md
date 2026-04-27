# EPUB Markdown Draft Rebuild Plan

## Summary

- Use the EPUB as the primary source and keep the PDF for manual reference only.
- Build clean English Markdown drafts before adding any translation automation.
- Start with chapter 5 as the quality gate.
- Keep generated output under `build/` and do not overwrite archived legacy attempts.

## Current Implementation Baseline

- `extract_epub_clean.py` is the active extractor.
- It reads EPUB metadata from `META-INF/container.xml` and `OEBPS/package.opf`, then resolves chapter XHTML through the EPUB spine.
- It parses XHTML structurally with the Python standard library instead of cutting HTML with regex.
- It outputs chapter-level and second-level-section Markdown files, chapter images, and strict validation reports.

## Formatting Rules

- English source drafts are not indented.
- Chinese translated prose paragraphs should use two full-width spaces at the beginning: `　　`.
- Headings, lists, image links, captions, and math are not indented.
- Preserve original paragraph boundaries; do not merge or split prose paragraphs during extraction.
- Preserve citations such as `[13]`, Markdown image links, figure numbers, and math expressions.

## Image Handling

- Keep image filenames in the `chapter_X_fig_Y_English_caption.ext` style.
- Insert each image immediately after the first paragraph that references it with `Figure X.Y` or `Fig. X.Y`.
- If one paragraph first references multiple images, insert them in reference order after that paragraph.
- Preserve visible figure captions below image links.
- Translate visible captions later in the Chinese output, but keep image paths stable.

## Validation Rules

- Strict mode is the default.
- Chapter 5 validation requires one chapter title, section numbers `5.1` through `5.5`, and 30 figures from `Fig. 5.1` through `Fig. 5.30`.
- Every figure must have a copied image file, a Markdown image reference, and a visible caption.
- Reject known bad extraction artifacts such as duplicated Tier lists, `data centersdata centers`, `Open Access`, raw `<math`, and unescaped `&lt;`.
- Section files must not include content from the next second-level section.

## Next Steps

- Review the chapter 5 output manually.
- If the chapter 5 format is accepted, extend the CLI with an `--all` mode for the full book.
- Add a separate translation client that reads section Markdown files, injects a termbase subset, and calls the configured ModelScope endpoint.
- Keep the translator resumable, stream-safe, and cache final responses before generating Chinese Markdown.
