---
name: economy-wallets
description: POCKET economic domain — operator wallets, digital twin wallets, escrow
---

# Economy

```http
GET  /v1/economy
GET  /v1/economy/twins
POST /v1/economy/transfer {"from":"wallet_operator","to":"twin_aria","amount":10}
POST /v1/economy/escrow   {"amount":40,"purpose":"rah"}
```

Paper-first. Parallax AI-wallet export: `GET /v1/economy/parallax/wallets`.
