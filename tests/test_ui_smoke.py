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
