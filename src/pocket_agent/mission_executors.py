"""Mission executors for AURO reasoning and approval-bound computer work."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request, urlopen

from .mission_artifacts import ArtifactRecord, ArtifactStore, UnsupportedArtifactFormat
from .mission_orchestrator import TaskExecutionResult
from .runtime_cells import OperationRequest, RuntimeCellGovernor


def bounded(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "..."


class AuroCouncilClient:
    """Bounded HTTP client for Auro-2B council reasoning."""

    def __init__(self, url: str | None = None, *, api_token: str | None = None, timeout_seconds: float = 180.0) -> None:
        self.url = (url or os.getenv("AURO_COUNCIL_URL", "http://127.0.0.1:8090/v1/council/respond")).strip()
        self.api_token = api_token if api_token is not None else os.getenv("AURO_API_TOKEN", "")
        self.timeout_seconds = max(5.0, min(float(timeout_seconds), 3600.0))

    def status(self) -> dict[str, Any]:
        return {
            "schema": "pocket.auro-council-client.v1",
            "url": self.url,
            "api_token_configured": bool(self.api_token),
            "timeout_seconds": self.timeout_seconds,
            "claim_boundary": "configured client does not prove endpoint readiness or checkpoint identity",
        }

    def respond(self, message: str, *, parent_context: str | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
        body = {"message": str(message)}
        if parent_context:
            body["parent_context"] = str(parent_context)[:48_000]
        headers = {"content-type": "application/json"}
        if self.api_token:
            headers["authorization"] = "Bearer " + self.api_token
        request = Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        timeout = self.timeout_seconds if timeout_seconds is None else max(5.0, min(float(timeout_seconds), 3600.0))
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not str(payload.get("text") or "").strip():
            raise RuntimeError("AURO council returned no usable text")
        return payload


class AuroCouncilTaskExecutor:
    """Multi-pass council executor that writes exact task deliverables."""

    def __init__(self, client: AuroCouncilClient, artifacts: ArtifactStore) -> None:
        self.client = client
        self.artifacts = artifacts

    def execute(self, mission: Mapping[str, Any], task: Mapping[str, Any], dependency_results: Sequence[Mapping[str, Any]], progress: Callable[[float, str], None] | None = None) -> TaskExecutionResult:
        dependencies = self.dependency_context(dependency_results)
        rounds = max(1, min(int(task.get("reasoning_rounds", 1)), 12))
        timeout = max(10, int(task.get("timeout_seconds", 1800)))
        per_round_timeout = max(10, timeout / rounds)
        previous = ""
        responses = []
        started = time.perf_counter()
        for index in range(rounds):
            if progress:
                progress(index / (rounds + 1), f"AURO reasoning pass {index + 1}/{rounds}")
            prompt = self.round_prompt(mission, task, dependencies, previous, index, rounds)
            response = self.client.respond(prompt, parent_context=dependencies or None, timeout_seconds=per_round_timeout)
            responses.append(response)
            previous = bounded(response.get("text"), 10_000)

        final = responses[-1]
        structured = dict(final.get("structured_answer") or {})
        text = str(final.get("text") or structured.get("answer") or "").strip()
        blockers = tuple(str(item) for item in final.get("blockers", []) if str(item).strip())
        if progress:
            progress(rounds / (rounds + 1), "writing task artifacts")
        artifact_records, artifact_blockers = self.write_artifacts(mission, task, text, structured, responses)
        evidence = self.evidence(responses)
        confidence = self.confidence(structured, final)
        options = [str(item.get("consensus") or "") for item in final.get("consensus_votes", []) if isinstance(item, Mapping) and str(item.get("consensus") or "").strip()]
        all_blockers = tuple([*blockers, *artifact_blockers])
        fail_on_blockers = bool(task.get("payload", {}).get("fail_on_blockers", False))
        accepted = bool(text) and not artifact_blockers and not (fail_on_blockers and blockers)
        decision = {
            "summary": bounded(text, 2_000),
            "options": options[:12],
            "decision": str(structured.get("answer") or text),
            "evidence": list(evidence),
            "confidence": confidence,
            "blockers": list(all_blockers),
            "private_chain_of_thought_exported": False,
        }
        return TaskExecutionResult(
            summary=text,
            output={
                "text": text,
                "structured_answer": structured,
                "round_count": rounds,
                "round_receipts": [item.get("runtime_receipt") for item in responses],
                "evidence_class": final.get("evidence_class"),
                "release_evidence_ready": final.get("release_evidence_ready", False),
                "blockers": list(all_blockers),
            },
            artifacts=tuple(artifact_records),
            decision=decision,
            metrics={
                "reasoning_rounds": rounds,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "atomic_agent_count": sum(int(item.get("atomic_agent_count", 0)) for item in responses),
                "model_backed_atomic_count": sum(int(item.get("model_backed_atomic_count", 0)) for item in responses),
                "artifact_count": len(artifact_records),
                "confidence": confidence,
            },
            evidence=evidence,
            blockers=all_blockers,
            accepted=accepted,
        )

    @staticmethod
    def dependency_context(results: Sequence[Mapping[str, Any]]) -> str:
        blocks = []
        for item in results:
            result = item.get("result") or {}
            summary = result.get("summary") if isinstance(result, Mapping) else ""
            if not summary and isinstance(result, Mapping):
                output = result.get("output") or {}
                summary = output.get("text") if isinstance(output, Mapping) else ""
            blocks.append(f"[{item.get('task_id', 'dependency')}] {bounded(summary, 6_000)}")
        return "\n".join(blocks)[:32_000]

    @staticmethod
    def round_prompt(mission: Mapping[str, Any], task: Mapping[str, Any], dependencies: str, previous: str, index: int, rounds: int) -> str:
        if index == 0:
            mode = "Develop an independent evidence-bound solution."
        elif index == rounds - 1:
            mode = "Produce the corrected final decision after resolving prior weaknesses."
        else:
            mode = "Critique the previous pass, test alternatives, identify contradictions, and improve it."
        return f"""POCKET AGENT MISSION TASK\nMission: {mission.get('title')}\nMission objective: {mission.get('objective')}\nTask: {task.get('title')}\nTask objective: {task.get('objective')}\nKind: {task.get('kind')}\nAcceptance criteria: {json.dumps(task.get('acceptance_criteria', []), ensure_ascii=False)}\nPass: {index + 1}/{rounds}\nMode: {mode}\n\nDependency results:\n{dependencies or '[none]'}\n\nPrevious pass:\n{previous or '[none]'}\n\nReturn the direct result, a bounded reasoning summary, evidence references, confidence, caveats, and next actions. Do not expose private chain-of-thought or claim unexecuted actions."""

    def write_artifacts(self, mission: Mapping[str, Any], task: Mapping[str, Any], text: str, structured: Mapping[str, Any], responses: Sequence[Mapping[str, Any]]) -> tuple[list[ArtifactRecord], list[str]]:
        mission_id, task_id = str(mission["mission_id"]), str(task["task_id"])
        report = {
            "schema": "pocket.mission.task-report.v1",
            "mission_id": mission_id,
            "task_id": task_id,
            "kind": task.get("kind"),
            "answer": text,
            "structured_answer": dict(structured),
            "round_count": len(responses),
            "round_receipt_hashes": [(item.get("runtime_receipt") or {}).get("receipt_sha256") for item in responses],
            "claim_boundary": "decision summary and outputs only; private chain-of-thought is not stored",
        }
        records = [
            self.artifacts.write_json(mission_id, f"tasks/{task_id}/report.json", report, task_id=task_id, label="task report"),
            self.artifacts.write_text(mission_id, f"tasks/{task_id}/result.md", text + "\n", task_id=task_id, label="task result"),
        ]
        blockers = []
        for relative in [str(item) for item in task.get("required_artifacts", [])]:
            if relative in {record.relative_path for record in records}:
                continue
            try:
                if Path(relative).suffix.lower() == ".json":
                    record = self.artifacts.write_json(mission_id, relative, report, task_id=task_id, label="required deliverable")
                else:
                    record = self.artifacts.write_text(mission_id, relative, text + "\n", task_id=task_id, label="required deliverable")
                records.append(record)
            except UnsupportedArtifactFormat as exc:
                blockers.append(str(exc))
        return records, blockers

    @staticmethod
    def evidence(responses: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        values = []
        for response in responses:
            receipt = response.get("runtime_receipt") or {}
            value = receipt.get("receipt_sha256") or receipt.get("digest") if isinstance(receipt, Mapping) else None
            if value:
                values.append("council:" + str(value))
            for stage in response.get("mesie_receipts", []) or []:
                if isinstance(stage, Mapping) and stage.get("receipt_sha256"):
                    values.append("mesie:" + str(stage["receipt_sha256"]))
        return tuple(dict.fromkeys(values))

    @staticmethod
    def confidence(structured: Mapping[str, Any], response: Mapping[str, Any]) -> float:
        try:
            return max(0.0, min(float(structured.get("confidence", 0.0)), 1.0))
        except (TypeError, ValueError):
            votes = [float(item.get("confidence", 0.0)) for item in response.get("consensus_votes", []) if isinstance(item, Mapping)]
            return sum(votes) / max(len(votes), 1)


class RuntimeCellTaskExecutor:
    """Execute an exact pre-approved operation through POCKET runtime cells."""

    def __init__(self, governor: RuntimeCellGovernor, backend: Callable[[Mapping[str, Any]], Any], *, validator: Callable[[Any], Mapping[str, Any]] | None = None, artifacts: ArtifactStore | None = None) -> None:
        self.governor = governor
        self.backend = backend
        self.validator = validator
        self.artifacts = artifacts

    def execute(self, mission: Mapping[str, Any], task: Mapping[str, Any], dependency_results: Sequence[Mapping[str, Any]], progress: Callable[[float, str], None] | None = None) -> TaskExecutionResult:
        payload = dict(task.get("payload") or {})
        approval_id = str(payload.get("approval_id") or "")
        approval_token = str(payload.get("approval_token") or "")
        operation_value = dict(payload.get("operation") or {})
        if not approval_id or not approval_token or not operation_value:
            return TaskExecutionResult(
                summary="Execution is awaiting an exact operator approval.",
                output={"approval_required": True},
                blockers=("approval_id, approval_token, and exact operation are required",),
                accepted=False,
            )
        operation = OperationRequest(
            operator_id=str(operation_value.get("operator_id") or mission.get("principal_id")),
            agent_id=str(operation_value.get("agent_id") or "pocket-mission-worker"),
            cell_id=str(operation_value.get("cell_id") or ""),
            tool=str(operation_value.get("tool") or ""),
            arguments=dict(operation_value.get("arguments") or {}),
            filesystem_scope=tuple(operation_value.get("filesystem_scope") or ()),
            egress_scope=tuple(operation_value.get("egress_scope") or ()),
            environment=str(operation_value.get("environment") or "development"),
            estimated_cost_usd=float(operation_value.get("estimated_cost_usd", 0.0)),
            destructive=bool(operation_value.get("destructive", False)),
        )
        if progress:
            progress(0.25, "consuming exact action-bound approval")
        receipt = self.governor.execute(approval_id=approval_id, operation=operation, token=approval_token, executor=self.backend, validator=self.validator)
        artifacts: list[ArtifactRecord] = []
        if self.artifacts:
            artifacts.append(self.artifacts.write_json(str(mission["mission_id"]), f"tasks/{task['task_id']}/execution-receipt.json", receipt, task_id=str(task["task_id"]), label="governed execution receipt"))
        succeeded = receipt.get("status") == "succeeded"
        return TaskExecutionResult(
            summary="Governed runtime-cell operation completed." if succeeded else "Governed runtime-cell operation did not succeed.",
            output={"execution_receipt": receipt},
            artifacts=tuple(artifacts),
            decision={
                "summary": "Executed only the exact approved operation.", "options": [],
                "decision": receipt.get("status"), "evidence": ["receipt:" + str(receipt.get("digest"))],
                "confidence": 1.0, "blockers": [] if succeeded else [str(receipt.get("error") or receipt.get("status"))],
                "private_chain_of_thought_exported": False,
            },
            evidence=("receipt:" + str(receipt.get("digest")),),
            blockers=() if succeeded else (str(receipt.get("error") or receipt.get("status")),),
            accepted=succeeded,
        )
