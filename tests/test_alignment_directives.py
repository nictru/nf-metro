"""Tests for alignment directives: equal_width, hidden_section, align_y, align_section_y, distribute_y, route_channel_y, section_gap."""

from __future__ import annotations

import re

import pytest

from nf_metro.layout.engine import compute_layout
from nf_metro.layout.routing import compute_station_offsets, route_edges
from nf_metro.layout.routing.route_channel import (
    _section_band_midpoint,
    resolve_route_channel_y_maps,
)
from nf_metro.layout.section_placement import (
    _section_visual_bottom,
    _section_visual_top,
)
from nf_metro.parser.mermaid import parse_metro_mermaid
from nf_metro.render.svg import render_svg
from nf_metro.themes import NFCORE_THEME


def _layout(text: str):
    graph = parse_metro_mermaid(text)
    compute_layout(graph)
    return graph


def _layout_and_routes(text: str):
    graph = _layout(text)
    offsets = compute_station_offsets(graph)
    routes = route_edges(graph, station_offsets=offsets)
    return graph, routes


def _horizontal_segment_ys(points: list[tuple[float, float]]) -> list[float]:
    ys: list[float] = []
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        if abs(y1 - y2) < 0.5 and abs(x2 - x1) > 5.0:
            ys.append(y1)
    return ys


def _gaps_between_sections(section_ids: list[str], graph) -> list[float]:
    sections = [graph.sections[sid] for sid in section_ids]
    gaps = []
    for left, right in zip(sections, sections[1:], strict=False):
        gaps.append(_section_visual_top(right) - _section_visual_bottom(left))
    return gaps


def _section_box_rect(svg: str, section_id: str) -> tuple[float, float, float, float]:
    match = re.search(
        rf'<rect\b[^>]*data-section-id="{re.escape(section_id)}"[^>]*/?>',
        svg,
    )
    assert match, f"missing section box for {section_id!r}"
    tag = match.group(0)
    x = float(re.search(r'\bx="([0-9.]+)"', tag).group(1))
    y = float(re.search(r'\by="([0-9.]+)"', tag).group(1))
    w = float(re.search(r'\bwidth="([0-9.]+)"', tag).group(1))
    h = float(re.search(r'\bheight="([0-9.]+)"', tag).group(1))
    return x, y, w, h


def _rendered_section_gap(svg: str, upper_id: str, lower_id: str) -> float:
    _, uy, _, uh = _section_box_rect(svg, upper_id)
    _, ly, _, _ = _section_box_rect(svg, lower_id)
    return ly - (uy + uh)


class TestAlignmentDirectiveParsing:
    def test_equal_width_parsed(self):
        text = """%%metro line: a | A | #000
%%metro equal_width: left, right
graph LR
    subgraph left [Left]
        a1[A1] -->|a| a2[A2]
    end
    subgraph right [Right]
        b1[B1] -->|a| b2[B2]
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.equal_width_groups == [["left", "right"]]

    def test_hidden_section_parsed(self):
        text = """%%metro line: a | A | #000
%%metro hidden_section: merge
graph LR
    subgraph merge [ ]
        _m
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.sections["merge"].is_hidden

    def test_align_y_parsed(self):
        text = """%%metro line: a | A | #000
%%metro align_y: target | midpoint | ref_a, ref_b
graph LR
    ref_a[ ] -->|a| target[T]
    ref_b[ ] -->|a| target
"""
        graph = parse_metro_mermaid(text)
        assert graph.station_y_alignments["target"] == ("midpoint", ["ref_a", "ref_b"])

    def test_equal_width_requires_two_sections(self):
        text = "%%metro equal_width: only\ngraph LR\n"
        with pytest.warns(UserWarning, match="equal_width"):
            graph = parse_metro_mermaid(text)
        assert graph.equal_width_groups == []

    def test_distribute_y_parsed(self):
        text = """%%metro line: a | A | #000
%%metro distribute_y: top, mid, bot | even
graph LR
    subgraph top [Top]
        t1[T1] -->|a| t2[T2]
    end
    subgraph mid [Mid]
        m1[M1] -->|a| m2[M2]
    end
    subgraph bot [Bot]
        b1[B1] -->|a| b2[B2]
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.section_y_distributions == [
            (["top", "mid", "bot"], "even", None)
        ]

    def test_distribute_y_parsed_with_gap(self):
        text = """%%metro line: a | A | #000
