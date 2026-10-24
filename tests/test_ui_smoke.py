import pytest

pytest.importorskip("PySide6")

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402

    import wheel_builder_qt as appmod  # noqa: E402
except ImportError as exc:  # ex.: libGL/libxkbcommon ausentes no sistema
    pytest.skip(f"Interface PySide6 indisponível: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_change_to_36_and_apply_does_not_crash(qt_app):
    window = appmod.WheelCalculatorApp()
    window.spokes_count_combo.setCurrentText("36")
    assert len(window.lat_offsets) == 36
    assert len(window.rad_offsets) == 36

    window.sim_spoke_idx.setText("35")
    window.apply_sim_adjustment()
    assert len(window.visualizer.lateral_offsets) == 36
    assert len(window.visualizer.radial_offsets) == 36

    # Força o paintEvent em modo offscreen.
    window.visualizer.resize(420, 420)
    window.visualizer.grab()

    window.calculate_spokes()
    text = window.info_text.toPlainText()
    assert "COMPRIMENTO DOS RAIOS" in text
    assert "Erro" not in text
    window.close()


def test_change_to_28_and_invalid_index(qt_app):
    window = appmod.WheelCalculatorApp()
    window.spokes_count_combo.setCurrentText("28")
    assert len(window.lat_offsets) == 28

    window.sim_spoke_idx.setText("27")
    window.apply_sim_adjustment()
    assert len(window.visualizer.radial_offsets) == 28

    window.sim_spoke_idx.setText("99")
    window.apply_sim_adjustment()
    assert "Erro" in window.info_text.toPlainText()
    window.close()


def test_invalid_cross_pattern_shows_error(qt_app):
    window = appmod.WheelCalculatorApp()
    window.spokes_count_combo.setCurrentText("28")
    invalid_index = window.cross_combo.findData(4)
    window.cross_combo.setCurrentIndex(invalid_index)
    window.calculate_spokes()
    assert "Erro" in window.info_text.toPlainText()
    window.close()


def test_spoke_count_adjusts_invalid_crossing(qt_app):
    window = appmod.WheelCalculatorApp()
    window.cross_combo.setCurrentIndex(window.cross_combo.findData(4))
    window.spokes_count_combo.setCurrentText("28")
    assert window.cross_combo.currentData() == 3
    window.close()


def test_dish_updates_lengths_and_centering_view(qt_app):
    window = appmod.WheelCalculatorApp()
    window.dish_input.setText("2.0")
    window.calculate_spokes()

    sheet = window.last_sheet
    assert sheet is not None
    assert sheet.spec.effective_left_offset_mm == 37.0
    assert sheet.spec.effective_right_offset_mm == 17.0
    assert "esquerda" in sheet.centering_action
    assert "CENTRALIZAÇÃO" in window.info_text.toPlainText()
    assert window.centering_view.spec is sheet.spec

    window.centering_view.resize(420, 280)
    window.centering_view.grab()
    window.close()


def test_build_sheet_preview_and_pdf(qt_app, tmp_path):
    if appmod.QPrinter is None:
        pytest.skip("QtPrintSupport indisponível")

    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    sheet = window.last_sheet
    assert sheet is not None
    assert "Ficha de montagem" in window.sheet_preview.toPlainText()

    pdf_path = tmp_path / "ficha.pdf"
    window._write_pdf(sheet, str(pdf_path))
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000
    window.close()


def test_visibility_flags_and_selected_spoke(qt_app):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()

    window.show_left_cb.setChecked(False)
    assert window.visualizer.show_left is False
    window.show_left_cb.setChecked(True)
    assert window.visualizer.show_left is True

    window.sim_spoke_idx.setText("5")
    assert window.visualizer.selected_index == 5
    window.sim_spoke_idx.setText("99")
    assert window.visualizer.selected_index is None

    window.visualizer.resize(420, 420)
    window.visualizer.grab()
    window.close()


def test_locknut_spacing_is_optional(qt_app):
    window = appmod.WheelCalculatorApp()
    window.locknut_input.setText("")
    window.calculate_spokes()
    assert window.last_sheet is not None
    assert window.last_sheet.spec.locknut_spacing_mm is None
    window.close()


def test_example_and_physical_suggestions_reduce_runout(qt_app):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    window.load_example()

    state = window.truing_state
    assert state is not None
    before_lateral = state.lateral_runout_mm
    before_radial = state.radial_runout_mm
    assert before_lateral > 0.0
    assert before_radial > 0.0
    assert "tensão" in window.sim_selected_info.text()

    window.suggest_sim_adjustments()
    suggestion = window.last_suggestion
    assert suggestion is not None
    assert suggestion.adjustments
    assert suggestion.predicted_lateral_runout_mm < before_lateral
    assert suggestion.predicted_radial_runout_mm < before_radial
    assert window.apply_suggestions_btn.isEnabled()
    assert "SUGESTÕES DE AJUSTE" in window.info_text.toPlainText()

    window.apply_sim_suggestions()
    assert window.last_suggestion is None
    assert not window.apply_suggestions_btn.isEnabled()
    assert state.lateral_runout_mm < before_lateral
    assert state.radial_runout_mm < before_radial
    assert window.visualizer.lateral_offsets == list(state.lateral_mm)
    assert "Sugestões aplicadas" in window.info_text.toPlainText()

    window.suggest_sim_adjustments()
    if window.last_suggestion is not None:
        window.apply_sim_suggestions()
    assert state.lateral_runout_mm < 0.4
    assert state.radial_runout_mm < 0.1

    window.visualizer.resize(420, 420)
    window.visualizer.grab()
    window.close()


def test_reset_sim_clears_physical_state(qt_app):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    window.load_example()
    window.reset_sim()

    assert window.truing_state is not None
    assert window.truing_state.lateral_runout_mm == pytest.approx(0.0)
    assert window.truing_state.radial_runout_mm == pytest.approx(0.0)
    assert window.last_suggestion is None
    assert not window.apply_suggestions_btn.isEnabled()
    assert "resetado" in window.info_text.toPlainText()
    window.close()


def test_apply_suggestions_without_suggestion_is_safe(qt_app):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    window.apply_sim_suggestions()
    assert "Nenhuma sugestão" in window.info_text.toPlainText()
    window.close()
