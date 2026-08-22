# Security Policy — POCKET Agent Alpha

POCKET Agent is an execution system. Its security posture depends on where an action runs, what credentials are available, and which filesystem/network capabilities are granted.

## Security boundary

### Local execution

Commands executed outside a capsule may run with the current operating-system user's permissions. Treat the active repository and machine as trusted operator space.

### Capsule execution

Use WASM capsules or another restricted runtime for untrusted evaluation, parallel isolation, or tasks that should not inherit normal host permissions. Capsule use reduces exposure; it does not automatically authorize access back to host resources.

### POCKET family execution

Cross-repo requests should use `pocket.family.v1`. The envelope carries principal, tenant, session, agent and request identity. POCKET Host is responsible for authenticating and authorizing the request before privileged execution is delegated to POCKET Agent.

## Secrets

- Never commit provider tokens, POCKET keys, cloud credentials, passwords or signing secrets.
- Do not include secrets in execution receipts, agent messages, diagnostics or bug reports.
- Prefer environment variables, OS key stores, or the upstream POCKET secret boundary.
- Redact command output before persistence when it may contain credentials.

## Receipts and privacy

`pocket.execution-receipt.v1` is designed for operational evidence: action, status, timestamps, scope, runtime metadata and digests. It must not contain private chain-of-thought, hidden prompts, raw secrets or unnecessary customer content.

## Reporting a vulnerability

Do not publish exploitable security issues as a public GitHub issue. Contact the repository maintainers privately through the organization’s available security/contact channel and include:

- affected version/commit;
- reproduction conditions;
- impact and required privileges;
- minimal proof-of-concept;
- suggested mitigation if known.

## Alpha non-goals

The Alpha channel does not claim formal penetration testing, SOC 2, ISO 27001, FedRAMP, HIPAA eligibility, or third-party security certification. Such claims require independent evidence and deployment-specific controls.
