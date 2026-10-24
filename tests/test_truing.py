import math

import pytest

from wheel_lab.core import (
    RimElasticProperties,
    Side,
    TruingState,
    WheelSpec,
    build_spoke_geometries,
    calculate_spoke_lengths,
    turns_to_mm,
)


def make_spec(spoke_count: int = 32) -> WheelSpec:
    return WheelSpec(
        erd_mm=600.0,
        left_flange_diameter_mm=45.0,
        right_flange_diameter_mm=45.0,
        left_flange_offset_mm=35.0,
        right_flange_offset_mm=19.0,
        hole_diameter_mm=2.6,
        spoke_count=spoke_count,
        crossings=3,
        rim_offset_mm=0.0,
        locknut_spacing_mm=130.0,
    )


def make_state(**kwargs) -> TruingState:
    return TruingState(make_spec(), 1000.0, 2.0, **kwargs)


def example_runout(spoke_count: int = 32):
    lateral = [
        0.6 * math.sin(2.0 * math.pi * index / spoke_count)
        for index in range(spoke_count)
    ]
    radial = [
        0.3 * math.cos(4.0 * math.pi * index / spoke_count)
        for index in range(spoke_count)
    ]
    return lateral, radial


def test_spoke_geometries_match_lengths_and_lateral_signs():
    spec = make_spec()
    result = calculate_spoke_lengths(spec)
    geometries = build_spoke_geometries(spec, 2.0, 1000.0)

    assert len(geometries) == 32
    assert geometries[0].side is Side.LEFT
    assert geometries[1].side is Side.RIGHT
    for geometry in geometries:
        expected = (
            result.left_mm
            if geometry.side is Side.LEFT
            else result.right_mm
        )
        assert geometry.free_length_mm == pytest.approx(expected)
        assert geometry.radial_component > 0.0
        if geometry.side is Side.LEFT:
            assert geometry.lateral_component > 0.0
        else:
            assert geometry.lateral_component < 0.0
        assert geometry.stiffness_n_per_mm > 1000.0

    # Roda com dish: o lado direito fica mais tensionado.
    assert geometries[0].initial_tension_n < geometries[1].initial_tension_n
    assert geometries[1].initial_tension_n == pytest.approx(1000.0)


def test_zero_adjustment_is_equilibrium():
    state = make_state()
    result = state.apply_turns({})

    assert result.delta_lateral_mm == pytest.approx([0.0] * 32)
    assert result.delta_radial_mm == pytest.approx([0.0] * 32)
    assert result.lateral_runout_mm == pytest.approx(0.0)
    assert result.radial_runout_mm == pytest.approx(0.0)
    assert result.tensions_n == pytest.approx(state.tensions_n)
    assert result.iterations >= 1
    assert result.slack_indices == ()


def test_tightening_left_moves_rim_left_and_inward():
    state = make_state()
    initial_tension = state.tensions_n[0]
    result = state.apply_turns({0: 0.25})

    assert result.delta_lateral_mm[0] < 0.0
    assert result.delta_radial_mm[0] < 0.0
    assert result.tensions_n[0] > initial_tension
    assert result.lateral_runout_mm > 0.0


def test_tightening_right_moves_rim_right():
    state = make_state()
    initial_tension = state.tensions_n[1]
    result = state.apply_turns({1: 0.25})

    assert result.delta_lateral_mm[1] > 0.0
    assert result.delta_radial_mm[1] < 0.0
    assert result.tensions_n[1] > initial_tension


def test_slack_spoke_gap_and_reactivation():
    state = make_state()
    result = state.apply_turns({0: -2.0})

    assert result.active[0] is False
    assert result.tensions_n[0] == pytest.approx(0.0)
    assert state.slack_gap_mm[0] > 0.0
    # Soltar o raio esquerdo remove o puxão para a esquerda: o aro vai
    # para a direita e para fora.
    assert result.delta_lateral_mm[0] > 0.0
    assert result.delta_radial_mm[0] > 0.0

    gap_before = state.slack_gap_mm[0]
    partial = state.apply_turns({0: 0.25})
    assert partial.active[0] is False
    assert state.slack_gap_mm[0] < gap_before

    closed = state.apply_turns({0: 1.0})
    assert closed.active[0] is True
    assert closed.tensions_n[0] > 0.0
    assert state.slack_gap_mm[0] == pytest.approx(0.0)


