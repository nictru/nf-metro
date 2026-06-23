"""Tests for the TB trunk-continuation straight-drop invariant.

In a TB fan-out where one line continues straight down the trunk column (sharing
the hub's X with its child) while a sibling peels off to another column, the
continuing line must drop straight.  A TB section draws a line at ``station.x -
offset`` (the 90-degree rotation of the LR lane fan), constant for a line along a
collinear run, so the continuation drops straight by construction.  The same
holds at a fan-in where a feeder's source is collinear with a section's terminal
merge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nf_metro.layout.engine import compute_layout
from nf_metro.layout.routing import compute_station_offsets, route_edges
from nf_metro.layout.routing.invariants import (
    check_trunk_continuation_drops_straight,
)
from nf_metro.parser.mermaid import parse_metro_mermaid

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
EXAMPLE_TOPOLOGIES = EXAMPLES / "topologies"
FIXTURE_TOPOLOGIES = REPO_ROOT / "tests" / "fixtures" / "topologies"


def _gather_fixtures() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted(EXAMPLES.glob("*.mmd")))
    paths.extend(sorted(EXAMPLE_TOPOLOGIES.glob("*.mmd")))
    paths.extend(sorted(FIXTURE_TOPOLOGIES.glob("*.mmd")))
    return paths


def _route(path: Path):
    graph = parse_metro_mermaid(path.read_text())
    compute_layout(graph)
    offsets = compute_station_offsets(graph)
    routes = route_edges(graph, station_offsets=offsets)
    return graph, routes, offsets


@pytest.mark.parametrize(
    "path", _gather_fixtures(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_no_trunk_continuation_jog_in_gallery(path: Path) -> None:
    """Every shipped example and topology routes a same-lane continuation edge
    as a straight run, never a one-step diagonal jog off the trunk."""
    graph, routes, offsets = _route(path)
    violations = check_trunk_continuation_drops_straight(graph, routes, offsets)
    assert not violations, "\n".join(v.message() for v in violations)
