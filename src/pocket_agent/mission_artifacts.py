"""Content-addressed artifact custody for durable POCKET Agent missions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Iterable, Mapping
import zipfile

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")
_INTERNAL_PACKAGE_FILES = {"ARTIFACT_MANIFEST.json", "mission-artifacts.zip"}
_TEXT_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".csv", ".json", ".yaml", ".yml", ".xml"}
_BINARY_RENDERER_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_segment(value: str) -> str:
    normalized = _SAFE_SEGMENT.sub("-", str(value).strip()).strip("-.")
    if not normalized:
        raise ValueError("identifier cannot be empty")
    return normalized[:160]


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    mission_id: str
    task_id: str | None
    relative_path: str
    media_type: str
    bytes: int
    sha256: str
    created_at_unix: int
    label: str = ""
    schema: str = "nexus.artifact.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnsupportedArtifactFormat(ValueError):
    pass


class ArtifactStore:
    """Path-safe, atomic artifact store with manifests and ZIP delivery."""

    def __init__(self, root: str | Path = "state/mission-artifacts", *, max_artifact_bytes: int = 64 * 1024 * 1024) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_artifact_bytes = max(1024, int(max_artifact_bytes))

    def mission_root(self, mission_id: str) -> Path:
        path = (self.root / safe_segment(mission_id)).resolve()
        path.relative_to(self.root)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve(self, mission_id: str, relative_path: str) -> tuple[Path, str]:
        relative = Path(str(relative_path).replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact path must be relative and cannot traverse parents")
        parts = [safe_segment(part) for part in relative.parts if part not in {"", "."}]
        if not parts:
            raise ValueError("artifact path cannot be empty")
        normalized = Path(*parts)
        root = self.mission_root(mission_id)
        path = (root / normalized).resolve()
        path.relative_to(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, normalized.as_posix()

    def record_existing(self, mission_id: str, relative_path: str, *, task_id: str | None = None, media_type: str | None = None, label: str = "") -> ArtifactRecord:
        path, normalized = self.resolve(mission_id, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        size = path.stat().st_size
        if size > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        digest = sha256_file(path)
        identity = hashlib.sha256(canonical({"mission_id": mission_id, "task_id": task_id, "path": normalized, "sha256": digest})).hexdigest()
        return ArtifactRecord(
            artifact_id="artifact_" + identity[:24],
            mission_id=mission_id,
            task_id=task_id,
            relative_path=normalized,
            media_type=media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            bytes=size,
            sha256=digest,
            created_at_unix=int(time.time()),
            label=str(label),
        )

    def write_bytes(self, mission_id: str, relative_path: str, data: bytes, *, task_id: str | None = None, media_type: str | None = None, label: str = "") -> ArtifactRecord:
        payload = bytes(data)
        if len(payload) > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        path, _ = self.resolve(mission_id, relative_path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        return self.record_existing(mission_id, relative_path, task_id=task_id, media_type=media_type, label=label)

    def write_text(self, mission_id: str, relative_path: str, text: str, *, task_id: str | None = None, media_type: str | None = None, label: str = "") -> ArtifactRecord:
        extension = Path(relative_path).suffix.lower()
        if extension in _BINARY_RENDERER_EXTENSIONS:
            raise UnsupportedArtifactFormat(
                f"{extension} requires a real registered renderer; POCKET Agent will not write text bytes into a binary document"
            )
        if extension and extension not in _TEXT_EXTENSIONS:
            raise UnsupportedArtifactFormat(f"unsupported text artifact extension: {extension}")
        actual_media = media_type or mimetypes.guess_type(relative_path)[0] or "text/plain"
        if actual_media.startswith("text/") and "charset=" not in actual_media:
            actual_media += "; charset=utf-8"
        return self.write_bytes(mission_id, relative_path, str(text).encode("utf-8"), task_id=task_id, media_type=actual_media, label=label)

    def write_json(self, mission_id: str, relative_path: str, value: Mapping[str, Any] | list[Any], *, task_id: str | None = None, label: str = "") -> ArtifactRecord:
        if Path(relative_path).suffix.lower() != ".json":
            raise ValueError("JSON artifacts must use a .json path")
        return self.write_bytes(
            mission_id,
            relative_path,
            (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
            task_id=task_id,
            media_type="application/json",
            label=label,
        )

    def list_files(self, mission_id: str) -> list[dict[str, Any]]:
        root = self.mission_root(mission_id)
        rows = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.name.endswith(".tmp"):
                continue
            rows.append({
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            })
        return rows

    def manifest(self, mission_id: str, records: Iterable[ArtifactRecord] | None = None) -> dict[str, Any]:
        supplied = list(records or [])
        files = [record.to_dict() for record in supplied] if supplied else [item for item in self.list_files(mission_id) if item["relative_path"] not in _INTERNAL_PACKAGE_FILES]
        payload: dict[str, Any] = {
            "schema": "pocket.mission.artifact-manifest.v1",
            "mission_id": mission_id,
            "artifact_count": len(files),
            "artifacts": files,
            "generated_at_unix": int(time.time()),
            "claim_boundary": "hashes prove artifact identity and custody in this store, not semantic correctness",
        }
        payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
        return payload

    def build_bundle(self, mission_id: str, *, records: Iterable[ArtifactRecord] | None = None, filename: str = "mission-artifacts.zip") -> tuple[ArtifactRecord, ArtifactRecord, dict[str, Any]]:
        root = self.mission_root(mission_id)
        manifest = self.manifest(mission_id, records)
        manifest_path = root / "ARTIFACT_MANIFEST.json"
        temp_manifest = manifest_path.with_suffix(".json.tmp")
        temp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_manifest.replace(manifest_path)
        manifest_record = self.record_existing(mission_id, "ARTIFACT_MANIFEST.json", media_type="application/json", label="artifact manifest")

        bundle_path, normalized = self.resolve(mission_id, filename)
        temporary = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                if path in {bundle_path, temporary} or path.name.endswith(".tmp"):
                    continue
                archive.write(path, path.relative_to(root).as_posix())
        temporary.replace(bundle_path)
        bundle_record = self.record_existing(mission_id, normalized, media_type="application/zip", label="mission artifact bundle")
        return manifest_record, bundle_record, manifest
