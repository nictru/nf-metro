"""TB sections are a true 90-degree rotation of LR: lanes never cross.

A TB section draws each line at ``station.x - offset``, the chirality-preserving
rotation image of LR's ``station.y + offset`` fan.  Two lines that enter a TB
section in a given left-to-right order therefore keep that order all the way down
the section -- the bundle runs parallel and never crosses, whether the lines
arrive over an LR-to-TB seam (a TOP/RIGHT entry) or fold in from a BOTTOM exit.

A within-section crossing leaves every individual arc concentric, so the curve
guards do not catch it; this test pins the no-cross property directly on the
laid-out geometry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nf_metro.layout.engine import compute_layout
from nf_metro.layout.routing import compute_station_offsets, route_edges
from nf_metro.parser.mermaid import parse_metro_mermaid
from nf_metro.parser.model import MetroGraph

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_TOPOLOGIES = REPO_ROOT / "examples" / "topologies"

# Fixtures whose lines enter a TB section over a seam (LR-to-TB TOP entry, an
# over-the-top RIGHT-entry U-turn, or a folded BOTTOM-exit) and run on as a
# multi-line bundle.
_SEAM_FIXTURES = [
    "lr_to_tb_top_two_lines.mmd",
    "lr_to_tb_top_drop_two_lines.mmd",
    "tb_right_entry_stack.mmd",
    "fold_double.mmd",
    "fold_fan_across.mmd",
]

_COORD_TOLERANCE = 1.0


def _route(path: Path) -> tuple[MetroGraph, list, dict[tuple[str, str], float]]:
    graph = parse_metro_mermaid(path.read_text())
    compute_layout(graph)
    offsets = compute_station_offsets(graph)
    routes = route_edges(graph, station_offsets=offsets)
    return graph, routes, offsets


def _line_x_at_station(graph: MetroGraph, routes: list, station) -> dict[str, float]:
    """Per line through *station*, the X at which its route passes the marker.

    A line riding station ``S`` has a routed point on ``S``'s own Y near its
    column; that X is the lane the line draws on at the marker, free of the
    inter-section approach legs that run at the entry port's Y rather than a
    station's.  When a route touches the marker Y more than once, the point
    nearest the column wins.
    """
    out: dict[str, float] = {}
    for route in routes:
        candidates = [
            x for x, y in route.points if abs(y - station.y) <= _COORD_TOLERANCE
        ]
        if not candidates:
            continue
        out[route.line_id] = min(candidates, key=lambda x: abs(x - station.x))
    return out


@pytest.mark.parametrize("fixture", _SEAM_FIXTURES)
def test_tb_section_lanes_do_not_cross(fixture: str) -> None:
    """Every pair of lines keeps its left-right order through each TB section.

    Compares each pair's drawn X at the topmost and bottommost station of every
    TB section; a sign flip between the two is a within-section crossing.
    """
    graph, routes, _offsets = _route(EXAMPLE_TOPOLOGIES / fixture)
    tb_sections = [s for s in graph.sections.values() if s.direction == "TB"]
    assert tb_sections, f"{fixture}: expected a TB section"

    checked = 0
    for sec in tb_sections:
        stations = sorted(
            (
                graph.stations[sid]
                for sid in sec.station_ids
                if not graph.stations[sid].is_port
            ),
            key=lambda s: s.y,
        )
        if len(stations) < 2:
            continue
        top_x = _line_x_at_station(graph, routes, stations[0])
        bottom_x = _line_x_at_station(graph, routes, stations[-1])
        lines = sorted(top_x.keys() & bottom_x.keys())
        for i, a in enumerate(lines):
            for b in lines[i + 1 :]:
                top_gap = top_x[a] - top_x[b]
                bottom_gap = bottom_x[a] - bottom_x[b]
                if abs(top_gap) < _COORD_TOLERANCE:
                    continue
                checked += 1
                assert top_gap * bottom_gap >= 0, (
                    f"{fixture} section {sec.id!r}: lines {a!r} and {b!r} cross "
                    f"inside the TB section (X order flips from top dx={top_gap:.1f} "
                    f"to bottom dx={bottom_gap:.1f})"
                )
    assert checked, f"{fixture}: no multi-line TB section pair exercised"


@pytest.mark.parametrize("fixture", _SEAM_FIXTURES)
def test_tb_line_draws_at_rotation_image_of_offset(fixture: str) -> None:
    """Each TB line passes a station at ``station.x - offset``.

    The defining property of the rotation model: a vertical-flow lane fans to
    -X, so a line's drawn X at a station is its grid column minus its stored
    (positive) offset.  A reflection fan (``x + bundle_max - offset``) puts the
    same line on the opposite side of the column and fails here.
    """
    graph, routes, offsets = _route(EXAMPLE_TOPOLOGIES / fixture)
    tb_sections = [s for s in graph.sections.values() if s.direction == "TB"]
    assert tb_sections, f"{fixture}: expected a TB section"

    checked = 0
    for sec in tb_sections:
        for sid in sec.station_ids:
            station = graph.stations[sid]
            if station.is_port:
                continue
            drawn = _line_x_at_station(graph, routes, station)
            for lid, x in drawn.items():
                expected = station.x - offsets.get((sid, lid), 0.0)
                checked += 1
                assert abs(x - expected) <= _COORD_TOLERANCE, (
                    f"{fixture} station {sid!r} line {lid!r}: drawn X {x:.1f} != "
                    f"rotation image {expected:.1f} (station.x={station.x:.1f} - "
                    f"offset={offsets.get((sid, lid), 0.0):.1f})"
                )
    assert checked, f"{fixture}: no TB station lines exercised"
