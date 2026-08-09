# Recursive Language Model (RLM) control plane

## Ideas

1. **Prompt as a variable** — large context is assigned, sliced, and passed by reference in code, not dumped into every call.  
2. **Tools as functions** — shell, files, capsules, subagents are callables in a persistent REPL.  
3. **Subagents as `rlm(...)`** — child agents return structured results into the parent program.  

## Example

```python
ctx = load_context("repo_summary.md")
parts = split_by_module(ctx)
results = rlm_map([f"review {p}" for p in parts], max_workers=4)
save("review.md", synthesize(results))
```

When scale requires **full harnesses** (not bare calls), the runtime escalates to **RAH**.
