from __future__ import annotations

import pytest

from cmfgen_viewer.parsers import common


def test_parse_float_token_supports_fortran_formats() -> None:
    assert common.parse_float_token("2.5D+03") == 2500.0
    assert common.parse_float_token("3.9241-115") == pytest.approx(3.9241e-115)
    assert common.parse_float_token("not-a-number") is None


def test_parse_numeric_tokens_is_all_or_nothing() -> None:
    assert common.parse_numeric_tokens("1 2 3") == [1.0, 2.0, 3.0]
    assert common.parse_numeric_tokens("1 2 bad") == []


def test_parse_key_value_pairs_extracts_multiple_entries() -> None:
    pairs = common.parse_key_value_pairs("RMAX = 1.0E+12   Mdot = 3.0D-6")
    assert pairs == [("RMAX", "1.0E+12"), ("Mdot", "3.0D-6")]


def test_maybe_number_parses_ints_floats_and_text() -> None:
    assert common.maybe_number("2.0") == 2
    assert common.maybe_number("2.5") == 2.5
    assert common.maybe_number("abc") == "abc"


def test_downsample_xy_limits_points_and_keeps_last() -> None:
    x = list(range(2000))
    y = [value * 2 for value in x]
    sampled_x, sampled_y = common.downsample_xy(x, y, max_points=100)

    assert len(sampled_x) == 100
    assert len(sampled_y) == 100
    assert sampled_x[0] == 0
    assert sampled_x[-1] == 1999
    assert sampled_y[-1] == 3998


def test_build_plotly_line_plot_requires_at_least_two_points() -> None:
    assert (
        common.build_plotly_line_plot(
            [1.0],
            [2.0],
            x_label="x",
            y_label="y",
        )
        is None
    )

    plot = common.build_plotly_line_plot(
        [1.0, 2.0, 3.0],
        [10.0, 20.0, 30.0],
        x_label="x",
        y_label="y",
    )
    assert plot is not None
    assert plot["point_count"] == 3
