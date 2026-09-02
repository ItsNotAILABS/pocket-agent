# Agent Pocket Deploy Handoff

Canonical route:

```text
https://beta.pocketnova.app/agents/
```

## Give this to Claude / Cloud / Cloudflare deploy agent

```text
Deploy Agent Pocket from ItsNotAILABS/pocket-agent.
Mount web/agent-pocket-console/index.html under https://beta.pocketnova.app/agents/.
Expose sdk/pocket-agent-client.js under the beta SDK path.
Wire POST /agents/tasks for agent task packet intake.
Wire POST /agents/production-claims for receipt-backed production claims.
Wire POST /agents/data-exports for operator-approved data export requests.
Wire POST /agents/payment-executions for operator-approved provider payment packets.
Wire POST /agents/wallet-executions for operator-approved provider wallet packets.
Do not infer execution state from chat text.
Do not accept raw card data, CVV/CVC, private keys, seed phrases, raw secrets, or hidden credentials.
```

## Added files

```text
web/agent-pocket-console/index.html
sdk/pocket-agent-client.js
deploy/cloudflare/agent-pocket-handoff.json
scripts/validate_agent_pocket_handoff.py
```

## Validate

```bash
python scripts/validate_agent_pocket_handoff.py
```

Receipt:

```text
dist/agent-pocket-handoff/validation-receipt.json
```

## Execution posture

Agent Pocket can accept task packets and restricted action requests. The deploy target must route restricted actions through explicit operator approval and receipt creation. Production, data export, payment, and wallet states must be read from receipts or provider references, never inferred from conversation text.
