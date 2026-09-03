---
name: screen-body
description: Inhabit the live Pocket desktop. See, touch, type, click named buttons through SCREEN-KERNEL/1.1.
---

# Screen body

The agent **is** the pointer on the operator PC. Same verbs as PhoneAI Portal.

```python
from pocket_sdk import Pocket
p = Pocket()          # http://127.0.0.1:8787
p.embody("coder")
p.screen_see()
p.screen_touch("tap", nx=0.5, ny=0.4)
p.screen_type("notes", submit=False)
p.screen_click("Save")
```

Host: `POST /v1/screen/embody` · MCP `screen_embody`. Stream: `pocket.stream.v1`.