%%metro distribute_y: top, mid, bot | even | 50
graph LR
    subgraph top [Top]
        t1[T1] -->|a| t2[T2]
    end
    subgraph mid [Mid]
        m1[M1] -->|a| m2[M2]
    end
    subgraph bot [Bot]
        b1[B1] -->|a| b2[B2]
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.section_y_distributions == [
            (["top", "mid", "bot"], "even", 50.0)
        ]

    def test_distribute_y_requires_two_sections(self):
        text = "%%metro distribute_y: only | even\ngraph LR\n"
        with pytest.warns(UserWarning, match="distribute_y"):
            graph = parse_metro_mermaid(text)
        assert graph.section_y_distributions == []

    def test_distribute_y_rejects_unknown_mode(self):
        text = "%%metro distribute_y: a, b | packed\ngraph LR\n"
        with pytest.warns(UserWarning, match="distribute_y"):
            graph = parse_metro_mermaid(text)
        assert graph.section_y_distributions == []

    def test_route_channel_y_from_parsed(self):
        text = """%%metro line: a | A | #000
%%metro route_channel_y: from _done | section_midpoint | top, mid, bot
graph LR
    _done[ ]
"""
        graph = parse_metro_mermaid(text)
        assert graph.route_channel_y_rules == [
            ("from", "_done", "section_midpoint", ["top", "mid", "bot"])
        ]

    def test_route_channel_y_to_parsed(self):
        text = """%%metro line: a | A | #000
%%metro route_channel_y: to _merge | section_midpoint | top, mid
graph LR
    _merge[ ]
"""
        graph = parse_metro_mermaid(text)
        assert graph.route_channel_y_rules == [
            ("to", "_merge", "section_midpoint", ["top", "mid"])
        ]

    def test_route_channel_y_rejects_unknown_mode(self):
        text = "%%metro route_channel_y: from _done | center | top\ngraph LR\n"
        with pytest.warns(UserWarning, match="route_channel_y"):
            graph = parse_metro_mermaid(text)
        assert graph.route_channel_y_rules == []

    def test_align_section_y_parsed(self):
        text = """%%metro line: a | A | #000
%%metro align_section_y: prep | section_midpoint | top, mid | _done
graph LR
    subgraph prep [Prep]
        _done[ ]
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.section_y_alignments == [
            (["prep"], "section_midpoint", ["top", "mid"], "_done")
        ]

    def test_align_section_y_parsed_multiple_targets(self):
        text = """%%metro line: a | A | #000
%%metro align_section_y: post, merge | section_midpoint | top, mid, bot | _merge
graph LR
    _merge[ ]
"""
        graph = parse_metro_mermaid(text)
        assert graph.section_y_alignments == [
            (
                ["post", "merge"],
                "section_midpoint",
                ["top", "mid", "bot"],
                "_merge",
            )
        ]

    def test_align_section_y_rejects_unknown_mode(self):
        text = "%%metro align_section_y: prep | center | top\ngraph LR\n"
        with pytest.warns(UserWarning, match="align_section_y"):
            graph = parse_metro_mermaid(text)
        assert graph.section_y_alignments == []

    def test_section_gap_parsed(self):
        text = """%%metro line: a | A | #000
%%metro section_gap: reporting | postprocessing | 50
graph LR
    subgraph postprocessing [Post]
        p1[P]
    end
    subgraph reporting [Report]
        r1[R]
    end
"""
        graph = parse_metro_mermaid(text)
        assert graph.section_y_gaps == [("reporting", "postprocessing", 50.0)]

    def test_section_gap_rejects_missing_fields(self):
        text = "%%metro section_gap: only\ngraph LR\n"
        with pytest.warns(UserWarning, match="section_gap"):
            graph = parse_metro_mermaid(text)
        assert graph.section_y_gaps == []

    def test_section_gap_rejects_non_numeric_gap(self):
        text = "%%metro section_gap: a | b | wide\ngraph LR\n"
        with pytest.warns(UserWarning, match="section_gap"):
            graph = parse_metro_mermaid(text)
        assert graph.section_y_gaps == []


class TestHiddenSection:
    HIDDEN_MAP = """%%metro line: a | A | #4CAF50
%%metro hidden_section: merge
graph LR
    subgraph prep [Prep]
        %%metro exit: right | a
        in[In] -->|a| out[Out]
    end

    subgraph merge [ ]
        _merge
    end

    subgraph post [Post]
        %%metro entry: left | a
        fin[Fin]
    end

    out -->|a| _merge
    _merge -->|a| fin
