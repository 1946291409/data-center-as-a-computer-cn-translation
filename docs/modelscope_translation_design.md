# ModelScope Translation Design

## Goal

Translate cleaned English Markdown drafts through ModelScope while keeping terminology, formatting, citations, math, image links, and visible captions stable.

## Request Flow

1. Read one Markdown section file from `build/original_text/...`.
2. Build a termbase subset:
   - Always include `terminology/terms.json` priority terms.
   - Add entries from `terminology/terms.csv` whose `source` appears in the Markdown fragment.
   - Prefer `approved` terms over `draft` terms when duplicates exist.
   - Cap the injected termbase at `max_termbase_entries_per_request`.
3. Render prompts:
   - System prompt: `prompts/modelscope_translation_system.md`
   - User template: `prompts/modelscope_translation_user_template.md`
4. Call `https://api-inference.modelscope.cn/v1/chat/completions` with OpenAI-compatible client settings.
5. Stream output:
   - Treat `delta.reasoning_content` as model reasoning and do not write it into translated Markdown.
   - Append only `delta.content` to the translated output.
6. Write output under `translated_content/chapter_X/section_X_Y.md`.

## Thinking Mode

Use Qwen3 thinking mode for first-pass translation because it can help resolve terminology and long technical sentences.

Default:

- `enable_thinking: true`
- `thinking_budget: 4096`
- `save_reasoning_trace: false`

If translation becomes slow or verbose, lower `thinking_budget` or disable thinking for simple sections.

## Prompt and Termbase Contract

- The model must treat the injected termbase as binding.
- The model must not emit a term table or explain terminology choices.
- The final answer should contain only translated Markdown.
- The translation client should validate that image paths, citations, and heading numbers still match the source.

## Validation After Translation

Minimum checks per translated section:

- Same heading numbers as source.
- Same citation markers, such as `[13]`.
- Same Markdown image filenames, with source `../../images/...` mapped to translated output `../../build/images/...`.
- Same number of visible image captions.
- No fenced wrapper around the entire output.
- Chinese prose paragraphs begin with `　　`; headings/lists/images/captions do not.

## Quota and Resume Behavior

- Store progress under `translation_state/modelscope/chapter_X/`.
- Treat quota-related `429` responses as `quota_exhausted` and stop the chapter immediately.
- Treat frequency-related `429`, `500`, `503`, and network interruptions as retryable with backoff.
- Never mark `.part` files as complete; rerun them on `--resume`.
- Use `python translate_modelscope.py --status` to inspect progress.
- After the daily quota refresh, rerun `python translate_modelscope.py --chapter 5 --resume`.

## Second-Phase Review Models

- Use `Qwen/Qwen3-32B` for translation and low-cost fallback.
- Use `Qwen/Qwen3-235B-A22B` as the default semantic review model.
- Keep review model calls limited to high-risk fragments selected by local audit.
- Review outputs are advisory reports and must not directly overwrite `translated_content`.
