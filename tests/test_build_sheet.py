import json

import pytest

from wheel_lab.core import Side, WheelSpec, create_build_sheet


def make_spec(**overrides):
    values = dict(
        erd_mm=618.0,
        left_flange_diameter_mm=39.0,
        right_flange_diameter_mm=39.0,
        left_flange_offset_mm=35.5,
        right_flange_offset_mm=19.0,
        hole_diameter_mm=2.4,
        spoke_count=36,
        crossings=3,
        rim_offset_mm=0.0,
        locknut_spacing_mm=130.0,
    )
    values.update(overrides)
    return WheelSpec(**values)


def test_build_sheet_contains_lengths_and_tensions():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    assert sheet.result.left_mm == pytest.approx(300.62, abs=0.01)
    assert sheet.result.right_purchase_mm == 299
    assert sheet.tighter_side is Side.RIGHT
    assert sheet.tensions_n[Side.RIGHT] == pytest.approx(1000.0)
    assert sheet.tensions_n[Side.LEFT] < 1000.0
    assert sheet.compression_n > 1000.0


def test_build_sheet_dict_is_json_serializable():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    payload = sheet.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "rim_offset_mm" in encoded
    assert payload["centering"]["is_centered"] is True
    assert payload["tension"]["tighter_side"] == "right"


def test_build_sheet_markdown_and_html():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    markdown = sheet.to_markdown()
    html = sheet.to_html()
    assert "Ficha de montagem" in markdown
    assert "Comprimentos" in markdown
    assert "300,62 mm" in markdown
    assert "<table>" in html
    assert "300,62 mm" in html
    assert "299,13 mm" in html


def test_build_sheet_reports_dish_warning():
    sheet = create_build_sheet(make_spec(rim_offset_mm=2.0), 1000.0, 2.0)
    warnings = sheet.warnings()
    assert any("descentralizada" in warning for warning in warnings)
    assert "esquerda" in sheet.centering_action
    assert sheet.to_dict()["centering"]["correction_mm"] == pytest.approx(-2.0)


def test_build_sheet_saves_files(tmp_path):
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    json_path = tmp_path / "ficha.json"
    md_path = tmp_path / "ficha.md"
    sheet.save_json(json_path)
    sheet.save_markdown(md_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["spec"]["erd_mm"] == 618
    assert "Ficha de montagem" in md_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("target", [0.0, -100.0, float("nan")])
def test_build_sheet_rejects_invalid_target(target):
    with pytest.raises(ValueError, match="tensão"):
        create_build_sheet(make_spec(), target, 2.0)


@pytest.mark.parametrize("diameter", [0.0, -2.0, float("inf")])
def test_build_sheet_rejects_invalid_diameter(diameter):
    with pytest.raises(ValueError, match="diâmetro"):
        create_build_sheet(make_spec(), 1000.0, diameter)
