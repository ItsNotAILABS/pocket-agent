export class AgentPocketClient {
  constructor(options = {}) {
    this.baseUrl = (options.baseUrl || 'https://beta.pocketnova.app').replace(/\/$/, '');
    this.token = options.token || null;
  }

  headers() {
    const headers = { 'content-type': 'application/json' };
    if (this.token) headers.authorization = `Bearer ${this.token}`;
    return headers;
  }

  async submitTask(task) {
    const packet = await this.localTaskPacket(task);
    return this.post('/agents/tasks', packet);
  }

  async claimProduction(claim) {
    requireApproval(claim);
    requireFields(claim, ['claim_id', 'deploy_target', 'verification_evidence']);
    return this.post('/agents/production-claims', claim);
  }

  async requestExport(exportRequest) {
    requireApproval(exportRequest);
    requireFields(exportRequest, ['export_id', 'format', 'scope']);
    return this.post('/agents/data-exports', exportRequest);
  }

  async requestPaymentExecution(payment) {
    requireApproval(payment);
    requireFields(payment, ['payment_id', 'provider_ref', 'amount', 'currency']);
    forbidSensitive(payment);
    return this.post('/agents/payment-executions', payment);
  }

  async requestWalletExecution(walletAction) {
    requireApproval(walletAction);
    requireFields(walletAction, ['wallet_action_id', 'provider_ref', 'chain', 'action']);
    forbidSensitive(walletAction);
    return this.post('/agents/wallet-executions', walletAction);
  }

  async post(path, body) {
    const res = await fetch(`${this.baseUrl}${path}`, { method: 'POST', headers: this.headers(), body: JSON.stringify(body) });
    const text = await res.text();
    const payload = text ? JSON.parse(text) : {};
    if (!res.ok) throw Object.assign(new Error(`Agent Pocket request failed: ${res.status}`), { status: res.status, payload });
    return payload;
  }

  async localTaskPacket(task) {
    requireFields(task, ['task_id', 'type', 'title', 'instructions']);
    const payload = {
      schema: 'pocket.agent.task_packet.v1',
      created_at: new Date().toISOString(),
      operator_approval: false,
      expected_outputs: ['artifact', 'receipt'],
      ...task,
      execution_status: 'not_executed_locally'
    };
    payload.hash = await digest(payload);
    return payload;
  }
}

function requireApproval(value) {
  if (!value || value.operator_approval !== true) throw new Error('Operator approval is required for this action.');
}

function requireFields(value, fields) {
  const missing = fields.filter(field => value?.[field] === undefined || value?.[field] === null || value?.[field] === '');
  if (missing.length) throw new Error(`Missing required fields: ${missing.join(', ')}`);
}

function forbidSensitive(value) {
  const text = stableStringify(value).toLowerCase();
  const blocked = ['private_key', 'seed phrase', 'mnemonic', 'cvv', 'cvc', 'raw_card', 'pan', 'secret_access_key'];
  const hit = blocked.find(term => text.includes(term));
  if (hit) throw new Error(`Blocked sensitive field detected: ${hit}`);
}

async function digest(value) {
  const encoded = new TextEncoder().encode(stableStringify(value));
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  return 'sha256:' + [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
