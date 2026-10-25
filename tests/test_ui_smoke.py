import math
import wave
from array import array

import pytest

pytest.importorskip("PySide6")

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402

    import wheel_builder_qt as appmod  # noqa: E402
except ImportError as exc:  # ex.: libGL/libxkbcommon ausentes no sistema
    pytest.skip(f"Interface PySide6 indisponível: {exc}", allow_module_level=True)


def write_tone_wav(path, frequency_hz, rate=8000, seconds=0.5):
    count = int(rate * seconds)
    frames = array(
        "h",
        [
            int(0.4 * 32767 * math.sin(2.0 * math.pi * frequency_hz * i / rate))
            for i in range(count)
        ],
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames.tobytes())


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


def test_assembly_tab_generates_plan_and_highlights(qt_app):
    window = appmod.WheelCalculatorApp()
    assert "Assistente de montagem" in [
        window.tabs.tabText(index) for index in range(window.tabs.count())
    ]
    window.calculate_spokes()

    plan = window.assembly_plan
    assert plan is not None
    assert len(plan.groups) == 4
    assert window.assembly_group_list.count() == 4
    assert window.visualizer.highlighted_indices == set(
        plan.groups[0].spoke_indices
    )

    window.assembly_group_list.setCurrentRow(2)
    assert window.visualizer.highlighted_indices == set(
        plan.groups[2].spoke_indices
    )
    assert "Conjunto 3 de 4" in window.assembly_text.toPlainText()

    window.complete_assembly_group()
    assert 3 in window.assembly_completed
    assert "✓ Conjunto 3" in window.assembly_group_list.item(2).text()
    assert "1 de 4" in window.assembly_progress.text()

    window.clear_assembly_progress()
    assert window.assembly_completed == set()
    assert "✓" not in window.assembly_group_list.item(2).text()

    window.visualizer.resize(420, 420)
    window.visualizer.grab()
    window.close()


def test_component_library_applies_and_build_sheet_includes(qt_app):
    window = appmod.WheelCalculatorApp()
    window.component_rim_combo.setCurrentText(
        "Aro 700c alumínio 36h (ERD 602 mm)"
    )
    # A seleção do aro sincroniza o cubo para a mesma furação.
    assert "36h" in window.component_hub_combo.currentText()

    window.apply_components()
    assert window.spokes_count_combo.currentText() == "36"
    assert window.current_components is not None
    assert window.current_components.rim.spoke_count == 36

    sheet = window.last_sheet
    assert sheet is not None
    assert sheet.components is window.current_components
    assert sheet.assembly_plan is not None
    assert len(sheet.assembly_plan.groups) == 4
    assert sheet.warnings() == []

    preview = window.sheet_preview.toPlainText()
    assert "Componentes" in preview
    assert "Assistente de montagem" in preview
    assert "Aro 700c alumínio 36h" in preview
    assert "aplicados" in window.component_summary.text()
    window.close()


def test_component_selection_syncs_rim_and_hub_counts(qt_app):
    window = appmod.WheelCalculatorApp()
    window.component_rim_combo.setCurrentText(
        "Aro 700c carbono 24h (ERD 595 mm)"
    )
    assert "24h" in window.component_hub_combo.currentText()

    window.component_hub_combo.setCurrentText(
        "Cubo traseiro 32h, 130 mm (PCD 45/45, offsets 35/19)"
    )
    assert "32h" in window.component_rim_combo.currentText()
    assert window.current_components is None
    window.close()


def test_assembly_actions_without_plan_are_safe(qt_app):
    window = appmod.WheelCalculatorApp()
    window.complete_assembly_group()
    window.clear_assembly_progress()
    window._show_assembly_group(0)
    assert "Selecione um conjunto" in window.assembly_text.toPlainText()
    assert "Gere o plano primeiro" in window.statusBar().currentMessage()
    window.close()


def test_audio_and_diagnostics_tabs_work(qt_app, tmp_path):
    window = appmod.WheelCalculatorApp()
    tab_names = [
        window.tabs.tabText(index) for index in range(window.tabs.count())
    ]
    assert "Leitura de tom" in tab_names
    assert "Diagnóstico e rigidez" in tab_names

    window.calculate_spokes()
    sheet = window.last_sheet
    assert sheet is not None
    assert sheet.diagnostics is not None

    window.audio_side_combo.setCurrentIndex(2)
    assert window.audio_hint.text().startswith("Esperado:")
    path = tmp_path / "tom.wav"
    write_tone_wav(path, sheet.tone_right_hz)
    window.audio_path_input.setText(str(path))
    window.analyze_audio()

    reading = window.last_tone_reading
    assert reading is not None
    assert reading.side is appmod.Side.RIGHT
    assert reading.frequency_hz == pytest.approx(sheet.tone_right_hz, abs=2.0)
    assert "LEITURA DE TOM" in window.audio_result_text.toPlainText()

    window.calculate_stiffness()
    assert window.last_stiffness is not None
    assert "RIGIDEZ DA RODA" in window.stiffness_text.toPlainText()

    window.generate_diagnostics()
    assert window.last_diagnostics is not None
    assert "DIAGNÓSTICO DA RODA" in window.diagnostics_text.toPlainText()
    assert "Diagnóstico da roda" in window.sheet_preview.toPlainText()
    assert window.last_sheet is not None
    assert window.last_sheet.diagnostics is window.last_diagnostics
    window.close()


def test_audio_without_side_only_reads_frequency(qt_app, tmp_path):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    path = tmp_path / "tom.wav"
    write_tone_wav(path, 440.0)
    window.audio_path_input.setText(str(path))
    window.audio_side_combo.setCurrentIndex(0)
    window.analyze_audio()

    reading = window.last_tone_reading
    assert reading is not None
    assert reading.side is None
    assert reading.tension_n is None
    assert "Tensão estimada" not in reading.summary_text()
    window.close()


def test_diagnostics_without_physical_state(qt_app):
    window = appmod.WheelCalculatorApp()
    window.spokes_count_combo.addItem("30")
    window.spokes_count_combo.setCurrentText("30")
    window.calculate_spokes()
    assert window.last_sheet is not None
    assert window.truing_state is None

    window.generate_diagnostics()
    assert window.last_diagnostics is not None
    assert "múltiplo de 4" in window.diagnostics_text.toPlainText()
    window.close()

def test_ensure_sheet_recalculates_after_field_change(qt_app):
    window = appmod.WheelCalculatorApp()
    window.calculate_spokes()
    old_sheet = window.last_sheet
    assert old_sheet is not None

    window.erd_input.setText("610.0")
    sheet = window._ensure_sheet()
    assert sheet is not None
    assert sheet is not old_sheet
    assert sheet.spec.erd_mm == 610.0
    window.close()