"""

    def test_hidden_section_not_numbered(self):
        graph = _layout(self.HIDDEN_MAP)
        visible = [s for s in graph.sections.values() if s.is_visible]
        numbers = sorted(s.number for s in visible)
        assert numbers == [1, 2]
        assert graph.sections["merge"].number == 0

    def test_hidden_section_not_rendered(self):
        graph = _layout(self.HIDDEN_MAP)
        svg = render_svg(graph, NFCORE_THEME)
        assert 'data-section-id="merge"' not in svg
        assert 'data-section-id="prep"' in svg
        assert 'data-section-id="post"' in svg


class TestEqualWidth:
    EQUAL_WIDTH_MAP = """%%metro line: a | A | #4CAF50
%%metro equal_width: narrow, wide
graph LR
    subgraph narrow [N]
        %%metro exit: right | a
        n1[N1] -->|a| n2[N2]
    end

    subgraph wide [Wide Section Name]
        %%metro entry: left | a
        %%metro exit: right | a
        w1[Wide One] -->|a| w2[Wide Two]
        w2 -->|a| w3[Wide Three]
    end
"""

    def test_equal_width_sections_match(self):
        graph = _layout(self.EQUAL_WIDTH_MAP)
        narrow = graph.sections["narrow"]
        wide = graph.sections["wide"]
        assert narrow.bbox_w == wide.bbox_w


class TestDistributeY:
    DISTRIBUTE_MAP = """%%metro line: a | A | #4CAF50
%%metro grid: tall | 0,2
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro distribute_y: top, mid, bot | even
graph LR
    subgraph tall [Tall]
        t_in[Input A]
        t_mid[Middle Step]
        t_out[Output A]
        t_in -->|a| t_mid
        t_mid -->|a| t_out
    end

    subgraph top [Top]
        top_a[A1] -->|a| top_b[A2]
    end

    subgraph mid [Mid]
        mid_a[B1] -->|a| mid_b[B2]
    end

    subgraph bot [Bot]
        bot_a[C1] -->|a| bot_b[C2]
    end
"""

    DISTRIBUTE_WITH_HIDDEN = """%%metro line: a | A | #4CAF50
%%metro hidden_section: hidden
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro distribute_y: top, mid, bot | even
graph LR
    subgraph top [Top]
        top_a[A1] -->|a| top_b[A2]
    end

    subgraph hidden [ ]
        _hidden
    end

    subgraph mid [Mid]
        mid_a[B1] -->|a| mid_b[B2]
    end

    subgraph bot [Bot]
        bot_a[C1] -->|a| bot_b[C2]
    end
"""

    def test_distribute_y_even_gaps(self):
        graph = _layout(self.DISTRIBUTE_MAP)
        gaps = _gaps_between_sections(["top", "mid", "bot"], graph)
        assert len(gaps) == 2
        assert gaps[0] == pytest.approx(gaps[1])

    def test_distribute_y_fixed_gap(self):
        text = self.DISTRIBUTE_MAP.replace(
            "%%metro distribute_y: top, mid, bot | even",
            "%%metro distribute_y: top, mid, bot | even | 50",
        )
        graph = _layout(text)
        gaps = _gaps_between_sections(["top", "mid", "bot"], graph)
        assert gaps == [pytest.approx(50.0), pytest.approx(50.0)]

    def test_distribute_y_fixed_gap_shifts_downstream_sections(self):
        text = """%%metro line: a | A | #4CAF50
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro grid: downstream | 2,4
%%metro distribute_y: top, mid, bot | even | 50
graph LR
    subgraph top [Top]
        top_a[A1] -->|a| top_b[A2]
    end
    subgraph mid [Mid]
        mid_a[B1] -->|a| mid_b[B2]
    end
    subgraph bot [Bot]
        bot_a[C1] -->|a| bot_b[C2]
    end
    subgraph downstream [Down]
        %%metro entry: left | a
        down_a[Down]
    end
    top_b -->|a| down_a
"""
        without = text.replace(
            "%%metro distribute_y: top, mid, bot | even | 50\n", ""
        )
        graph_without = _layout(without)
        graph_with = _layout(text)
        delta = (
            graph_with.sections["downstream"].bbox_y
            - graph_without.sections["downstream"].bbox_y
        )
        assert delta < 0

    def test_distribute_y_leaves_unlisted_sections_unmoved(self):
        without = """%%metro line: a | A | #4CAF50
