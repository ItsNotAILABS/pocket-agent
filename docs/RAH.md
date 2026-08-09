# Recursive Agent Harnesses (RAH)

**Recursive unit = full agent harness** (context + tools + plan + spawn),  
not a bare model call (that is classic RLM territory).

## Flow

1. Parent receives large task  
2. Host scores fit (`score_rah_fit`) — **auto** when independent + high-value  
3. Parent materializes orchestration plan/script  
4. Runtime fans out leaf harnesses in parallel  
5. Intermediate state on filesystem `~/.pocket/rah/<run_id>/`  
6. Verify + synthesize  

## When agents auto-use RAH

- Audit/scan **every** endpoint/module  
- Large migration/port across codebase  
- 4+ independent bullet work items  
- Explicit “parallel / fan-out” language  

Users do **not** need to say “RAH”.

## CLI

```bash
pocket-agent run "Audit every API endpoint for missing auth"
# if host present: uses POCKET auto-RAH; else local rlm_map simulation
```
