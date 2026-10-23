import math

import pytest

from wheel_lab.core import (
    Side,
    lateral_tension_ratio,
    linear_density_kg_per_m,
    rim_compression_from_sides,
    rim_compression_n,
    spoke_elongation_mm,
    target_tensions,
    tension_from_tone_hz,
    tire_constriction_n,
    tone_frequency_hz,
)


def test_lateral_tension_ratio_rear_wheel():
    ratio = lateral_tension_ratio(35.0, 19.0, 292.919, 291.447)
    assert ratio == pytest.approx(0.5456, abs=0.001)
    assert ratio < 1.0  # lado direito mais tenso


def test_lateral_tension_ratio_symmetric_wheel():
    ratio = lateral_tension_ratio(32.0, 32.0, 290.0, 290.0)
    assert ratio == pytest.approx(1.0)


def test_target_tensions_right_tighter():
    tensions = target_tensions(1000.0, 0.5456, tighter_side=Side.RIGHT)
    assert tensions[Side.RIGHT] == pytest.approx(1000.0)
    assert tensions[Side.LEFT] == pytest.approx(545.6)


def test_target_tensions_left_tighter():
    tensions = target_tensions(1000.0, 1.84, tighter_side=Side.LEFT)
    assert tensions[Side.LEFT] == pytest.approx(1000.0)
    assert tensions[Side.RIGHT] == pytest.approx(1000.0 / 1.84)


def test_rim_compression_matches_book():
    # 36 raios a 1000 N => 5730 N (eq. 7)
    assert rim_compression_n([1000.0] * 36) == pytest.approx(5729.58, abs=0.1)


def test_rim_compression_mixed_tensions():
    assert rim_compression_n([1000.0, 500.0]) == pytest.approx(
        1500.0 / (2.0 * math.pi)
    )


def test_rim_compression_from_sides_expands_each_spoke():
    # 32 raios: 16 de cada lado. Não é a soma de apenas dois valores.
    expected = (16 * 546.0 + 16 * 1000.0) / (2.0 * math.pi)
    assert rim_compression_from_sides(546.0, 1000.0, 32) == pytest.approx(
        expected
    )
    assert rim_compression_from_sides(546.0, 1000.0, 32) > 1000.0


def test_spoke_elongation_matches_book():
    # Raio 1,6 mm, 290 mm, 1000 N => ~0,75 mm (eq. 3)
    assert spoke_elongation_mm(1000.0, 290.0, 1.6) == pytest.approx(
        0.75, abs=0.01
    )


def test_tone_and_tension_are_inverse():
    mu = linear_density_kg_per_m(2.0)
    frequency = tone_frequency_hz(1000.0, 290.0, mu)
    assert tension_from_tone_hz(frequency, 290.0, mu) == pytest.approx(1000.0)


def test_tire_constriction_matches_book():
    # 0,8 MPa, seção de 25 mm, cordas a 45° => ~392,7 N (eq. 8)
    assert tire_constriction_n(0.8e6, 25.0, 45.0) == pytest.approx(
        392.7, abs=0.1
    )


def test_tire_constriction_zero_near_equilibrium_angle():
    assert tire_constriction_n(0.8e6, 25.0, 35.27) == pytest.approx(
        0.0, abs=1.0
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: lateral_tension_ratio(0.0, 19.0, 290.0, 290.0),
        lambda: target_tensions(0.0, 1.0),
        lambda: rim_compression_n([-1.0]),
        lambda: spoke_elongation_mm(1000.0, 290.0, 0.0),
        lambda: tone_frequency_hz(0.0, 290.0, 0.02),
        lambda: tire_constriction_n(0.8e6, 25.0, 90.0),
    ],
)
def test_invalid_inputs(call):
    with pytest.raises(ValueError):
        call()
