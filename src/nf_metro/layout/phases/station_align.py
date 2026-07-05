"""Author-directed station Y alignment."""

from __future__ import annotations

from nf_metro.parser.model import MetroGraph


def apply_station_y_alignments(graph: MetroGraph) -> None:
    """Apply ``%%metro align_y:`` directives after layout has settled.

    Runs late in the layout pipeline so off-track reference stations have
    their final Y before a target station is centred between them.
    """
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
