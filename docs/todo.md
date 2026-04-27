# TODO

## Working Rules

- Current delivery lane uses:
  - local audit
  - strong-model review
  - manual selection of high-confidence fixes
  - fixes applied only to `reviewed_content/`
- Do not promote the arbiter to full automatic chapter-wide writeback until its patch granularity and conflict handling are verified.
- Even when the same base model is used for `review_model` and `arbiter_model`, keep the roles isolated:
  - different prompts
  - different input bundles
  - different output schemas
  - no reuse of review judgments as implicit approval

## Current Delivery Lane

- [x] Finish confirmed-fix application for remaining chapters that still only have local audit results.
- [x] Decide whether chapters `1/2/4/7/11` need any semantic review beyond local audit.
- [x] Generate a final chapter-by-chapter review status summary for all `reviewed_content`.
- [ ] Decide final publishing directory structure after second-pass review is complete.

## Deferred Architecture Work

- [ ] Refine `review_arbiter.py` from issue-level natural-language replacement to patch-level structured edits.
- [ ] Add conflict resolution when multiple accepted issues target the same paragraph or list block.
- [ ] Add chapter-level arbiter regression tests before enabling broader automatic application.
- [ ] Revisit whether `arbiter_model` should remain `Qwen/Qwen3-235B-A22B` or switch to a different stronger review model.
- [ ] Add a separate “challenge” reviewer role if same-model review/arbitration still shows confirmation bias.

## Deferred Quality Work

- [ ] Expand termbase beyond chapter 5 seed terms and normalize chapter 12 bibliography/title conventions.
- [ ] Improve number-diff audit to distinguish true numeric loss from Chinese formatting changes.
- [ ] Improve formula audit so it focuses on semantic corruption, not typography preferences.
- [ ] Improve chapter 12 bibliography/item splitting rules so review copies do not need manual cleanup.

## Notes

- Preferred sequence:
  1. Ship a solid reviewed draft.
  2. Freeze content.
  3. Re-open deferred automation and optimization tasks from this file.