%%metro grid: tall | 0,2
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
graph LR
    subgraph tall [Tall]
        t_in[Input A]
        t_mid[Middle Step]
        t_out[Output A]
        t_in -->|a| t_mid
        t_mid -->|a| t_out
    end
    subgraph top [Top]
        top_a[A1] -->|a| top_b[A2]
    end
    subgraph mid [Mid]
        mid_a[B1] -->|a| mid_b[B2]
    end
    subgraph bot [Bot]
        bot_a[C1] -->|a| bot_b[C2]
    end
"""
        with_directive = without.replace(
            "%%metro grid: bot | 1,4",
            "%%metro grid: bot | 1,4\n%%metro distribute_y: top, mid, bot | even",
        )
        graph_without = _layout(without)
        graph_with = _layout(with_directive)
        assert graph_with.sections["tall"].offset_y == pytest.approx(
            graph_without.sections["tall"].offset_y
        )


class TestAlignY:
    ALIGN_Y_MAP = """%%metro line: a | A | #4CAF50
%%metro off_track: top_a, top_b
%%metro align_y: middle | midpoint | top_a, top_b
graph LR
    subgraph prep [Prep]
        top_a[ ]
        top_b[ ]
        middle[Middle]
        top_a -->|a| middle
        top_b -->|a| middle
    end
"""

    def test_align_y_midpoint(self):
        graph = _layout(self.ALIGN_Y_MAP)
        top_a = graph.stations["top_a"]
        top_b = graph.stations["top_b"]
        middle = graph.stations["middle"]
        expected = (top_a.y + top_b.y) / 2
        assert middle.y == pytest.approx(expected)

    def test_align_y_routes_from_aligned_position(self):
        graph = _layout(self.ALIGN_Y_MAP)
        svg = render_svg(graph, NFCORE_THEME)
        middle_y = graph.stations["middle"].y
        top_a_y = graph.stations["top_a"].y
        assert re.search(rf"M[0-9.]+,{top_a_y:.1f}", svg)
        assert re.search(rf"L[0-9.]+,{middle_y:.1f}", svg)


class TestRouteChannelY:
    BASE_MAP = """%%metro line: a | A | #4CAF50
%%metro grid: prep | 0,2
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro grid: convergence | 2,4
%%metro grid: post | 3,4
%%metro distribute_y: top, mid, bot | even | 50
%%metro hidden_section: convergence
{directives}graph LR
    subgraph prep [Prep]
        %%metro exit: right | a
        in[In] -->|a| _done
    end
    subgraph top [Top]
        %%metro entry: left | a
        %%metro exit: right | a
        top_a[A] -->|a| top_b[B]
    end
    subgraph mid [Mid]
        %%metro entry: left | a
        %%metro exit: right | a
        mid_a[C] -->|a| mid_b[D]
    end
    subgraph bot [Bot]
        %%metro entry: left | a
        %%metro exit: right | a
        bot_a[E] -->|a| bot_b[F]
    end
    subgraph convergence [ ]
        %%metro entry: left | a
        _merge
    end
    subgraph post [Post]
        %%metro entry: left | a
        fin[Fin]
    end
    _done -->|a| top_a
    _done -->|a| mid_a
    _done -->|a| bot_a
    top_b -->|a| _merge
    mid_b -->|a| _merge
    bot_b -->|a| _merge
    _merge -->|a| fin
"""

    DIRECTIVES = """%%metro route_channel_y: from _done | section_midpoint | top, mid, bot
