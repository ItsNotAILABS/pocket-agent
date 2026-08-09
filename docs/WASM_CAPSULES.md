# WASM multi-sandbox capsules — 20 reasons agents spin them up

Protocol: **PROTO-CAPSULE-WASM-009** (POCKET multi-sandbox capsule).  
Runtimes: **WASI** (wasmtime) · **HostWorker** · **BrowserWorker** (+ optional **WebGPU**).

Agents should call `capsule_spin(...)` / skill `capsule_allocate` when any of these apply.

## The 20 reasons

| # | Reason ID | Improves agents by… |
|---|-----------|---------------------|
| 1 | `untrusted_eval` | Run untrusted code/scripts without host ambient authority |
| 2 | `sandbox_tests` | Isolated test runs that cannot trash the workspace |
| 3 | `dependency_install` | Ephemeral package installs that never leak into host site-packages |
| 4 | `repo_mount_edit` | Mount a repo, edit in overlay, commit only on explicit approve |
| 5 | `wasm_guest_tool` | Execute portable `.wasm` tools (wasi) with no ambient net |
| 6 | `webgpu_compute` | GPGPU / ML kernels via WebGPU doctrine (host probe / Edge) |
| 7 | `parallel_slice` | Isolate one RAH leaf’s filesystem so parallel writers don’t collide |
| 8 | `adversarial_verify` | Run verifier/adversary in a throwaway environment |
| 9 | `repro_bug` | Reproduce a bug with clean env, keep logs, terminate |
| 10 | `secret_scrub` | Process data where overlay is discarded if secrets appear |
| 11 | `browser_worker` | Edge/BrowserWorker guest for DOM/WebGPU without desk pollution |
| 12 | `build_artifact` | Compile/build artifacts in capsule, export only dist/ |
| 13 | `fuzz_input` | Fuzz parsers/tools with crash isolation |
| 14 | `policy_eval` | Evaluate economic/policy scripts without mutating live ledgers |
| 15 | `skill_preview` | Try a generated skill package before promoting to durable skills |
| 16 | `third_party_cli` | Run third-party CLIs with capped FS preopens |
| 17 | `long_job_park` | Park long-running work in capsule overlay between heartbeats |
| 18 | `multi_tenant_slice` | Soft multi-tenant isolation for seat/demo runs |
| 19 | `mesh_artifact_lab` | Produce mesh artifacts offline, then publish hash-only |
| 20 | `rollback_experiment` | Experiment freely; terminate capsule = full rollback |

## API (Python)

```python
from pocket_agent.capsules import spin, list_reasons, terminate

print(list_reasons())
cap = spin(tier="512MB", webgpu=False, reason="untrusted_eval", label="eval-1")
# ... run guest commands via host when POCKET is present ...
terminate(cap["id"])
```

## CLI

```bash
pocket-agent capsule reasons
pocket-agent capsule spin --reason sandbox_tests --tier 512MB
pocket-agent capsule list
```

## Security

- No ambient network unless granted  
- OverlayFS under `~/.pocket/capsules/{id}/` until `commit()`  
- Live/economic rails remain paper-first outside capsules  
