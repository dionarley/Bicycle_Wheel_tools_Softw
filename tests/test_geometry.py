import pytest

from wheel_lab.core import (
    erd_from_outer_diameter,
    is_valid_cross_pattern,
    max_crossings,
    spoke_angle_deg,
)


def test_spoke_angle_values():
    assert spoke_angle_deg(36, 3) == pytest.approx(60.0)
    assert spoke_angle_deg(32, 3) == pytest.approx(67.5)
    assert spoke_angle_deg(36, 4) == pytest.approx(80.0)
    assert spoke_angle_deg(32, 0) == 0.0


def test_max_crossings():
    assert max_crossings(24) == 3
    assert max_crossings(28) == 3
    assert max_crossings(32) == 4
    assert max_crossings(36) == 4
    assert max_crossings(48) == 6


def test_cross_pattern_validation():
    assert is_valid_cross_pattern(28, 3)
    assert not is_valid_cross_pattern(28, 4)
    assert is_valid_cross_pattern(32, 4)
    assert not is_valid_cross_pattern(32, 5)
    assert is_valid_cross_pattern(36, 0)


def test_spoke_angle_rejects_invalid():
    with pytest.raises(ValueError):
        spoke_angle_deg(28, 4)
    with pytest.raises(ValueError):
        spoke_angle_deg(31, 3)
    with pytest.raises(ValueError):
        spoke_angle_deg(32, -1)


def test_erd_from_outer_diameter():
    assert erd_from_outer_diameter(622.0, 9.0) == pytest.approx(604.0)
    assert erd_from_outer_diameter(600.0, 0.0) == pytest.approx(600.0)


def test_erd_rejects_invalid():
    with pytest.raises(ValueError):
        erd_from_outer_diameter(0.0, 9.0)
    with pytest.raises(ValueError):
        erd_from_outer_diameter(622.0, -1.0)
    with pytest.raises(ValueError):
        erd_from_outer_diameter(10.0, 9.0)