%%metro route_channel_y: to _merge | section_midpoint | top, mid, bot
"""

    def _map(self, *, with_directives: bool) -> str:
        directives = self.DIRECTIVES if with_directives else ""
        return self.BASE_MAP.format(directives=directives)

    def test_section_midpoint_resolves(self):
        graph = _layout(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        from_map, to_map = resolve_route_channel_y_maps(graph)
        assert from_map["_done"] == pytest.approx(expected)
        assert to_map["_merge"] == pytest.approx(expected)

    def test_fan_out_uses_centered_channel(self):
        graph, routes = _layout_and_routes(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        junction_ids = {
            jid
            for jid in graph.junction_ids
            if any(
                graph.ports.get(e.target) is not None
                and graph.ports[e.target].section_id == "top"
                for e in graph.edges_from(jid)
            )
        }
        assert junction_ids
        fan_routes = [
            r
            for r in routes
            if r.edge is not None
            and r.edge.source in junction_ids
            and graph.ports.get(r.edge.target) is not None
            and graph.ports[r.edge.target].section_id == "top"
        ]
        assert fan_routes
        ys = [p[1] for p in fan_routes[0].points]
        assert any(abs(y - expected) < 1.0 for y in ys)

    def test_fan_in_uses_centered_channel(self):
        graph, routes = _layout_and_routes(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        entry_ports = [
            pid
            for pid, port in graph.ports.items()
            if port.is_entry and port.section_id == "convergence"
        ]
        fan_routes = [
            r
            for r in routes
            if r.edge is not None
            and r.edge.target in entry_ports
            and graph.stations[r.edge.source].section_id == "top"
        ]
        assert fan_routes
        ys = [p[1] for p in fan_routes[0].points]
        assert any(abs(y - expected) < 1.0 for y in ys)

    def test_merge_entry_port_inherits_channel_y(self):
        graph = _layout(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        _from_map, to_map = resolve_route_channel_y_maps(graph)
        entry_ports = [
            pid
            for pid, port in graph.ports.items()
            if port.is_entry and port.section_id == "convergence"
        ]
        assert entry_ports
        for pid in entry_ports:
            assert to_map[pid] == pytest.approx(expected)


class TestRouteChannelYPositioning:
    """Late layout pass seats fan-out hubs on the authored channel Y."""

    MAP = """%%metro line: a | A | #4CAF50
%%metro grid: prep | 0,2
%%metro grid: top | 1,0
%%metro grid: bot | 1,4
%%metro distribute_y: top, bot | even | 50
%%metro route_channel_y: from _done | section_midpoint | top, bot
%%metro align_section_y: prep | section_midpoint | top, bot
graph LR
    subgraph prep [Prep]
        %%metro exit: right | a
        top_in[TopIn] -->|a| _done
        bot_in[BotIn] -->|a| _done
    end
    subgraph top [Top]
        %%metro entry: left | a
        top_a[A] -->|a| top_b[B]
    end
    subgraph bot [Bot]
        %%metro entry: left | a
        bot_a[C] -->|a| bot_b[D]
    end
    _done -->|a| top_a
    _done -->|a| bot_a
"""

    def test_fanout_hub_seated_on_channel_y(self):
        graph = _layout(self.MAP)
        expected = _section_band_midpoint(graph, ["top", "bot"])
        assert expected is not None
        assert graph.stations["_done"].y == pytest.approx(expected, abs=1.0)
        exit_port = graph.sections["prep"].exit_ports[0]
        assert graph.stations[exit_port].y == pytest.approx(expected, abs=1.0)

    def test_fanout_routes_without_channel_detour(self):
        graph, routes = _layout_and_routes(self.MAP)
        expected = _section_band_midpoint(graph, ["top", "bot"])
        assert expected is not None
        prep_exit_x = max(
            graph.stations[pid].x
            for pid in graph.sections["prep"].exit_ports
        )
        entry_ports = [
            pid
            for pid, port in graph.ports.items()
            if port.is_entry and port.section_id == "top"
        ]
        fan_routes = [
            r
            for r in routes
            if r.edge is not None
            and r.edge.target in entry_ports
            and (
                r.edge.source == "_done"
                or r.edge.source in graph.junction_ids
            )
        ]
        assert fan_routes
        points = fan_routes[0].points
        first_gap_y = None
        for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
            if (
                abs(y1 - y2) < 0.5
                and abs(x2 - x1) > 5.0
                and x1 >= prep_exit_x - 1.0
            ):
                first_gap_y = y1
                break
        assert first_gap_y is not None
        assert abs(first_gap_y - expected) < 2.0

    def test_section_bbox_tightens_below_hub(self):
        graph = _layout(self.MAP)
        done_y = graph.stations["_done"].y
        prep = graph.sections["prep"]
        slack = prep.bbox_y + prep.bbox_h - done_y
        lowest = max(
            graph.stations[sid].y
            for sid in prep.station_ids
            if sid in graph.stations and not graph.stations[sid].is_port
        )
        assert slack < lowest - done_y + 60.0


class TestAlignSectionY:
    BASE_MAP = """%%metro line: a | A | #4CAF50