def test_influence_matrix_shape_and_signs():
    state = make_state()
    influence = state.influence_matrix()

    assert len(influence) == 32
    assert all(len(column) == 64 for column in influence)
    # Coluna 0: raio esquerdo no nó 0. Aperto de 1 mm puxa para a esquerda
    # e para dentro.
    assert influence[0][1] < 0.0
    assert influence[0][0] < 0.0
    # Coluna 1: raio direito no nó 1. Puxa para a direita.
    assert influence[1][3] > 0.0
    assert influence[1][2] < 0.0


def test_influence_column_is_zero_for_slack_spoke():
    state = make_state()
    state.apply_turns({0: -2.0})
    influence = state.influence_matrix()

    assert influence[0] == pytest.approx([0.0] * 64)
    assert any(value != 0.0 for value in influence[1])


def test_suggestions_reduce_runout_in_two_steps():
    lateral, radial = example_runout()
    state = make_state(initial_lateral_mm=lateral, initial_radial_mm=radial)

    first = state.suggest_adjustments(max_turns=0.75)
    assert first.adjustments
    assert first.predicted_lateral_runout_mm < first.current_lateral_runout_mm
    assert first.predicted_radial_runout_mm < first.current_radial_runout_mm

    result = state.apply_turns(
        {adjustment.index: adjustment.turns for adjustment in first.adjustments}
    )
    assert result.lateral_runout_mm < first.current_lateral_runout_mm - 0.1
    assert result.radial_runout_mm < first.current_radial_runout_mm - 0.05
    assert not result.slack_indices

    second = state.suggest_adjustments(max_turns=0.75)
    if second.adjustments:
        result = state.apply_turns(
            {
                adjustment.index: adjustment.turns
                for adjustment in second.adjustments
            }
        )

    assert result.lateral_runout_mm < 0.4
    assert result.radial_runout_mm < 0.1
    assert result.min_tension_n > 0.0


def test_true_wheel_has_no_suggested_adjustments():
    state = make_state()
    suggestion = state.suggest_adjustments()

    assert suggestion.adjustments == ()
    assert suggestion.predicted_lateral_runout_mm == pytest.approx(0.0)
    assert suggestion.predicted_radial_runout_mm == pytest.approx(0.0)
    assert any("Nenhum ajuste" in warning for warning in suggestion.warnings)


def test_slack_wheel_suggestion_warns_and_ignores_slack_column():
    state = make_state()
    state.apply_turns({0: -2.0})
    suggestion = state.suggest_adjustments()

    assert any("frouxos" in warning for warning in suggestion.warnings)
    assert all(
        adjustment.index != 0 for adjustment in suggestion.adjustments
    )


def test_apply_turns_and_adjustments_are_equivalent():
    turns_state = make_state()
    mm_state = make_state()

    turns_result = turns_state.apply_turns({0: 0.25})
    mm_result = mm_state.apply_adjustments({0: turns_to_mm(0.25)})

    assert turns_result.delta_lateral_mm == pytest.approx(
        mm_result.delta_lateral_mm
    )
    assert turns_result.delta_radial_mm == pytest.approx(
        mm_result.delta_radial_mm
    )
    assert turns_result.tensions_n == pytest.approx(mm_result.tensions_n)


def test_runout_metrics_use_peak_to_peak():
    lateral = [0.0] * 32
    radial = [0.0] * 32
    lateral[3] = 1.5
    lateral[10] = -0.5
    radial[4] = 0.4
    radial[20] = -0.2
    state = make_state(initial_lateral_mm=lateral, initial_radial_mm=radial)

    assert state.lateral_runout_mm == pytest.approx(2.0)
    assert state.radial_runout_mm == pytest.approx(0.6)


def test_validation_errors():
    spec = make_spec()
    with pytest.raises(ValueError):
        TruingState(spec, 1000.0, 2.0, initial_lateral_mm=[0.0])
    with pytest.raises(ValueError):
        TruingState(
            spec,
            1000.0,
            2.0,
            initial_tensions_n=[-1.0] * 32,
        )
    with pytest.raises(ValueError):
        RimElasticProperties(cross_section_area_mm2=0.0).validate()

    state = make_state()
    with pytest.raises(ValueError):
        state.apply_turns({99: 0.25})
    with pytest.raises(ValueError):
        state.apply_turns({0: float("nan")})
    with pytest.raises(ValueError):
        state.suggest_adjustments(max_turns=0.0)

    odd_spec = make_spec(spoke_count=30)
    with pytest.raises(ValueError):
        build_spoke_geometries(odd_spec, 2.0, 1000.0)
