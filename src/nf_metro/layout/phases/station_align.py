"""Author-directed station Y alignment."""

from __future__ import annotations

from nf_metro.layout.constants import SECTION_Y_PADDING
from nf_metro.parser.model import MetroGraph, PortSide


def apply_station_y_alignments(
    graph: MetroGraph,
    section_y_padding: float = SECTION_Y_PADDING,
) -> None:
    """Apply ``%%metro align_y:`` directives after layout has settled.

    Runs late in the layout pipeline so off-track reference stations have
    their final Y before a target station is centred between them.
    """
    aligned_off_track: set[str] = set()
    for station_id, (mode, ref_ids) in graph.station_y_alignments.items():
        target = graph.stations.get(station_id)
        if target is None:
            continue
        ref_ys = [
            graph.stations[ref_id].y
            for ref_id in ref_ids
            if ref_id in graph.stations
        ]
        if not ref_ys:
            continue
        if mode == "midpoint":
            target.y = sum(ref_ys) / len(ref_ys)
            if target.off_track:
                aligned_off_track.add(station_id)

    if aligned_off_track:
        _refit_off_track_sections_after_align_y(
            graph, aligned_off_track, section_y_padding
        )


def _refit_off_track_sections_after_align_y(
    graph: MetroGraph,
    aligned_station_ids: set[str],
    section_y_padding: float,
) -> None:
    """Re-seat implicit/off-track section bboxes and exit ports after ``align_y``.

    ``align_y`` can move an off-track input far from the consumer Y it was
    anchored to during Stage 5.2.  Its section bbox and RIGHT/LEFT exit port
    still reflect the pre-align placement, which kinks the inter-section run.
    Sync each feeder exit port to the aligned station Y first, then refit the
    section bbox around the settled content.
    """
    from nf_metro.layout.phases._common import _pull_section_ports_to_edge
    from nf_metro.layout.phases.bbox import (
        _predict_section_content_bottom,
        _section_content_hug_top,
    )
    from nf_metro.layout.phases.ports import _set_port_y
    from nf_metro.layout.routing import compute_station_offsets

    affected_sections: set[str] = set()
    for station_id in aligned_station_ids:
        station = graph.stations.get(station_id)
        if station and station.section_id:
            affected_sections.add(station.section_id)

    offsets = compute_station_offsets(graph)
    for section_id in affected_sections:
        section = graph.sections.get(section_id)
        if section is None or section.bbox_h <= 0:
            continue

        for pid in section.exit_ports:
            port = graph.ports.get(pid)
            if port is None or port.side not in (PortSide.LEFT, PortSide.RIGHT):
                continue
            for edge in graph.edges_to(pid):
                if edge.source not in aligned_station_ids:
                    continue
                feeder = graph.stations.get(edge.source)
                if feeder is None or not feeder.off_track:
                    continue
                _set_port_y(graph, pid, feeder.y)

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