%%metro grid: prep | 0,2
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro grid: convergence | 2,4
%%metro grid: post | 3,4
%%metro distribute_y: top, mid, bot | even | 50
%%metro hidden_section: convergence
{directives}graph LR
    subgraph prep [Prep]
        %%metro exit: right | a
        in[In] -->|a| _done
    end
    subgraph top [Top]
        %%metro entry: left | a
        %%metro exit: right | a
        top_a[A] -->|a| top_b[B]
    end
    subgraph mid [Mid]
        %%metro entry: left | a
        %%metro exit: right | a
        mid_a[C] -->|a| mid_b[D]
    end
    subgraph bot [Bot]
        %%metro entry: left | a
        %%metro exit: right | a
        bot_a[E] -->|a| bot_b[F]
    end
    subgraph convergence [ ]
        %%metro entry: left | a
        _merge
    end
    subgraph post [Post]
        %%metro entry: left | a
        fin[Fin]
    end
    _done -->|a| top_a
    _done -->|a| mid_a
    _done -->|a| bot_a
    top_b -->|a| _merge
    mid_b -->|a| _merge
    bot_b -->|a| _merge
    _merge -->|a| fin
"""

    DIRECTIVES = """%%metro align_section_y: prep | section_midpoint | top, mid, bot | _done
%%metro align_section_y: post, convergence | section_midpoint | top, mid, bot | _merge
"""

    def _map(self, *, with_directives: bool) -> str:
        directives = self.DIRECTIVES if with_directives else ""
        return self.BASE_MAP.format(directives=directives)

    def test_anchor_stations_align_to_band_midpoint(self):
        graph = _layout(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        assert graph.stations["_done"].y == pytest.approx(expected, abs=1.0)
        assert graph.stations["_merge"].y == pytest.approx(expected, abs=1.0)

    def test_fan_out_starts_near_band_midpoint(self):
        graph, routes = _layout_and_routes(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        assert graph.stations["_done"].y == pytest.approx(expected, abs=1.0)
        entry_ports = [
            pid
            for pid, port in graph.ports.items()
            if port.is_entry and port.section_id == "top"
        ]
        fan_routes = [
            r
            for r in routes
            if r.edge is not None
            and r.edge.target in entry_ports
            and (
                r.edge.source == "_done"
                or r.edge.source in graph.junction_ids
            )
        ]
        assert fan_routes
        horiz_ys = _horizontal_segment_ys(fan_routes[0].points)
        assert horiz_ys
        assert any(abs(y - expected) < 2.0 for y in horiz_ys)

    def test_fan_in_ends_near_band_midpoint_without_detour_spike(self):
        graph, routes = _layout_and_routes(self._map(with_directives=True))
        expected = _section_band_midpoint(graph, ["top", "mid", "bot"])
        assert expected is not None
        merge_y = graph.stations["_merge"].y
        assert merge_y == pytest.approx(expected, abs=1.0)
        entry_ports = [
            pid
            for pid, port in graph.ports.items()
            if port.is_entry and port.section_id == "convergence"
        ]
        fan_routes = [
            r
            for r in routes
            if r.edge is not None
            and r.edge.target in entry_ports
            and graph.stations[r.edge.source].section_id == "top"
        ]
        assert fan_routes
        points = fan_routes[0].points
        end_y = points[-1][1]
        assert end_y == pytest.approx(expected, abs=2.0)
        horiz_ys = _horizontal_segment_ys(points)
        assert horiz_ys
        assert any(abs(y - expected) < 2.0 for y in horiz_ys)


class TestSectionGap:
    BASE_MAP = """%%metro line: a | A | #4CAF50
%%metro grid: prep | 0,2
%%metro grid: top | 1,0
%%metro grid: mid | 1,2
%%metro grid: bot | 1,4
%%metro grid: convergence | 2,4
%%metro grid: post | 3,4
%%metro grid: report | 3,5
%%metro distribute_y: top, mid, bot | even | 50
%%metro hidden_section: convergence
%%metro align_section_y: post | section_midpoint | top, mid, bot | _merge
{directives}graph LR
    subgraph prep [Prep]
        %%metro exit: right | a
        in[In] -->|a| _done
    end
    subgraph top [Top]
        %%metro entry: left | a
        %%metro exit: right | a
        top_a[A] -->|a| top_b[B]
    end
    subgraph mid [Mid]
        %%metro entry: left | a
        %%metro exit: right | a
        mid_a[C] -->|a| mid_b[D]
    end
    subgraph bot [Bot]
        %%metro entry: left | a
        %%metro exit: right | a
        bot_a[E] -->|a| bot_b[F]
    end
    subgraph convergence [ ]
        %%metro entry: left | a
        _merge
    end
    subgraph post [Post]
        %%metro entry: left | a
        fin[Fin]
    end
    subgraph report [Report]
        %%metro entry: left | a
        rep[Rep]
    end
    _done -->|a| top_a
    _done -->|a| mid_a
    _done -->|a| bot_a
    top_b -->|a| _merge
    mid_b -->|a| _merge
    bot_b -->|a| _merge
    _merge -->|a| fin
    _merge -->|a| rep
