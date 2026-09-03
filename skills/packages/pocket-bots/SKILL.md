# POCKET Bots

Grok-Bot-style teammates **inside POCKET**, running on **pocket-agent**.

Each bot has a name, a job, its own computer (`~/.pocket/bots/<id>/computer`), a thread, and optional always-on pulse.

```http
GET /bots
GET /v1/bots
POST /v1/bots/hire
{"prompt":"I need a bot that handles sales follow-ups"}
POST /v1/bots/{id}/message
{"text":"Draft tonight's checklist"}
POST /v1/skills/run
{"skill":"bots_hire","prompt":"ops bot for invoices"}
```

Runtime: pocket-agent harness + internal models. Not a third-party bot cloud.
