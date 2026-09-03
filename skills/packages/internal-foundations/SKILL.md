# Internal AI foundations

POCKET computational AI and math are **internal**. Do not call a third-party model API for proofs, hashes, world facts, or identity.

## Use

```http
GET /v1/foundations
POST /v1/skills/run
{"skill":"foundations_map"}
POST /v1/internal-models/express
{"id":"ghost","goal":"hash this receipt"}
```

Math models: `ghost` · `logic` · `pattern`  
Self: `identity` · `heuristic`  
World: `world` · `auro` · `guppy`
