---
name: rah-auto
description: Use Recursive Agent Harnesses for large independent parallel work
---

# RAH

Agents should auto-use RAH when tasks audit/scan **every** module/endpoint or need parallel independent slices.

```http
POST /v1/rah/plan  {"task":"..."}
POST /v1/rah/run   {"task":"...","max_leaves":8}
POST /v1/rah/score {"task":"..."}
```

Host auto-escalates when `POCKET_RAH_AUTO=1` (default). User need not say "RAH".
