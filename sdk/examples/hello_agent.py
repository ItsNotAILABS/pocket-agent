"""Any AI agent can run this against a local or remote POCKET host."""

import os
from pocket_sdk import Pocket

p = Pocket(base_url=os.environ.get("POCKET_URL", "http://127.0.0.1:8787"))
if os.environ.get("POCKET_PASSWORD"):
    print("login", p.login())
print("health", p.health())
print("identity", (p.identity() or {}).get("you_are"))
print("protocols", (p.protocols() or {}).get("count"))
