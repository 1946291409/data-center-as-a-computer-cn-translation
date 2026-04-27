# ModelScope Resume and Quota Workflow

## First Run

Set the token only in the current shell:

```powershell
$env:MODELSCOPE_SDK_TOKEN = "your-token"
```

Estimate cost before making API calls:

```powershell
python translate_modelscope.py --chapter 5 --estimate
```

Start or resume translation:

```powershell
python translate_modelscope.py --chapter 5 --resume
```

## If Quota Runs Out

The script classifies quota-related `429` errors as `quota_exhausted`, stops the chapter, and writes:

- `translation_state/modelscope/chapter_5/state.json`
- `translation_state/modelscope/chapter_5/chunks.jsonl`
- `translation_state/modelscope/chapter_5/raw_usage.jsonl`

After the daily quota refresh, run the same command again:

```powershell
$env:MODELSCOPE_SDK_TOKEN = "your-token"
python translate_modelscope.py --chapter 5 --resume
```

Completed chunks are skipped by source hash. Interrupted `.part` chunks are not treated as complete and will be retried.

## Manual Controls

```powershell
python translate_modelscope.py --status
python translate_modelscope.py --section 5.3 --resume
python translate_modelscope.py --section 5.3 --force --resume
python translate_modelscope.py --chapter 5 --resume --no-thinking
python translate_modelscope.py --smoke-test
```

## Error States

- `auth_error`: missing or invalid token. Set `MODELSCOPE_SDK_TOKEN` and rerun.
- `bad_request`: model/request/context issue. Inspect `state.json`.
- `quota_exhausted`: daily quota or billing limit reached. Retry after quota refresh.
- `rate_limited`: request frequency exceeded. Script retries with backoff.
- `paused_retryable_error`: network/server overload persisted beyond retries. Rerun `--resume`.
- `validation_error`: translated Markdown failed structural checks; inspect the chunk output and prompt.
