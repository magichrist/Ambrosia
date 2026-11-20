# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for phase loading and listing (organizational only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.domain.models import Artifact
from ambrosia.phases import (
    PhaseCatalog,
    load_phase_file,
    load_phases_from_dir,
)

if TYPE_CHECKING:
    from pathlib import Path


def _artifact(artifact_id: str, artifact_type: str, value: dict[str, object]) -> Artifact:
    return Artifact(
        id=artifact_id,
        engagement_id="eng",
        type=artifact_type,
        value=value,
    )


_PHASE_TEXT = """\
id: phase.discovery
name: Discovery
description: Discovery phase
tags: [discovery]
action_refs: [net.discover]
preset_refs: [net.demo]
visible_when:
  - kind: artifact_exists
    artifact_type: network.service
sort_order: 50
"""


def test_load_phase_file(tmp_path: Path) -> None:
    path = tmp_path / "phase.yaml"
    path.write_text(_PHASE_TEXT, encoding="utf-8")
    phase = load_phase_file(path)
    assert phase.id == "phase.discovery"
    assert phase.name == "Discovery"
    assert phase.sort_order == 50
    assert len(phase.visible_when) == 1


def test_load_phases_from_dir_deterministic(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text(
        _PHASE_TEXT.replace("phase.discovery", "phase.b").replace("name: Discovery", "name: B"),
        encoding="utf-8",
    )
    (tmp_path / "a.yaml").write_text(
        _PHASE_TEXT.replace("phase.discovery", "phase.a")
        .replace("name: Discovery", "name: A")
        .replace("sort_order: 50", "sort_order: 10"),
        encoding="utf-8",
    )
    catalog = load_phases_from_dir(tmp_path)
    ids = catalog.ids()
    assert ids == ("phase.a", "phase.b")
    listed = catalog.all()
    assert [p.id for p in listed] == ["phase.a", "phase.b"]


def test_get_and_unknown_refs(tmp_path: Path) -> None:
    (tmp_path / "p.yaml").write_text(_PHASE_TEXT, encoding="utf-8")
    catalog = load_phases_from_dir(tmp_path)
    assert catalog.get("phase.discovery") is not None
    assert catalog.get("phase.missing") is None
    assert catalog.unknown_refs(["phase.discovery", "phase.missing"]) == ["phase.missing"]


def test_evaluate_visibility(tmp_path: Path) -> None:
    path = tmp_path / "visibility.yaml"
    path.write_text(_PHASE_TEXT, encoding="utf-8")
    phase = load_phase_file(path)
    catalog = PhaseCatalog(phases={"phase.discovery": phase})
    smb = _artifact("s1", "network.service", {"service": "smb"})
    assert catalog.evaluate_visibility("phase.discovery", artifacts=[smb], inputs={}) is True
    assert catalog.evaluate_visibility("phase.discovery", artifacts=[], inputs={}) is False


def test_phase_is_organizational_only(tmp_path: Path) -> None:
    """A phase carries no permission or lifecycle machinery.

    Loading/listing a phase must not register actions, force ordering, or
    grant effects. The catalog surface is lookup, listing, and visibility
    evaluation only.
    """
    (tmp_path / "p.yaml").write_text(_PHASE_TEXT, encoding="utf-8")
    catalog = load_phases_from_dir(tmp_path)
    # Visible purely as metadata; no effect/permission surface.
    assert not hasattr(catalog, "grant_permission")
    assert not hasattr(catalog, "force_lifecycle")
    assert not hasattr(catalog, "authorize")
    # Phase refs are passive lists on the definition only.
    phase = catalog.get("phase.discovery")
    assert phase is not None
    assert phase.action_refs == ["net.discover"]
    assert phase.preset_refs == ["net.demo"]
