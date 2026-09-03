# pocket-sdk

Downloadable Python SDK for any AI agent or app talking to a **POCKET host**.

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/sdk.sh | sh
# or: pip install -e /path/to/pocket-agent/sdk
```

```python
from pocket_sdk import Pocket

p = Pocket(base_url="http://127.0.0.1:8787")  # or POCKET_URL
p.login("pocket", "…")  # or POCKET_TOKEN
print(p.health())
print(p.protocols())
sid = p.create_session(mode="plan", title="sdk")
print(p.send_message(sid, "Who are you?"))
print(p.economy())
print(p.rah_plan("Audit every API endpoint for missing auth"))
print(p.agents_tools())       # full MCP tools + 20 uses manifest
print(p.engine_uses())
print(p.engine_use(prompt="research multi-agent hosts"))
print(p.mail_inbox("assist"))
print(p.genetic_run("hash and plan"))
print(p.model_build(kind="formula", formula="x*phi", model_id="user-roi"))
p.embody("sdk")
p.screen_see()
```

Also see the **Phone Agent app** (`pocket-phone-agent`) — separate agentic phone on port **8795** using a dedicated internal SDK against the same host API.

Env: `POCKET_URL`, `POCKET_TOKEN`, `POCKET_USER`, `POCKET_PASSWORD`.
