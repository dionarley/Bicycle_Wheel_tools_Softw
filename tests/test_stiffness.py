import pytest

from wheel_lab.core import (
    TruingState,
    WheelSpec,
    estimate_wheel_stiffness,
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
        rim_offset_mm=0.0,
        locknut_spacing_mm=130.0,
    )
    values.update(overrides)
    return WheelSpec(**values)


def test_stiffness_metrics_are_positive_and_ordered():
    spec = make_spec()
    stiffness = estimate_wheel_stiffness(spec, 1000.0, 2.0)

    assert stiffness.spoke_count == 32
    assert stiffness.active_spoke_count == 32
    assert stiffness.lateral_n_per_mm > 0.0
    assert stiffness.radial_n_per_mm > 0.0
    assert stiffness.torsional_nm_per_deg > 0.0
    assert stiffness.radial_n_per_mm > stiffness.lateral_n_per_mm
    assert (
        stiffness.lateral_min_n_per_mm
        <= stiffness.lateral_n_per_mm
        <= stiffness.lateral_max_n_per_mm
    )
    assert (
        stiffness.radial_min_n_per_mm
        <= stiffness.radial_n_per_mm
        <= stiffness.radial_max_n_per_mm
    )
    assert len(stiffness.lateral_point_n_per_mm) == 32
    assert len(stiffness.radial_point_n_per_mm) == 32
    assert stiffness.warnings == ()
    assert "RIGIDEZ DA RODA" in stiffness.summary_text()
    assert stiffness.to_dict()["spoke_count"] == 32


def test_radial_lacing_has_zero_torsional_stiffness():
    stiffness = estimate_wheel_stiffness(
        make_spec(crossings=0), 1000.0, 2.0
    )
    assert stiffness.torsional_nm_per_deg == pytest.approx(0.0)
    assert any("radial" in warning.lower() for warning in stiffness.warnings)


def test_point_stiffnesses_and_stiffness_matrix_are_symmetric():
    state = TruingState(make_spec(), 1000.0, 2.0)
    radial, lateral = state.point_stiffnesses()
    assert len(radial) == 32
    assert len(lateral) == 32
    assert all(value > 0.0 for value in radial)
    assert all(value > 0.0 for value in lateral)

    matrix = state.stiffness_matrix()
    assert len(matrix) == 64
    assert len(matrix[0]) == 64
    for row in (0, 7, 31, 63):
        assert matrix[row][row] > 0.0
        for column in (0, 7, 31, 63):
            assert matrix[row][column] == pytest.approx(
                matrix[column][row]
            )


def test_slack_spoke_is_excluded_from_point_stiffness():
    state = TruingState(
        make_spec(),
        1000.0,
        2.0,
        initial_tensions_n=[0.0] + [1000.0] * 31,
    )
    assert state.slack_indices == (0,)
    radial, lateral = state.point_stiffnesses()
    assert len(radial) == 32
    assert len(lateral) == 32
    assert all(value > 0.0 for value in radial)
    assert all(value > 0.0 for value in lateral)


def test_no_active_spokes_is_rejected():
    state = TruingState(
        make_spec(),
        1000.0,
        2.0,
        initial_tensions_n=[0.0] * 32,
    )
    with pytest.raises(ValueError, match="raios tensionados"):
        state.stiffness_matrix()
    with pytest.raises(ValueError, match="raios tensionados"):
        state.point_stiffnesses()
    with pytest.raises(ValueError, match="raios tensionados"):
        estimate_wheel_stiffness(make_spec(), 0.5, 2.0)
