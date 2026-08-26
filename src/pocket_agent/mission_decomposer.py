"""Bounded AURO-assisted decomposition of one large objective into workstreams.

The decomposer proposes structure only. It cannot execute tools, approve
runtime cells, create unbounded recursive tasks, or silently turn a malformed
model response into a mission. Every proposed workstream and deliverable passes
deterministic validation before the durable planner accepts it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .mission_executors import AuroCouncilClient
from .mission_profiles import (
    DeliverableContract,
    WorkstreamSpec,
    reasoning_profile,
)


DECOMPOSITION_SCHEMA = "pocket.mission.decomposition.v2"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    candidates = [raw]
    if "```" in raw:
        for block in raw.split("```"):
            stripped = block.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                candidates.append(stripped)
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.find("{") : raw.rfind("}") + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("AURO decomposition response did not contain one valid JSON object")


@dataclass(frozen=True)
class MissionDecomposition:
    objective: str
    title: str
    workstreams: tuple[Mapping[str, Any], ...]
    deliverables: tuple[Mapping[str, Any], ...]
    assumptions: tuple[str, ...]
    questions: tuple[str, ...]
    risks: tuple[str, ...]
    response_sha256: str
    evidence_class: str
    model_identity: Mapping[str, Any]
    receipt_sha256: str
    schema: str = DECOMPOSITION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["workstreams"] = [dict(item) for item in self.workstreams]
        value["deliverables"] = [dict(item) for item in self.deliverables]
        value["model_identity"] = dict(self.model_identity)
        return value


class AuroMissionDecomposer:
    """Ask the Auro council for a plan, then enforce a strict local schema."""

    def __init__(
        self,
        client: AuroCouncilClient,
        *,
        max_workstreams: int = 12,
        max_deliverables: int = 24,
        max_text_chars: int = 12_000,
    ) -> None:
        self.client = client
        self.max_workstreams = max(1, min(int(max_workstreams), 32))
        self.max_deliverables = max(1, min(int(max_deliverables), 100))
        self.max_text_chars = max(1_000, min(int(max_text_chars), 100_000))

    def decompose(
        self,
        objective: str,
        *,
        title: str = "",
        context: str = "",
        profile: str | Mapping[str, Any] = "deep",
        requested_deliverables: Sequence[str | Mapping[str, Any]] = (),
    ) -> MissionDecomposition:
        objective = str(objective).strip()
        if not objective:
            raise ValueError("objective is required")
        if len(objective) > self.max_text_chars:
            raise ValueError("objective exceeds decomposition input limit")
        selected = reasoning_profile(profile)
        prompt = self._prompt(
            objective,
            title=title,
            requested_deliverables=requested_deliverables,
            max_workstreams=self.max_workstreams,
            max_deliverables=self.max_deliverables,
        )
        response = self.client.respond(
            prompt,
            context=str(context)[: self.max_text_chars],
            reasoning_rounds=max(2, min(selected.interpretation_rounds + 1, 8)),
            model_lane="auro-2b-council",
        )
        structured = response.get("structured_answer")
        if isinstance(structured, Mapping) and isinstance(structured.get("workstreams"), list):
            payload = dict(structured)
        else:
            payload = _json_object(
                str(response.get("text") or response.get("answer") or "")
            )
        normalized = self._validate_payload(
            payload,
            objective=objective,
            fallback_title=title,
            requested_deliverables=requested_deliverables,
        )
        response_hash = _sha(response)
        receipt = {
            "schema": DECOMPOSITION_SCHEMA,
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
            "response_sha256": response_hash,
            "workstream_ids": [item["workstream_id"] for item in normalized["workstreams"]],
            "deliverable_paths": [item["path"] for item in normalized["deliverables"]],
            "evidence_class": str(response.get("evidence_class") or "E2-execution-log"),
            "model_identity": response.get("model") or response.get("runtime") or {},
            "private_chain_of_thought_exported": False,
            "validated_locally": True,
            "claim_boundary": (
                "decomposition proves a bounded plan proposal, not task completion, "
                "artifact correctness, deployment, or model superiority"
            ),
        }
        receipt_hash = _sha(receipt)
        return MissionDecomposition(
            objective=objective,
            title=normalized["title"],
            workstreams=tuple(normalized["workstreams"]),
            deliverables=tuple(normalized["deliverables"]),
            assumptions=tuple(normalized["assumptions"]),
            questions=tuple(normalized["questions"]),
            risks=tuple(normalized["risks"]),
            response_sha256=response_hash,
            evidence_class=receipt["evidence_class"],
            model_identity=dict(receipt["model_identity"]),
            receipt_sha256=receipt_hash,
        )

    @staticmethod
    def _prompt(
        objective: str,
        *,
        title: str,
        requested_deliverables: Sequence[str | Mapping[str, Any]],
        max_workstreams: int,
        max_deliverables: int,
    ) -> str:
        return f"""You are the AURO mission decomposition council.
Convert the objective into a finite set of independently executable workstreams.
Return JSON only. Do not execute anything. Do not include hidden chain-of-thought.

Required JSON schema:
{{
  "title": "short mission title",
  "workstreams": [
    {{
      "id": "safe-id",
      "title": "title",
      "objective": "bounded outcome",
      "context": "only context necessary for this workstream",
      "priority": 0,
      "acceptance_criteria": ["testable criterion"],
      "deliverables": [
        {{"path": "workstreams/safe-id/result.md", "title": "Result"}}
      ]
    }}
  ],
  "deliverables": [
    {{"path": "deliverables/final-report.md", "title": "Final Report"}}
  ],
  "assumptions": ["explicit assumption"],
  "questions": ["important unresolved question"],
  "risks": ["important risk"]
}}

