import pytest

from wheel_lab.core import WheelSpec, calculate_spoke_lengths


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
        rim_offset_mm=0.0,
        locknut_spacing_mm=130.0,
    )
    values.update(overrides)
    return WheelSpec(**values)


def test_centered_wheel_has_zero_dish():
    spec = make_spec()
    assert spec.is_centered
    assert spec.hub_center_mm == pytest.approx(0.0)
    assert spec.centering_correction_mm == pytest.approx(0.0)
    assert spec.effective_left_offset_mm == pytest.approx(35.0)
    assert spec.effective_right_offset_mm == pytest.approx(19.0)


def test_centering_tolerance_is_half_millimeter():
    assert make_spec(rim_offset_mm=0.5).is_centered
    assert not make_spec(rim_offset_mm=0.51).is_centered


def test_positive_dish_shifts_effective_offsets():
    spec = make_spec(rim_offset_mm=2.0)
    assert spec.effective_left_offset_mm == pytest.approx(37.0)
    assert spec.effective_right_offset_mm == pytest.approx(17.0)
    assert spec.hub_center_mm == pytest.approx(-2.0)
    assert spec.centering_correction_mm == pytest.approx(-2.0)
    assert not spec.is_centered


def test_flange_and_locknut_positions_relative_to_rim():
    spec = make_spec(rim_offset_mm=2.0)
    assert spec.flange_positions_mm() == pytest.approx((-37.0, 17.0))
    assert spec.locknut_positions_mm() == pytest.approx((-67.0, 63.0))


def test_dish_changes_spoke_lengths():
    centered = calculate_spoke_lengths(make_spec())
    shifted = calculate_spoke_lengths(make_spec(rim_offset_mm=2.0))
    assert shifted.left_mm > centered.left_mm
    assert shifted.right_mm < centered.right_mm


def test_negative_dish_moves_rim_left():
    spec = make_spec(rim_offset_mm=-1.5)
    assert spec.effective_left_offset_mm == pytest.approx(33.5)
    assert spec.effective_right_offset_mm == pytest.approx(20.5)
    assert spec.centering_correction_mm == pytest.approx(1.5)
    assert spec.hub_center_mm == pytest.approx(1.5)


def test_dish_beyond_flange_is_rejected():
    spec = make_spec(rim_offset_mm=19.0)
    with pytest.raises(ValueError, match="dish|flange"):
        calculate_spoke_lengths(spec)


def test_invalid_locknut_spacing_is_rejected():
    spec = make_spec(locknut_spacing_mm=0.0)
    with pytest.raises(ValueError, match="locknuts"):
        spec.validate()


def test_locknut_spacing_is_optional():
    spec = make_spec(locknut_spacing_mm=None)
    assert spec.locknut_positions_mm() is None
    spec.validate()
