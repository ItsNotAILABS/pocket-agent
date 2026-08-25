import hashlib
import json

import pytest

from pocket_agent.mission_decomposer import (
    AutoMissionProgramService,
    AuroMissionDecomposer,
)
from test_mission_program_v2 import build_service


class FakeDecompositionClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def respond(self, objective, *, context="", reasoning_rounds=1, model_lane=None):
        self.calls.append(
            {
                "objective": objective,
                "context": context,
                "reasoning_rounds": reasoning_rounds,
                "model_lane": model_lane,
            }
        )
        return {
            "text": json.dumps(self.payload),
            "evidence_class": "E3-validated-output",
            "model": {
                "model_id": "Auro-2B",
                "checkpoint_sha256": "a" * 64,
            },
        }


def valid_payload():
    return {
        "title": "Automatic product mission",
        "workstreams": [
            {
                "id": "research",
                "title": "Research",
                "objective": "Evaluate evidence and uncertainty.",
                "priority": 3,
                "acceptance_criteria": ["sources and uncertainty are explicit"],
                "deliverables": [
                    {"path": "workstreams/research/result.md", "title": "Research Result"}
                ],
            },
            {
                "id": "implementation",
                "title": "Implementation",
                "objective": "Build and validate the implementation.",
                "priority": 4,
                "acceptance_criteria": ["implementation and validation are documented"],
            },
            {
                "id": "delivery",
                "title": "Delivery",
                "objective": "Prepare user-facing delivery material.",
                "priority": 2,
                "acceptance_criteria": ["customer-facing output is present"],
            },
        ],
        "deliverables": [
            {"path": "deliverables/final-report.md", "title": "Final Report"},
            {"path": "deliverables/evidence.json", "title": "Evidence"},
        ],
        "assumptions": ["The AURO council endpoint is configured."],
        "questions": ["Which deployment target is approved?"],
        "risks": ["Exact checkpoint quality remains an evidence dependency."],
    }


def test_decomposer_turns_one_large_objective_into_validated_workstreams():
    client = FakeDecompositionClient(valid_payload())
    decomposer = AuroMissionDecomposer(client, max_workstreams=8)
    result = decomposer.decompose(
        "Research, implement, and prepare a customer release.",
        profile="deep",
        requested_deliverables=["deliverables/operator-checklist.md"],
    )
    assert result.title == "Automatic product mission"
    assert [item["workstream_id"] for item in result.workstreams] == [
        "research",
        "implementation",
        "delivery",
    ]
    assert {item["path"] for item in result.deliverables} == {
        "deliverables/operator-checklist.md",
        "deliverables/final-report.md",
        "deliverables/evidence.json",
    }
    assert result.evidence_class == "E3-validated-output"
    assert len(result.response_sha256) == 64
    assert len(result.receipt_sha256) == 64
    assert client.calls[0]["model_lane"] == "auro-2b-council"
    assert client.calls[0]["reasoning_rounds"] >= 2


def test_decomposer_rejects_unbounded_duplicate_or_unverifiable_output():
    duplicate = valid_payload()
    duplicate["workstreams"][1]["id"] = "research"
    with pytest.raises(ValueError, match="duplicate"):
        AuroMissionDecomposer(FakeDecompositionClient(duplicate)).decompose("Do the work")

    missing_criteria = valid_payload()
    missing_criteria["workstreams"][0]["acceptance_criteria"] = []
    with pytest.raises(ValueError, match="acceptance criterion"):
        AuroMissionDecomposer(FakeDecompositionClient(missing_criteria)).decompose("Do the work")

    too_many = valid_payload()
    too_many["workstreams"] = [
        {
            "id": f"w{index}",
            "objective": f"Objective {index}",
            "acceptance_criteria": ["complete"],
        }
        for index in range(5)
    ]
    with pytest.raises(ValueError, match="limit is 2"):
        AuroMissionDecomposer(
            FakeDecompositionClient(too_many),
            max_workstreams=2,
        ).decompose("Do the work")


def test_auto_service_persists_the_decomposed_program(tmp_path):
    base, _ = build_service(tmp_path)
    client = FakeDecompositionClient(valid_payload())
    auto = AutoMissionProgramService(base, AuroMissionDecomposer(client))
    result = auto.create_from_objective(
        {
            "title": "Automatic",
            "objective": "Research, implement, review, and deliver the product.",
            "reasoning_profile": "quick",
            "deliverables": ["deliverables/requested.md"],
        },
        principal_id="user-auto",
        tenant_id="tenant-auto",
    )
    mission = result["created"]["mission"]
    assert mission["principal_id"] == "user-auto"
    assert mission["tenant_id"] == "tenant-auto"
    assert mission["progress"]["total"] > 10
    assert len({task["task_id"] for task in mission["tasks"]}) == len(mission["tasks"])
    assert result["decomposition"]["receipt_sha256"]
    base.store.close()


def test_binary_deliverable_from_model_requires_explicit_renderer():
    payload = valid_payload()
    payload["deliverables"].append(
        {"path": "deliverables/fake.pdf", "title": "Fake PDF"}
    )
    with pytest.raises(ValueError, match="registered renderer"):
        AuroMissionDecomposer(FakeDecompositionClient(payload)).decompose("Do the work")