Constraints:
- 1..{max_workstreams} workstreams.
- At most {max_deliverables} total deliverables.
- IDs use letters, numbers, hyphens, or underscores.
- No recursive or open-ended task creation.
- No shell commands, credentials, approvals, or claims that actions ran.
- Every criterion must be externally inspectable.
- PDF, DOCX, PPTX, and XLSX paths require an explicit renderer name.
- Preserve requested deliverables unless they are unsafe or duplicate.

Requested title: {title or '[derive one]'}
Requested deliverables: {json.dumps(list(requested_deliverables), ensure_ascii=False)}
Objective:
{objective}
"""

    def _validate_payload(
        self,
        payload: Mapping[str, Any],
        *,
        objective: str,
        fallback_title: str,
        requested_deliverables: Sequence[str | Mapping[str, Any]],
    ) -> dict[str, Any]:
        title = str(payload.get("title") or fallback_title or "POCKET Agent mission").strip()
        if not title or len(title) > 300:
            raise ValueError("decomposition title must contain 1..300 characters")
        raw_streams = payload.get("workstreams")
        if not isinstance(raw_streams, list) or not raw_streams:
            raise ValueError("decomposition requires a non-empty workstreams array")
        if len(raw_streams) > self.max_workstreams:
            raise ValueError(
                f"decomposition returned {len(raw_streams)} workstreams; limit is {self.max_workstreams}"
            )
        workstreams: list[dict[str, Any]] = []
        seen: set[str] = set()
        total_deliverables = 0
        for index, raw in enumerate(raw_streams):
            if not isinstance(raw, Mapping):
                raise ValueError(f"workstreams[{index}] must be an object")
            raw_id = str(raw.get("id") or raw.get("workstream_id") or "").strip()
            if not _ID.fullmatch(raw_id) or raw_id in seen:
                raise ValueError(f"invalid or duplicate workstream ID: {raw_id!r}")
            stream = WorkstreamSpec.from_value(
                {
                    "id": raw_id,
                    "title": str(raw.get("title") or raw_id),
                    "objective": str(raw.get("objective") or ""),
                    "context": str(raw.get("context") or ""),
                    "priority": int(raw.get("priority", 0)),
                    "acceptance_criteria": list(raw.get("acceptance_criteria") or []),
                    "deliverables": list(raw.get("deliverables") or []),
                    "metadata": {
                        "decomposed_from_objective_sha256": hashlib.sha256(
                            objective.encode("utf-8")
                        ).hexdigest()
                    },
                },
                index=index,
            )
            if not stream.acceptance_criteria:
                raise ValueError(
                    f"workstream {raw_id} requires at least one acceptance criterion"
                )
            total_deliverables += len(stream.deliverables)
            workstreams.append(stream.to_dict())
            seen.add(raw_id)

        global_values = [
            *list(requested_deliverables),
            *list(payload.get("deliverables") or []),
        ]
        deliverables: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for raw in global_values:
            contract = DeliverableContract.from_value(raw)
            if contract.path in seen_paths:
                continue
            seen_paths.add(contract.path)
            deliverables.append(contract.to_dict())
        total_deliverables += len(deliverables)
        if total_deliverables > self.max_deliverables:
            raise ValueError(
                f"decomposition returned {total_deliverables} deliverables; limit is {self.max_deliverables}"
            )

        def strings(name: str, limit: int = 50) -> list[str]:
            raw = payload.get(name) or []
            if not isinstance(raw, list):
                raise ValueError(f"{name} must be an array")
            return [str(item).strip()[:1000] for item in raw[:limit] if str(item).strip()]

        return {
            "title": title,
            "workstreams": workstreams,
            "deliverables": deliverables,
            "assumptions": strings("assumptions"),
            "questions": strings("questions"),
            "risks": strings("risks"),
        }


class AutoMissionProgramService:
    """Compose validated AURO decomposition with the durable mission service."""

    def __init__(self, base_service, decomposer: AuroMissionDecomposer) -> None:
        self.base_service = base_service
        self.decomposer = decomposer

    def create_from_objective(
        self,
        request: Mapping[str, Any],
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        objective = str(request.get("objective") or "").strip()
        decomposition = self.decomposer.decompose(
            objective,
            title=str(request.get("title") or ""),
            context=str(request.get("context") or ""),
            profile=request.get("reasoning_profile") or "deep",
            requested_deliverables=list(request.get("deliverables") or []),
        )
        program_request = {
            **dict(request),
            "title": decomposition.title,
            "objective": objective,
            "workstreams": [dict(item) for item in decomposition.workstreams],
            "deliverables": [dict(item) for item in decomposition.deliverables],
            "metadata": {
                **dict(request.get("metadata") or {}),
                "decomposition_receipt_sha256": decomposition.receipt_sha256,
                "decomposition_response_sha256": decomposition.response_sha256,
            },
        }
        created = self.base_service.create_program(
            program_request,
            principal_id=principal_id,
            tenant_id=tenant_id,
        )
        return {
            "schema": "pocket.mission.auto-created.v2",
            "decomposition": decomposition.to_dict(),
            "created": created,
        }
