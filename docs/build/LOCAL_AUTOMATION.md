# Local resilient automation

`scripts/automation/arkali_automation.py` is a local control wrapper, not an
acceptance authority. Run it only with the canonical WSL interpreter:

```text
/home/lenovo/.venvs/arkali/bin/python scripts/automation/arkali_automation.py plan.json
```

Codex is the sole implementation actor and repository writer. The driver holds
an OS advisory lock for the entire run, executes packets serially, and stops if
another writer holds that lock. Local Qwen `qwen2.5-coder:14b` receives only a
bounded text prompt through Ollama and returns optional analysis, test
classification and suggestions. It receives no filesystem tools and has no
gate, acceptance or Git interface. Qwen failure is recorded as
`NOT_CONFIGURED`; Codex remains authoritative.

Quota-shaped Codex failures retry with bounded exponential backoff. Other
failures stop immediately. `HUMAN_GATE_REQUIRED`, `CANONICAL_AMBIGUITY`,
`BLOCKER_OPEN` and `HIGH_OPEN` are terminal. A packet may name a machine gate,
but it runs only after Codex succeeds and every declared target/full-regression
command exits zero. The plan must omit a gate until the final candidate is
complete and governance permits the one submission.

Commands containing push/pull/fetch, PR creation, deploy, network clients or
credential/token material are refused before execution. The subprocess
environment forwards no credential variables. The driver never installs a
dependency, contacts an external provider, deploys, pushes or opens a PR.
Journal records are local and ignored under `.arkali-automation/`.