"""

    DIRECTIVES = "%%metro section_gap: report | post | 50\n"

    def _map(self, *, with_directives: bool) -> str:
        directives = self.DIRECTIVES if with_directives else ""
        return self.BASE_MAP.format(directives=directives)

    def test_section_gap_matches_aligner_spacing(self):
        graph = _layout(self._map(with_directives=True))
        gap = _gaps_between_sections(["post", "report"], graph)[0]
        assert gap == pytest.approx(50.0)

    def test_section_gap_runs_after_align_section_y(self):
        without = _layout(self._map(with_directives=False))
        with_gap = _layout(self._map(with_directives=True))
        without_gap = _gaps_between_sections(["post", "report"], without)[0]
        with_fixed = _gaps_between_sections(["post", "report"], with_gap)[0]
        assert without_gap > with_fixed
        assert with_fixed == pytest.approx(50.0)

    def test_section_gap_matches_rendered_section_boxes(self):
        graph = _layout(self._map(with_directives=True))
        svg = render_svg(graph, NFCORE_THEME)
        gap = _rendered_section_gap(svg, "post", "report")
        assert gap == pytest.approx(50.0, abs=1.0)


class TestAlignStationToSection:
    MAP = """%%metro line: a | A | #4CAF50
%%metro off_track: barcode_in
%%metro grid: aligner | 1,2
%%metro align_y: barcode_in | midpoint | first_step, last_step
graph LR
    subgraph aligner [Aligner]
        %%metro entry: left | a
        first_step[First] -->|a| middle[Middle]
        middle -->|a| last_step[Last]
    end
    barcode_in[ ]
    barcode_in -->|a| first_step
"""

    def test_off_track_input_aligns_to_section_midline(self):
        graph = _layout(self.MAP)
        first = graph.stations["first_step"]
        last = graph.stations["last_step"]
        barcode = graph.stations["barcode_in"]
        expected = (first.y + last.y) / 2
        assert barcode.y == pytest.approx(expected)
        section = graph.sections["aligner"]
        section_mid = section.bbox_y + section.bbox_h / 2
        assert barcode.y == pytest.approx(section_mid, abs=1.0)


class TestAlignYInterSectionRoute:
    MAP = """%%metro line: a | A | #4CAF50
%%metro off_track: barcode_in
%%metro grid: aligner | 1,2
%%metro align_y: barcode_in | midpoint | first_step, last_step
graph LR
    subgraph aligner [Aligner]
        %%metro entry: left | a
        first_step[First] -->|a| middle[Middle]
        middle -->|a| last_step[Last]
    end
    barcode_in[ ]
    barcode_in -->|a| first_step
"""

    def test_off_track_exit_port_matches_aligned_station_y(self):
        graph = _layout(self.MAP)
        barcode = graph.stations["barcode_in"]
        exit_ports = [
            graph.ports[pid]
            for pid in graph.sections["__implicit__"].exit_ports
            if pid in graph.ports
        ]
        assert exit_ports, "expected an implicit-section exit port"
        assert all(abs(port.y - barcode.y) < 1.0 for port in exit_ports)

    def test_off_track_to_section_entry_is_horizontal(self):
        graph, routes = _layout_and_routes(self.MAP)
        barcode_y = graph.stations["barcode_in"].y
        inter_routes = [
            route
            for route in routes
            if route.is_inter_section
            and route.edge.source.startswith("__implicit__")
            and "aligner" in route.edge.target
        ]
        assert inter_routes, "expected inter-section route into aligner"
        for route in inter_routes:
            horiz = _horizontal_segment_ys(route.points)
            assert horiz, f"expected horizontal run, got {route.points}"
            assert all(abs(y - barcode_y) < 1.0 for y in horiz)
