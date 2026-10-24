import json

import pytest

from wheel_lab.core import (
    Side,
    SpokeDirection,
    WheelSpec,
    build_assembly_plan,
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


def test_plan_has_four_groups_covering_every_spoke():
    plan = build_assembly_plan(make_spec())
    assert len(plan.groups) == 4
    assert plan.group_size == 8
    assert plan.angle_deg == pytest.approx(67.5)

    indices = [
        index for group in plan.groups for index in group.spoke_indices
    ]
    assert sorted(indices) == list(range(32))
    assert all(group.count == 8 for group in plan.groups)

    assert plan.groups[0].side is Side.LEFT
    assert plan.groups[0].direction is SpokeDirection.LEADING
    assert plan.groups[1].side is Side.RIGHT
    assert plan.groups[1].direction is SpokeDirection.LEADING
    assert plan.groups[2].side is Side.LEFT
    assert plan.groups[2].direction is SpokeDirection.TRAILING
    assert plan.groups[3].side is Side.RIGHT
    assert plan.groups[3].direction is SpokeDirection.TRAILING


def test_rim_holes_follow_the_four_hole_pattern():
    plan = build_assembly_plan(make_spec())
    assert plan.groups[0].rim_holes == (1, 5, 9, 13, 17, 21, 25, 29)
    assert plan.groups[1].rim_holes == (2, 6, 10, 14, 18, 22, 26, 30)
    assert plan.groups[2].rim_holes == (3, 7, 11, 15, 19, 23, 27, 31)
    assert plan.groups[3].rim_holes == (4, 8, 12, 16, 20, 24, 28, 32)


def test_hub_holes_cover_each_flange_once():
    plan = build_assembly_plan(make_spec())
    left_holes = set(plan.groups[0].hub_holes) | set(plan.groups[2].hub_holes)
    right_holes = set(plan.groups[1].hub_holes) | set(plan.groups[3].hub_holes)
    assert left_holes == set(range(1, 17))
    assert right_holes == set(range(1, 17))
    for group in plan.groups:
        assert len(set(group.hub_holes)) == 8


def test_plan_text_markdown_html_and_dict():
    plan = build_assembly_plan(make_spec())
    text = plan.to_text()
    markdown = plan.to_markdown()
    html = plan.to_html()
    payload = plan.to_dict()

    assert "ASSISTENTE DOS 4 CONJUNTOS" in text
    assert "Conjunto 1" in text
    assert "Conjunto 4" in text
    assert "## Assistente de montagem" in markdown
    assert "| 1 | Esquerda | leading | 8 |" in markdown
    assert "<h2>Assistente de montagem" in html
    assert "Conjunto 1" in html
    assert len(payload["groups"]) == 4
    assert payload["wheel"]["spoke_count"] == 32
    json.dumps(payload, ensure_ascii=False)


def test_focus_group_text_only_includes_selected_group():
    plan = build_assembly_plan(make_spec())
    text = plan.to_text(focus_group=2)
    assert "Conjunto 2 de 4" in text
    assert "=== Conjunto 2" in text
    assert "=== Conjunto 1" not in text
    with pytest.raises(ValueError, match="não existe"):
        plan.group_by_number(9)


def test_36_spokes_has_nine_per_group():
    plan = build_assembly_plan(make_spec(spoke_count=36))
    assert [group.count for group in plan.groups] == [9, 9, 9, 9]
    assert plan.groups[0].rim_holes == (1, 5, 9, 13, 17, 21, 25, 29, 33)
    assert sorted(
        index for group in plan.groups for index in group.spoke_indices
    ) == list(range(36))


def test_radial_plan_warns_and_still_has_four_groups():
    plan = build_assembly_plan(make_spec(spoke_count=24, crossings=0))
    assert [group.count for group in plan.groups] == [6, 6, 6, 6]
    assert any("radial" in warning.lower() for warning in plan.warnings)
    assert "não há cruzamentos" in plan.to_text()


def test_limit_angle_warns():
    plan = build_assembly_plan(make_spec(spoke_count=24, crossings=3))
    assert plan.angle_deg == pytest.approx(90.0)
    assert any("90°" in warning for warning in plan.warnings)


def test_plan_can_omit_warnings_when_embedded():
    plan = build_assembly_plan(make_spec(spoke_count=24, crossings=0))
    assert "### Avisos" in plan.to_markdown()
    assert "### Avisos" not in plan.to_markdown(include_warnings=False)
    assert "<h3>Avisos</h3>" in plan.to_html()
    assert "<h3>Avisos</h3>" not in plan.to_html(include_warnings=False)


def test_plan_rejects_spoke_count_not_multiple_of_four():
    with pytest.raises(ValueError, match="múltiplo de 4"):
        build_assembly_plan(make_spec(spoke_count=30, crossings=3))


def test_plan_rejects_invalid_cross_pattern():
    with pytest.raises(ValueError, match="máximo"):
        build_assembly_plan(make_spec(spoke_count=24, crossings=4))
