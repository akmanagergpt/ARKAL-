# Local model runtime options for staged generation

ARKALI is not tied to Ollama. `scripts/run_staged_generation.py` supports two
transport families:

```text
--runtime ollama
--runtime openai-compatible --endpoint http://127.0.0.1:PORT
```

The second option uses the existing `OpenAICompatibleAdapter`, always requires
a loopback endpoint, probes `/v1/models`, and generates through
`/v1/chat/completions`. It forwards the stage's output-token bound and requests
JSON mode. A runtime is never reported available unless its real probe passes.

## Free local alternatives

All options below can run local/open-weight models without per-token API fees.
Model licenses still apply individually.

| Runtime | Typical endpoint | Notes |
|---|---|---|
| llama.cpp `llama-server` | `http://127.0.0.1:8080` | Lightweight native server; OpenAI-compatible chat endpoint; strong GGUF/CPU+GPU support. |
| LM Studio / `llmster` | `http://127.0.0.1:1234` | Windows-friendly GUI or headless local server; OpenAI-compatible endpoints. |
| LocalAI | `http://127.0.0.1:8080` | Open-source multi-backend runtime exposing OpenAI and Anthropic APIs. |
| Jan | `http://127.0.0.1:1337` (Desktop) or `:6767` (CLI) | Open-source local-first desktop/CLI powered by llama.cpp; OpenAI-compatible server. |
| vLLM | `http://127.0.0.1:8000` | OpenAI-compatible high-throughput serving; best suited to Linux/WSL and larger GPU deployments. |

Official documentation:

- llama.cpp: https://github.com/ggml-org/llama.cpp
- LM Studio server: https://lmstudio.ai/docs/developer/core/server
- LocalAI: https://localai.io/docs/
- Jan local API: https://jan.ai/docs/api-server
- vLLM OpenAI-compatible server: https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/

## Examples

LM Studio:

```powershell
python scripts/run_staged_generation.py `
  --candidate-id golden-work-XYZ `
  --runtime openai-compatible `
  --endpoint http://127.0.0.1:1234 `
  --model <model-id-returned-by-v1-models> `
  --goal-file scripts/goals/student_fee_management.txt
```

llama.cpp / LocalAI use the same command with their endpoint. Runtime fallback
is deliberately explicit rather than automatic: silently switching models in
the middle of one candidate would destroy reproducibility and provenance. A
new runtime/model combination therefore always receives a new candidate id.

## Acceptance

After `STAGED_GENERATION_PASS`, run:

```powershell
python scripts/run_golden_acceptance.py --candidate-id golden-work-XYZ
```

This is the only command allowed to emit `GOLDEN_ACCEPTANCE_PASS`. Omitting the
browser with `--skip-browser` always produces `GOLDEN_ACCEPTANCE_INCOMPLETE`,
never PASS.
