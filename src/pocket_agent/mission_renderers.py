"""Validated artifact renderers for POCKET Agent mission deliverables.

Text, Markdown, JSON, CSV, and HTML can be rendered without optional
third-party dependencies. Binary office formats require a real renderer
registered by the host. The registry never writes UTF-8 text into a `.pdf`,
`.docx`, `.pptx`, or `.xlsx` filename and calls that a valid artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import html
import io
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .mission_artifacts import ArtifactRecord, ArtifactStore, UnsupportedArtifactFormat
from .mission_profiles import DeliverableContract


RENDER_RECEIPT_SCHEMA = "pocket.mission.render-receipt.v1"


@dataclass(frozen=True)
class RenderedArtifact:
    data: bytes
    media_type: str
    renderer: str
    metadata: Mapping[str, Any]


class Renderer(Protocol):
    def __call__(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact: ...


class ArtifactRendererRegistry:
    """Explicit renderer registry with extension and output validation."""

    def __init__(self) -> None:
        self._renderers: dict[str, tuple[frozenset[str], Renderer]] = {}
        self.register("builtin-markdown", {".md", ".txt", ".yaml", ".yml", ".xml"}, self._render_text)
        self.register("builtin-json", {".json"}, self._render_json)
        self.register("builtin-csv", {".csv"}, self._render_csv)
        self.register("builtin-html", {".html", ".htm"}, self._render_html)

    def register(
        self,
        name: str,
        extensions: Sequence[str] | set[str],
        renderer: Renderer,
        *,
        replace: bool = False,
    ) -> None:
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError("renderer name is required")
        if normalized_name in self._renderers and not replace:
            raise ValueError(f"renderer already registered: {normalized_name}")
        normalized_extensions = frozenset(
            item.lower() if str(item).startswith(".") else "." + str(item).lower()
            for item in extensions
        )
        if not normalized_extensions:
            raise ValueError("renderer must support at least one extension")
        self._renderers[normalized_name] = (normalized_extensions, renderer)

    def manifest(self) -> dict[str, Any]:
        return {
            "schema": "pocket.mission.renderer-registry.v1",
            "renderers": {
                name: sorted(extensions)
                for name, (extensions, _) in sorted(self._renderers.items())
            },
            "binary_formats_require_registered_renderer": True,
        }

    def renderer_for(self, contract: DeliverableContract) -> tuple[str, Renderer]:
        extension = contract.extension
        if contract.renderer:
            try:
                extensions, renderer = self._renderers[contract.renderer]
            except KeyError as exc:
                raise UnsupportedArtifactFormat(
                    f"deliverable {contract.path} requires unavailable renderer {contract.renderer!r}"
                ) from exc
            if extension not in extensions:
                raise UnsupportedArtifactFormat(
                    f"renderer {contract.renderer!r} does not support {extension}"
                )
            return contract.renderer, renderer
        for name, (extensions, renderer) in self._renderers.items():
            if extension in extensions:
                return name, renderer
        raise UnsupportedArtifactFormat(
            f"no real renderer is registered for {extension or '[no extension]'}"
        )

    def render(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        name, renderer = self.renderer_for(contract)
        rendered = renderer(contract, source)
        if not isinstance(rendered, RenderedArtifact):
            raise TypeError(f"renderer {name} returned an invalid result")
        if len(rendered.data) < contract.minimum_bytes:
            raise ValueError(
                f"rendered {contract.path} is {len(rendered.data)} bytes; "
                f"minimum is {contract.minimum_bytes}"
            )
        if not rendered.media_type.strip():
            raise ValueError(f"renderer {name} returned no media type")
        return rendered

    def render_to_store(
        self,
        artifacts: ArtifactStore,
        mission_id: str,
        task_id: str,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> tuple[ArtifactRecord, dict[str, Any]]:
        rendered = self.render(contract, source)
        record = artifacts.write_bytes(
            mission_id,
            contract.path,
            rendered.data,
            task_id=task_id,
            media_type=contract.media_type or rendered.media_type,
            label=contract.title or "mission deliverable",
        )
        criteria = [str(item) for item in contract.acceptance_criteria]
        receipt = {
            "schema": RENDER_RECEIPT_SCHEMA,
            "artifact": record.to_dict(),
            "renderer": rendered.renderer,
            "required": contract.required,
            "minimum_bytes": contract.minimum_bytes,
            "acceptance_criteria": criteria,
            "metadata": {**dict(contract.metadata), **dict(rendered.metadata)},
            "checks": {
                "path_matches": record.relative_path == contract.path,
                "minimum_bytes": record.bytes >= contract.minimum_bytes,
                "sha256_present": len(record.sha256) == 64,
                "media_type_present": bool(record.media_type),
            },
            "claim_boundary": (
                "the receipt proves renderer invocation and artifact identity; "
                "semantic acceptance criteria still require a validator"
            ),
        }
        receipt["valid"] = all(receipt["checks"].values())
        return record, receipt

    @staticmethod
    def _source_text(source: Mapping[str, Any]) -> str:
        for key in ("text", "answer", "summary", "result"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        structured = source.get("structured_answer")
        if isinstance(structured, Mapping):
            for key in ("answer", "summary", "consensus"):
                value = structured.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return json.dumps(source, indent=2, sort_keys=True, ensure_ascii=False)

    def _render_text(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        text = self._source_text(source)
        extension = contract.extension
        if extension == ".md":
            title = contract.title or Path(contract.path).stem.replace("-", " ").title()
            text = f"# {title}\n\n{text}\n"
            media_type = "text/markdown; charset=utf-8"
        elif extension in {".yaml", ".yml"}:
            # JSON is a valid YAML 1.2 subset and remains deterministic here.
            text = json.dumps(source, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            media_type = "application/yaml"
        elif extension == ".xml":
            text = (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                f"<mission-deliverable><title>{html.escape(contract.title)}</title>"
                f"<content>{html.escape(text)}</content></mission-deliverable>\n"
            )
            media_type = "application/xml"
        else:
            text += "\n"
            media_type = "text/plain; charset=utf-8"
        return RenderedArtifact(
            data=text.encode("utf-8"),
            media_type=media_type,
            renderer="builtin-markdown",
            metadata={"encoding": "utf-8"},
        )

    def _render_json(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        payload = {
            "schema": "pocket.mission.deliverable.v1",
            "title": contract.title,
            "source": dict(source),
            "acceptance_criteria": list(contract.acceptance_criteria),
            "metadata": dict(contract.metadata),
        }
        return RenderedArtifact(
            data=(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
            media_type="application/json",
            renderer="builtin-json",
            metadata={"encoding": "utf-8"},
        )

    def _render_csv(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        rows = source.get("rows")
        if not isinstance(rows, list) or not all(isinstance(item, Mapping) for item in rows):
            rows = [
                {"field": key, "value": json.dumps(value, ensure_ascii=False, default=str)}
                for key, value in source.items()
            ]
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if str(key) not in fieldnames:
                    fieldnames.append(str(key))
        if not fieldnames:
            fieldnames = ["value"]
            rows = [{"value": ""}]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
        return RenderedArtifact(
            data=buffer.getvalue().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            renderer="builtin-csv",
            metadata={"rows": len(rows), "columns": fieldnames},
        )

    def _render_html(
        self,
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        text = html.escape(self._source_text(source)).replace("\n", "<br>\n")
        title = html.escape(contract.title or Path(contract.path).stem)
        document = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body><main><h1>{title}</h1><p>{text}</p></main></body>
</html>
"""
        return RenderedArtifact(
            data=document.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            renderer="builtin-html",
            metadata={"encoding": "utf-8"},
        )


def callable_binary_renderer(
    name: str,
    media_type: str,
    callback: Callable[[DeliverableContract, Mapping[str, Any]], bytes],
) -> Renderer:
    """Wrap a host-owned binary renderer while preserving receipt metadata."""

    def render(
        contract: DeliverableContract,
        source: Mapping[str, Any],
    ) -> RenderedArtifact:
        data = callback(contract, source)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"binary renderer {name} must return bytes")
        return RenderedArtifact(
            data=bytes(data),
            media_type=media_type,
            renderer=name,
            metadata={"host_registered": True},
        )

    return render
