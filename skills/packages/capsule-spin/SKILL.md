---
name: capsule-spin
description: Spin a POCKET WASM multi-sandbox capsule for isolated agent work
---

# Capsule spin

When the user or task needs isolation (untrusted code, tests, GPU, parallel RAH leaf), spin a capsule.

## Run (host)

```http
POST /v1/skills/run
{"skill":"capsule_allocate","prompt":"untrusted eval","params":{"reason":"untrusted_eval","tier":"512MB","enableWebGPU":false}}
```

## CLI

```bash
pocket-agent capsule spin --reason untrusted_eval
pocket-agent capsule reasons
```

## Python SDK

```python
from pocket_sdk import Pocket
p = Pocket()
p.login()
print(p.capsule_allocate(reason="sandbox_tests"))
```

## Reasons (20)

See skill `capsule_reasons` or `docs/WASM_CAPSULES.md`. Prefer capsules over raw host shell for guest code.
