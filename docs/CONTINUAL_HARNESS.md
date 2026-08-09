# Continual Harness

Durable state local to the session/project by default:

- supplemental prompts  
- memories  
- skill descriptions  
- reusable subagent specifications  

## `/refine`

Reviews trajectory and applies **small, evidence-backed** updates.

- **Never** rewrites the immutable base system prompt  
- Snapshots support **rollback**  

```python
from pocket_agent.harness import Harness

h = Harness(project="my-app")
h.refine(evidence="pytest green after auth fix", notes="prefer integration tests")
h.rollback()  # last snapshot
```
