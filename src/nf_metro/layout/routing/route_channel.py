"""Author-directed inter-section route channel Y alignment."""

from __future__ import annotations

from nf_metro.layout.constants import SECTION_Y_PADDING
from nf_metro.parser.model import MetroGraph, PortSide

RouteChannelRule = tuple[str, str, str, list[str]]


def _section_band_midpoint(graph: MetroGraph, section_ids: list[str]) -> float | None:
    members = [
        graph.sections[sid]
        for sid in section_ids
        if sid in graph.sections and graph.sections[sid].bbox_h > 0
    ]
    if not members:
        return None
    top = min(section.bbox_y for section in members)
    bottom = max(section.bbox_y + section.bbox_h for section in members)
    return (top + bottom) / 2


def _fanout_junction_ids_downstream(graph: MetroGraph, start_id: str) -> set[str]:
    """Fan-out junctions reachable forward from ``start_id``."""
    result: set[str] = set()
    seen: set[str] = set()
    queue = [start_id]
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        if cur in graph.junction_ids:
            out_entries = [
                e2
                for e2 in graph.edges_from(cur)
                if (port := graph.ports.get(e2.target)) is not None and port.is_entry
            ]
            if len(out_entries) > 1:
                result.add(cur)
        for edge in graph.edges_from(cur):
            queue.append(edge.target)
    return result


def _entry_ports_for_junction(graph: MetroGraph, junction_id: str) -> list[str]:
    ports: list[str] = []
    for edge in graph.edges_to(junction_id):
        port = graph.ports.get(edge.source)
        if port is not None and port.is_entry:
            ports.append(edge.source)
    return ports


def _entry_ports_for_target_station(graph: MetroGraph, station_id: str) -> list[str]:
    """Entry ports fed from outside the target station's section."""
    station = graph.stations.get(station_id)
    if station is None or station.section_id is None:
        return []
    section_id = station.section_id
    ports: list[str] = []
    for pid, port in graph.ports.items():
        if not port.is_entry or port.section_id != section_id:
            continue
        for edge in graph.edges_to(pid):
            src = graph.stations.get(edge.source)
            if src is None or src.section_id == section_id:
                continue
            ports.append(pid)
            break
    return ports


def _junction_fanout_target_sections(graph: MetroGraph, junction_id: str) -> set[str]:
    sections: set[str] = set()
    for edge in graph.edges_from(junction_id):
        port = graph.ports.get(edge.target)
        if port is not None and port.is_entry and port.section_id is not None:
            sections.add(port.section_id)
    return sections


def resolve_route_channel_y_maps(
    graph: MetroGraph,
) -> tuple[dict[str, float], dict[str, float]]:
    """Resolve ``%%metro route_channel_y:`` rules to station-keyed Y maps."""
    from_map: dict[str, float] = {}
    to_map: dict[str, float] = {}
    for side, station_id, mode, section_ids in graph.route_channel_y_rules:
        if mode != "section_midpoint":
            continue
        channel_y = _section_band_midpoint(graph, section_ids)
        if channel_y is None:
            continue
        if side == "from":
            from_map[station_id] = channel_y
            allowed_sections = set(section_ids)
            for jid in _fanout_junction_ids_downstream(graph, station_id):
                target_sections = _junction_fanout_target_sections(graph, jid)
                if target_sections and target_sections.issubset(allowed_sections):
                    from_map[jid] = channel_y
        elif side == "to":
            to_map[station_id] = channel_y
            if station_id in graph.junction_ids:
                port_ids = _entry_ports_for_junction(graph, station_id)
            else:
                port_ids = _entry_ports_for_target_station(graph, station_id)
            for port_id in port_ids:
                to_map[port_id] = channel_y
    return from_map, to_map


def lookup_route_channel_y(
    from_map: dict[str, float],
    to_map: dict[str, float],
    source_id: str,
    target_id: str,
) -> float | None:
    """Return an authored channel Y for this edge, if any."""
    if source_id in from_map:
        return from_map[source_id]
    if target_id in to_map:
        return to_map[target_id]
    return None


def _sync_feeder_exit_ports(
    graph: MetroGraph, feeder_id: str, channel_y: float
) -> None:
    """Align RIGHT/LEFT exit ports fed from *feeder_id* to *channel_y*."""
    from nf_metro.layout.phases.ports import _set_port_y

    station = graph.stations.get(feeder_id)
    if station is None or station.section_id is None:
        return
    section = graph.sections.get(station.section_id)
    if section is None:
        return
    for pid in section.exit_ports:
        port = graph.ports.get(pid)
        if port is None or port.is_entry:
            continue
        if port.side not in (PortSide.LEFT, PortSide.RIGHT):
            continue
        for edge in graph.edges_to(pid):
            if edge.source != feeder_id:
                continue
            _set_port_y(graph, pid, channel_y)


def _refit_sections_after_route_channel_y(
    graph: MetroGraph,
    section_ids: set[str],
    section_y_padding: float,
) -> None:
    """Tighten section bboxes after a hub moves within its box."""
    from nf_metro.layout.phases._common import _pull_section_ports_to_edge
    from nf_metro.layout.phases.bbox import (
        _predict_section_content_bottom,
        _section_content_hug_top,
    )
    from nf_metro.layout.routing import compute_station_offsets

    offsets = compute_station_offsets(graph)
    for section_id in section_ids:
        section = graph.sections.get(section_id)
        if section is None or section.bbox_h <= 0:
            continue
        top = _section_content_hug_top(
            graph, section, section_y_padding, offsets
        )
        bottom = _predict_section_content_bottom(
            graph, section, section_y_padding, offsets
        )
        if top is None or bottom is None:
            continue
        section.bbox_y = top
        section.bbox_h = max(0.0, bottom - top)
        _pull_section_ports_to_edge(graph, section, PortSide.TOP, section.bbox_y)
        _pull_section_ports_to_edge(
            graph,
            section,
            PortSide.BOTTOM,
            section.bbox_y + section.bbox_h,
        )


def apply_route_channel_y_positions(
    graph: MetroGraph,
    section_y_padding: float = SECTION_Y_PADDING,
) -> None:
    """Seat ``route_channel_y: from`` sources at their authored channel Y.

    Runs after ``align_section_y`` so reference bands are settled, then
    re-anchors fan-out hubs and their exit ports before junction
    positioning.  Refits affected section bboxes to remove slack opened
    when a hub moves within its box.
    """
    if not graph.route_channel_y_rules:
        return

    from_map, _ = resolve_route_channel_y_maps(graph)
    if not from_map:
        return

    affected_sections: set[str] = set()
    for station_id, channel_y in from_map.items():
        if station_id in graph.junction_ids:
            continue
        station = graph.stations.get(station_id)
        if station is None:
            continue
        if abs(station.y - channel_y) <= 1e-6:
            continue
        station.y = channel_y
        if station.section_id:
            affected_sections.add(station.section_id)
        _sync_feeder_exit_ports(graph, station_id, channel_y)

    if affected_sections:
        _refit_sections_after_route_channel_y(
            graph, affected_sections, section_y_padding
        )
