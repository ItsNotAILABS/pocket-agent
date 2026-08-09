"""Plug-n-play POCKET host client (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class Pocket:
    """HTTP client for POCKET host — sessions, protocols, economy, RAH, capsules."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("POCKET_URL") or "http://127.0.0.1:8787").rstrip("/")
        self.token = token or os.environ.get("POCKET_TOKEN") or ""
        self.timeout = timeout
        self.user = os.environ.get("POCKET_USER") or "pocket"

    def _headers(self, *, json_body: bool = True) -> Dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": f"pocket-sdk/{__import__('pocket_sdk').__version__}"}
        if json_body:
            h["Content-Type"] = "application/json"
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
            h["X-Pocket-Token"] = self.token
        if self.user:
            h["X-Pocket-User"] = self.user
        h["X-Pocket-Device"] = "sdk"
        return h

    def request(self, method: str, path: str, body: Any = None) -> Any:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        data = None
        headers = self._headers(json_body=body is not None)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {"ok": True, "status": resp.status}
                try:
                    return json.loads(raw)
                except Exception:
                    return {"ok": True, "text": raw[:5000]}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:2000]
            try:
                return json.loads(err)
            except Exception:
                return {"ok": False, "error": err or str(e), "status": e.code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        return self.request("POST", path, body or {})

    # --- core ---
    def health(self) -> Any:
        return self.get("/health")

    def identity(self) -> Any:
        return self.get("/v1/identity")

    def protocols(self) -> Any:
        return self.get("/v1/protocols")

    def protocols_status(self) -> Any:
        return self.get("/v1/protocols/status")

    def login(self, username: str = "", password: str = "") -> Any:
        u = username or os.environ.get("POCKET_USER") or "pocket"
        p = password or os.environ.get("POCKET_PASSWORD") or ""
        r = self.post("/v1/auth/login", {"username": u, "user": u, "password": p})
        tok = (r or {}).get("token") or ""
        if tok:
            self.token = tok
            self.user = u
        return r

    def create_session(self, *, mode: str = "plan", title: str = "sdk") -> str:
        r = self.post("/v1/sessions", {"mode": mode, "title": title, "workspace": "workspace"})
        return str((r or {}).get("id") or "")

    def send_message(self, session_id: str, text: str, **extra: Any) -> Any:
        body = {"text": text, "workspace": extra.get("workspace") or "workspace", "interrupt": True}
        body.update({k: v for k, v in extra.items() if k != "workspace"})
        return self.post(f"/v1/sessions/{session_id}/messages", body)

    def get_session(self, session_id: str) -> Any:
        return self.get(f"/v1/sessions/{session_id}")

    # --- economy ---
    def economy(self) -> Any:
        return self.get("/v1/economy")

    def twins(self) -> Any:
        return self.get("/v1/economy/twins")

    def transfer(self, *, to: str, amount: int, from_id: str = "wallet_operator", memo: str = "") -> Any:
        return self.post("/v1/economy/transfer", {"from": from_id, "to": to, "amount": amount, "memo": memo})

    # --- RAH ---
    def rah_plan(self, task: str, **kw: Any) -> Any:
        return self.post("/v1/rah/plan", {"task": task, **kw})

    def rah_run(self, task: str, **kw: Any) -> Any:
        return self.post("/v1/rah/run", {"task": task, **kw})

    def rah_score(self, task: str, mode: str = "plan") -> Any:
        return self.post("/v1/rah/score", {"task": task, "mode": mode})

    # --- capsules ---
    def capsule_reasons(self) -> Any:
        # via platform skill if host has it
        r = self.post("/v1/skills/run", {"skill": "capsule_reasons", "prompt": ""})
        if (r or {}).get("ok") is False and "not found" in str(r).lower():
            return {"ok": True, "note": "use pocket-agent capsule reasons offline"}
        return r

    def capsule_allocate(self, *, reason: str = "untrusted_eval", tier: str = "512MB", webgpu: bool = False) -> Any:
        return self.post(
            "/v1/skills/run",
            {
                "skill": "capsule_allocate",
                "prompt": reason,
                "params": {"reason": reason, "tier": tier, "enableWebGPU": webgpu},
            },
        )

    # --- platform ---
    def skills_run(self, skill: str, prompt: str = "", params: Optional[Dict[str, Any]] = None) -> Any:
        return self.post("/v1/skills/run", {"skill": skill, "prompt": prompt, "params": params or {}})

    def platform_map(self) -> Any:
        return self.skills_run("platform_map")

    def chat(self, messages: List[Dict[str, str]], agent: str = "planner") -> Any:
        return self.post("/v1/ai/chat", {"messages": messages, "agent": agent})
