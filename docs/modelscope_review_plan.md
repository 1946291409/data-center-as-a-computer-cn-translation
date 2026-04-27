# ModelScope Review Plan

## Model Split

- Translation model: `Qwen/Qwen3-32B`
- Review model: `Qwen/Qwen3-235B-A22B`
- Fallback model: `Qwen/Qwen3-32B`

## Review Strategy

Run local audit first. Only send high-risk fragments to `Qwen/Qwen3-235B-A22B`.

High-risk fragments include:

- Numbers, units, formulas, citations, and image/table references.
- Power, energy, cooling, reliability, security, carbon, SLO, PUE, latency, encryption, and fault-related paragraphs.
- Termbase conflicts that cannot be resolved by local rules.

## Outputs

- `review_reports/chapter_X/audit.md`
- `review_reports/chapter_X/issues.jsonl`
- `review_reports/chapter_X/model_review.jsonl`
- `reviewed_content/chapter_X/section_X_Y.md`

## Rules

- Do not overwrite `translated_content`.
- Apply low-risk mechanical fixes only to `reviewed_content`.
- Model review suggestions are advisory until manually accepted.
