"""Reasoning and artifact contracts for long-running POCKET Agent missions.

Profiles control explicit work structure, independent review, revision cycles,
and bounded council passes. They do not expose or persist private chain-of-
thought. Deliverable contracts describe files that must be produced and how
they must be validated; a filename alone is never treated as proof that a
valid artifact exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


PROFILE_SCHEMA = "pocket.mission.reasoning-profile.v1"
DELIVERABLE_SCHEMA = "pocket.mission.deliverable-contract.v1"
WORKSTREAM_SCHEMA = "pocket.mission.workstream.v1"


@dataclass(frozen=True)
class ReasoningProfile:
    name: str
    interpretation_rounds: int
    evidence_rounds: int
    solution_rounds: int
    review_rounds: int
    revision_rounds: int
    synthesis_rounds: int
    revision_cycles: int
    independent_reviewers: int
    max_parallel: int
    default_timeout_seconds: int
    max_tasks: int
    description: str
    schema: str = PROFILE_SCHEMA

    def __post_init__(self) -> None:
        for field_name in (
            "interpretation_rounds",
            "evidence_rounds",
            "solution_rounds",
            "review_rounds",
            "revision_rounds",
            "synthesis_rounds",
        ):
            value = int(getattr(self, field_name))
            if value < 1 or value > 12:
                raise ValueError(f"{field_name} must be in 1..12")
        if self.revision_cycles < 0 or self.revision_cycles > 6:
            raise ValueError("revision_cycles must be in 0..6")
        if self.independent_reviewers < 1 or self.independent_reviewers > 6:
            raise ValueError("independent_reviewers must be in 1..6")
        if self.max_parallel < 1 or self.max_parallel > 32:
            raise ValueError("max_parallel must be in 1..32")
        if self.default_timeout_seconds < 30 or self.default_timeout_seconds > 86_400:
            raise ValueError("default_timeout_seconds must be in 30..86400")
        if self.max_tasks < 1 or self.max_tasks > 10_000:
            raise ValueError("max_tasks must be in 1..10000")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REASONING_PROFILES: dict[str, ReasoningProfile] = {
    "quick": ReasoningProfile(
        name="quick",
        interpretation_rounds=1,
        evidence_rounds=1,
        solution_rounds=1,
        review_rounds=1,
        revision_rounds=1,
        synthesis_rounds=1,
        revision_cycles=0,
        independent_reviewers=1,
        max_parallel=2,
        default_timeout_seconds=900,
        max_tasks=100,
        description="Fast bounded work with one analysis and one final review.",
    ),
    "standard": ReasoningProfile(
        name="standard",
        interpretation_rounds=2,
        evidence_rounds=2,
        solution_rounds=3,
        review_rounds=2,
        revision_rounds=2,
        synthesis_rounds=2,
        revision_cycles=1,
        independent_reviewers=2,
        max_parallel=3,
        default_timeout_seconds=3_600,
        max_tasks=500,
        description="Balanced production work with evidence, implementation, review, and revision.",
    ),
    "deep": ReasoningProfile(
        name="deep",
        interpretation_rounds=3,
        evidence_rounds=4,
        solution_rounds=5,
        review_rounds=4,
        revision_rounds=4,
        synthesis_rounds=4,
        revision_cycles=2,
        independent_reviewers=3,
        max_parallel=5,
        default_timeout_seconds=7_200,
        max_tasks=1_500,
        description="Multiple independent analyses, two revision cycles, and cross-workstream synthesis.",
    ),
    "exhaustive": ReasoningProfile(
        name="exhaustive",
        interpretation_rounds=4,
        evidence_rounds=6,
        solution_rounds=8,
        review_rounds=6,
        revision_rounds=6,
        synthesis_rounds=6,
        revision_cycles=3,
        independent_reviewers=4,
        max_parallel=8,
        default_timeout_seconds=21_600,
        max_tasks=5_000,
        description="Long-form mission mode with broad parallel work, repeated adversarial review, and staged synthesis.",
    ),
}


def reasoning_profile(value: str | Mapping[str, Any] | ReasoningProfile | None) -> ReasoningProfile:
    """Resolve a named profile or a bounded custom profile."""
    if value is None:
        return REASONING_PROFILES["standard"]
    if isinstance(value, ReasoningProfile):
        return value
    if isinstance(value, str):
        try:
            return REASONING_PROFILES[value.strip().lower()]
        except KeyError as exc:
            raise ValueError(
                f"unknown reasoning profile {value!r}; choose {sorted(REASONING_PROFILES)}"
            ) from exc
    if not isinstance(value, Mapping):
        raise TypeError("reasoning profile must be a name, mapping, or ReasoningProfile")
    base_name = str(value.get("base") or value.get("name") or "standard").lower()
    base = REASONING_PROFILES.get(base_name, REASONING_PROFILES["standard"])
    data = base.to_dict()
    data.pop("schema", None)
    for key in tuple(data):
        if key in value:
            data[key] = value[key]
    data["name"] = str(value.get("name") or f"custom-{base.name}")
    data["description"] = str(value.get("description") or base.description)
    return ReasoningProfile(**data)


_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$")
_BINARY_FORMATS = {".pdf", ".docx", ".pptx", ".xlsx"}
_TEXT_FORMATS = {".md", ".txt", ".json", ".csv", ".html", ".htm", ".yaml", ".yml", ".xml"}


@dataclass(frozen=True)
class DeliverableContract:
    path: str
    title: str = ""
    media_type: str | None = None
    renderer: str | None = None
    required: bool = True
    minimum_bytes: int = 1
    acceptance_criteria: tuple[str, ...] = ()
    source_tasks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema: str = DELIVERABLE_SCHEMA

    def __post_init__(self) -> None:
        normalized = str(self.path).replace("\\", "/").strip()
        if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
            raise ValueError("deliverable path must be a safe relative path")
        if not _SAFE_PATH.fullmatch(normalized):
            raise ValueError(f"unsafe deliverable path: {normalized}")
        if int(self.minimum_bytes) < 0:
            raise ValueError("minimum_bytes must be nonnegative")
        extension = Path(normalized).suffix.lower()
        if extension in _BINARY_FORMATS and not self.renderer:
            raise ValueError(
                f"{extension} deliverables require an explicit registered renderer"
            )
        if extension and extension not in _TEXT_FORMATS | _BINARY_FORMATS:
            raise ValueError(f"unsupported deliverable extension: {extension}")
        object.__setattr__(self, "path", normalized)

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    @property
    def binary(self) -> bool:
        return self.extension in _BINARY_FORMATS

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["metadata"] = dict(self.metadata)
        return value

    @classmethod
    def from_value(
        cls,
        value: str | Mapping[str, Any] | "DeliverableContract",
    ) -> "DeliverableContract":
        if isinstance(value, DeliverableContract):
            return value
        if isinstance(value, str):
            return cls(path=value, title=Path(value).stem.replace("-", " ").title())
        if not isinstance(value, Mapping):
            raise TypeError("deliverable must be a path, mapping, or DeliverableContract")
        path = str(value.get("path") or value.get("name") or "").strip()
        return cls(
            path=path,
            title=str(value.get("title") or Path(path).stem.replace("-", " ").title()),
            media_type=str(value.get("media_type") or "").strip() or None,
            renderer=str(value.get("renderer") or "").strip() or None,
            required=bool(value.get("required", True)),
            minimum_bytes=max(0, int(value.get("minimum_bytes", 1))),
            acceptance_criteria=tuple(
                str(item) for item in value.get("acceptance_criteria", ()) if str(item).strip()
            ),
            source_tasks=tuple(
                str(item) for item in value.get("source_tasks", ()) if str(item).strip()
            ),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class WorkstreamSpec:
    workstream_id: str
    objective: str
    title: str = ""
    context: str = ""
    priority: int = 0
    deliverables: tuple[DeliverableContract, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema: str = WORKSTREAM_SCHEMA

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", self.workstream_id):
            raise ValueError("workstream_id must use letters, numbers, hyphens, or underscores")
        if not str(self.objective).strip():
            raise ValueError("workstream objective is required")
        object.__setattr__(self, "objective", str(self.objective).strip())
        object.__setattr__(self, "title", str(self.title or self.workstream_id).strip())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["deliverables"] = [item.to_dict() for item in self.deliverables]
        value["metadata"] = dict(self.metadata)
        return value

    @classmethod
    def from_value(
        cls,
        value: str | Mapping[str, Any] | "WorkstreamSpec",
        *,
        index: int,
    ) -> "WorkstreamSpec":
        if isinstance(value, WorkstreamSpec):
            return value
        if isinstance(value, str):
            return cls(
                workstream_id=f"workstream-{index + 1:02d}",
                title=f"Workstream {index + 1}",
                objective=value,
            )
        if not isinstance(value, Mapping):
            raise TypeError("workstream must be a string, mapping, or WorkstreamSpec")
        raw_id = str(value.get("workstream_id") or value.get("id") or f"workstream-{index + 1:02d}")
        return cls(
            workstream_id=raw_id,
            title=str(value.get("title") or raw_id),
            objective=str(value.get("objective") or ""),
            context=str(value.get("context") or ""),
            priority=int(value.get("priority", 0)),
            deliverables=tuple(
                DeliverableContract.from_value(item)
                for item in value.get("deliverables", ())
            ),
            acceptance_criteria=tuple(
                str(item) for item in value.get("acceptance_criteria", ()) if str(item).strip()
            ),
            metadata=dict(value.get("metadata") or {}),
        )


def normalize_workstreams(
    values: Sequence[str | Mapping[str, Any] | WorkstreamSpec],
) -> tuple[WorkstreamSpec, ...]:
    if not values:
        raise ValueError("at least one workstream is required")
    output = tuple(WorkstreamSpec.from_value(item, index=index) for index, item in enumerate(values))
    ids = [item.workstream_id for item in output]
    if len(ids) != len(set(ids)):
        raise ValueError("workstream IDs must be unique")
    return output


def normalize_deliverables(
    values: Sequence[str | Mapping[str, Any] | DeliverableContract],
) -> tuple[DeliverableContract, ...]:
    output = tuple(DeliverableContract.from_value(item) for item in values)
    paths = [item.path for item in output]
    if len(paths) != len(set(paths)):
        raise ValueError("deliverable paths must be unique")
    return output
