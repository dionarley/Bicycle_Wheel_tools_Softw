import json

import pytest

from wheel_lab.core import (
    Side,
    Severity,
    ToneReading,
    TruingState,
    WheelSpec,
    create_build_sheet,
    default_component_library,
    diagnose_build_sheet,
    estimate_wheel_stiffness,
)


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


def codes(report):
    return {finding.code for finding in report.findings}


def test_clean_sheet_has_no_findings():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    report = diagnose_build_sheet(sheet)
    assert report.findings == ()
    assert report.score == 100
    assert report.overall is Severity.INFO
    assert "nenhum achado" in report.summary_text()
    assert "Nenhum problema" in report.to_text()


def test_dish_and_component_findings():
    sheet = create_build_sheet(make_spec(rim_offset_mm=2.0), 1000.0, 2.0)
    report = diagnose_build_sheet(sheet)
    assert "dish" in codes(report)
    dish = next(finding for finding in report.findings if finding.code == "dish")
    assert dish.severity is Severity.CRITICAL
    assert dish.value == pytest.approx(2.0)
    assert report.score < 100
    assert report.overall is Severity.CRITICAL

    components = default_component_library().default_set()
    mismatched = create_build_sheet(
        make_spec(), 1000.0, 2.0, components=components
    )
    mismatch_report = diagnose_build_sheet(mismatched)
    assert "component_mismatch" in codes(mismatch_report)
    assert any(
        finding.severity is Severity.WARNING
        for finding in mismatch_report.findings
        if finding.code == "component_mismatch"
    )


def test_missing_locknut_is_information():
    sheet = create_build_sheet(
        make_spec(locknut_spacing_mm=None), 1000.0, 2.0
    )
    report = diagnose_build_sheet(sheet)
    assert "locknut_missing" in codes(report)
    finding = next(
        finding for finding in report.findings if finding.code == "locknut_missing"
    )
    assert finding.severity is Severity.INFO


def test_truing_state_adds_runout_slack_and_tension_findings():
    spec = make_spec()
    sheet = create_build_sheet(spec, 1000.0, 2.0)
    state = TruingState(
        spec,
        1000.0,
        2.0,
        initial_lateral_mm=[0.0] * 18 + [2.0] * 18,
        initial_radial_mm=[0.0] * 18 + [1.5] * 18,
        initial_tensions_n=[0.0] + [1000.0] * 35,
    )
    report = diagnose_build_sheet(sheet, truing_state=state)
    found = codes(report)
    assert "runout_lateral" in found
    assert "runout_radial" in found
    assert "slack_spokes" in found
    assert "tension_low" in found
    assert report.overall is Severity.CRITICAL
    assert any("Raios frouxos" in finding.message for finding in report.findings)


def test_mismatched_truing_state_is_reported():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    other_spec = make_spec(erd_mm=600.0)
    state = TruingState(other_spec, 1000.0, 2.0)
    report = diagnose_build_sheet(sheet, truing_state=state)
    assert "truing_spec_mismatch" in codes(report)
    assert "runout_lateral" not in codes(report)


def test_tone_reading_adds_tension_deviation_and_confidence_findings():
    sheet = create_build_sheet(make_spec(), 1000.0, 2.0)
    reading = ToneReading(
        frequency_hz=400.0,
        confidence=0.3,
        rms=0.1,
        peak_amplitude=0.2,
        sample_rate_hz=8000,
        duration_s=0.5,
        side=Side.RIGHT,
        tension_n=500.0,
        expected_tension_n=1000.0,
    )
    report = diagnose_build_sheet(sheet, tone_readings=reading)
    found = codes(report)
    assert "tone_confidence" in found
    assert "tone_tension" in found
    tension_finding = next(
        finding for finding in report.findings if finding.code == "tone_tension"
    )
    assert tension_finding.severity is Severity.CRITICAL
    assert "500 N" in tension_finding.message


def test_stiffness_adds_information_and_warnings():
    spec = make_spec()
    sheet = create_build_sheet(spec, 1000.0, 2.0)
    stiffness = estimate_wheel_stiffness(spec, 1000.0, 2.0)
    report = diagnose_build_sheet(sheet, stiffness=stiffness)
    assert "stiffness_metrics" in codes(report)
    assert report.score == 100

    radial = estimate_wheel_stiffness(
        make_spec(crossings=0), 1000.0, 2.0
    )
    radial_report = diagnose_build_sheet(sheet, stiffness=radial)
    assert "stiffness_warning" in codes(radial_report)


def test_report_exports_are_serializable():
    sheet = create_build_sheet(make_spec(rim_offset_mm=2.0), 1000.0, 2.0)
    report = diagnose_build_sheet(sheet)
    payload = report.to_dict()
    assert json.loads(json.dumps(payload, ensure_ascii=False))["score"] < 100
    assert "Diagnóstico da roda" in report.to_markdown()
    assert "<table>" in report.to_html()
    assert "DIAGNÓSTICO DA RODA" in report.to_text()
    assert payload["overall"] == "critical"
    assert payload["counts"]["critical"] >= 1


def test_build_sheet_includes_base_diagnostics():
    sheet = create_build_sheet(make_spec(rim_offset_mm=2.0), 1000.0, 2.0)
    assert sheet.diagnostics is not None
    payload = sheet.to_dict()
    assert payload["diagnostics"]["score"] < 100
    assert "## Diagnóstico da roda" in sheet.to_markdown()
    assert "Diagnóstico da roda" in sheet.to_html()
    assert "Diagnóstico" in sheet.to_summary_text()
