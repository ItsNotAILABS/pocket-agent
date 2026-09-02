#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy" / "cloudflare" / "agent-pocket-handoff.json"
WEB = ROOT / "web" / "agent-pocket-console" / "index.html"
SDK = ROOT / "sdk" / "pocket-agent-client.js"
OUT = ROOT / "dist" / "agent-pocket-handoff" / "validation-receipt.json"
REQUIRED_ENDPOINTS = {"/agents/tasks", "/agents/production-claims", "/agents/data-exports", "/agents/payment-executions", "/agents/wallet-executions"}


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    web = WEB.read_text(encoding="utf-8")
    sdk = SDK.read_text(encoding="utf-8")
    endpoints = {item["path"] for item in manifest.get("api_contracts", [])}
    checks = [
        {"check": "canonical_route", "ok": manifest.get("canonical_beta_url") == "https://beta.pocketnova.app/agents/"},
        {"check": "web_console", "ok": WEB.exists() and "Agent Pocket Console" in web},
        {"check": "sdk_restricted_methods", "ok": all(term in sdk for term in ["claimProduction", "requestExport", "requestPaymentExecution", "requestWalletExecution"])},
        {"check": "operator_approval_enforced", "ok": "requireApproval" in sdk and "operator_approval" in sdk},
        {"check": "sensitive_fields_blocked", "ok": "forbidSensitive" in sdk and "private_key" in sdk and "seed phrase" in sdk},
        {"check": "all_endpoints", "ok": REQUIRED_ENDPOINTS.issubset(endpoints)},
        {"check": "claude_cloud_prompt", "ok": "deployment_prompt_for_claude_or_cloud" in manifest},
    ]
    receipt = {
        "schema": "pocket.agent_handoff.validation_receipt.v1",
        "ok": all(c["ok"] for c in checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "artifacts": [str(MANIFEST.relative_to(ROOT)), str(WEB.relative_to(ROOT)), str(SDK.relative_to(ROOT))],
    }
    receipt["hash"] = digest(receipt)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
