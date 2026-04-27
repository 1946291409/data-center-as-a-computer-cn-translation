# ModelScope API Interface

The active translation target is Alibaba ModelScope API, not Ollama. Keep API access separate from extraction and terminology work. Do not store the real ModelScope token in project files; use `MODELSCOPE_SDK_TOKEN`.

## Sample Config

Start from `configs/modelscope.example.json`.

Important fields:

- `base_url`: `https://api-inference.modelscope.cn/v1`
- `api_key_env`: `MODELSCOPE_SDK_TOKEN`
- `model`: `Qwen/Qwen3-32B`
- `termbase_csv`: `terminology/terms.csv`
- `termbase_json`: `terminology/terms.json`
- `stream`: enabled
- `extra_body.enable_thinking`: enabled

## Environment Setup

```powershell
$env:MODELSCOPE_SDK_TOKEN = "replace-with-your-token"
```

## OpenAI-Compatible Smoke Test

```powershell
@'
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api-inference.modelscope.cn/v1",
    api_key=os.environ["MODELSCOPE_SDK_TOKEN"],
)

response = client.chat.completions.create(
    model="Qwen/Qwen3-32B",
    messages=[
        {"role": "user", "content": "9.9和9.11谁大"}
    ],
    stream=True,
    extra_body={
        "enable_thinking": True,
        "thinking_budget": 4096,
    },
)

done_thinking = False
for chunk in response:
    if not chunk.choices:
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
PY
'@ | python -
```

## Integration Notes

- Use `prompts/modelscope_translation_system.md` and `prompts/modelscope_translation_user_template.md` for translation requests.
- Load a compact termbase subset into each translation request.
- Preserve Markdown image filenames; translated output maps `../../images/...` to `../../build/images/...`.
- Apply two full-width spaces only to translated Chinese prose paragraphs.
- Collect `reasoning_content` separately from `content`; only `content` becomes translated Markdown.
- See `docs/modelscope_resume_workflow.md` for quota exhaustion and manual restart steps.
