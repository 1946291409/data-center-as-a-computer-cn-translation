# Terminology Guide

## Purpose

The termbase is the translation contract for this project. It prevents the model from changing technical terms across chapters.

## Files

- `terminology/terms.csv`: human-editable master table.
- `terminology/terms.json`: machine-readable copy for later translation tooling.

## Status Values

- `draft`: initial assistant proposal; needs human review.
- `approved`: user-approved term; translator must follow it.
- `blocked`: do not use this translation.

## Columns

- `source`: English term or abbreviation.
- `target`: preferred Chinese rendering.
- `category`: domain group, such as `power`, `cooling`, `operations`, `construction`, `abbreviation`.
- `status`: review state.
- `first_use`: initial source scope used for this proposal.
- `notes`: usage rule or warning.

## Translation Rules

- Keep company names, product names, paper names, and standards names in English unless the termbase explicitly says otherwise.
- For abbreviations, first use should normally be `中文全称（ABBR）`; later uses can keep the abbreviation if the context is clear.
- Preserve `WSC`, `UPS`, `PDU`, `CRAC`, `CDU`, `SLO`, `PUE`, and similar abbreviations when they are the most natural technical form.
- Do not force overly localized translations for standards or named frameworks, such as `Uptime Institute`, `TIA-942`, and `Open Compute`.
- When a term has uncertainty, keep `status=draft` and explain the uncertainty in `notes`.

## Review Workflow

1. Review `draft` entries by chapter.
2. Change accepted entries to `approved`.
3. Add project-specific preferred renderings when the model output drifts.
4. Before batch translation, generate a chapter-specific subset from this termbase.
