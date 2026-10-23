import math

import pytest

from wheel_lab.core import (
    Side,
    WheelSpec,
    calculate_spoke_lengths,
    purchase_length_mm,
    spoke_length_mm,
)


def make_spec(**overrides):
    values = dict(
        erd_mm=600.0,
        left_flange_diameter_mm=45.0,
        right_flange_diameter_mm=45.0,
        left_flange_offset_mm=35.0,
        right_flange_offset_mm=19.0,
        hole_diameter_mm=2.6,
        spoke_count=32,
        crossings=3,
    )
    values.update(overrides)
    return WheelSpec(**values)


def test_brandt_equation_example():
    """Exemplo da p. 127: ERD 618, d 39, C 35,5, S 2,4, N 36, X 3."""
    length = spoke_length_mm(618, 39, 35.5, 2.4, 36, 3)
    assert length == pytest.approx(300.62, abs=0.01)


def test_symmetric_wheel_has_equal_lengths():
    spec = make_spec(left_flange_offset_mm=32.0, right_flange_offset_mm=32.0)
    result = calculate_spoke_lengths(spec)
    assert result.left_mm == pytest.approx(result.right_mm)
    assert result.angle_deg == pytest.approx(67.5)


def test_rear_wheel_right_side_is_shorter():
    result = calculate_spoke_lengths(make_spec())
    assert result.right_mm < result.left_mm
    assert result.left_purchase_mm == math.floor(result.left_mm)
    assert result.right_purchase_mm == math.floor(result.right_mm)


def test_purchase_length_rounds_down():
    assert purchase_length_mm(300.62) == 300
    assert purchase_length_mm(292.999999) == 292
    assert purchase_length_mm(300.0) == 300
    assert purchase_length_mm(301.0, step_mm=2.0) == 300


@pytest.mark.parametrize(
    "length",
    [0.0, -1.0, float("nan"), float("inf")],
)
def test_purchase_length_rejects_invalid(length):
    with pytest.raises(ValueError):
        purchase_length_mm(length)


def test_invalid_cross_pattern_is_rejected():
    spec = make_spec(spoke_count=28, crossings=4)
    with pytest.raises(ValueError, match="cruzamentos|cruzamento"):
        calculate_spoke_lengths(spec)


def test_radial_pattern_is_valid():
    spec = make_spec(spoke_count=32, crossings=0)
    result = calculate_spoke_lengths(spec)
    assert result.angle_deg == 0.0
    assert result.left_mm > 0


def test_flange_larger_than_erd_is_rejected():
    spec = make_spec(left_flange_diameter_mm=700.0)
    with pytest.raises(ValueError, match="flange"):
        calculate_spoke_lengths(spec)


def test_side_helpers():
    result = calculate_spoke_lengths(make_spec())
    assert result.length_for(Side.LEFT) == result.left_mm
    assert result.length_for(Side.RIGHT) == result.right_mm
    assert result.purchase_for(Side.LEFT) == result.left_purchase_mm
    assert result.purchase_for(Side.RIGHT) == result.right_purchase_mm
