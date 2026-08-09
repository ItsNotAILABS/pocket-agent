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
print(p.capsule_reasons())
```

Env: `POCKET_URL`, `POCKET_TOKEN`, `POCKET_USER`, `POCKET_PASSWORD`.
