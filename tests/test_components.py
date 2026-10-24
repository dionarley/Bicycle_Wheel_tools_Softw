import json
from dataclasses import replace

import pytest

from wheel_lab.core import (
    ComponentLibrary,
    ComponentSet,
    HubComponent,
    NippleComponent,
    RimComponent,
    SpokeComponent,
    default_component_library,
)


def test_default_library_is_valid_and_has_defaults():
    library = default_component_library()
    library.validate()
    assert library.rims
    assert library.hubs
    assert library.spokes
    assert library.nipples

    components = library.default_set()
    assert isinstance(components, ComponentSet)
    components.validate()
    spec = components.to_spec(crossings=3)
    assert spec.erd_mm == pytest.approx(600.0)
    assert spec.spoke_count == 32
    assert spec.locknut_spacing_mm == pytest.approx(130.0)


def test_library_finds_components_by_name():
    library = default_component_library()
    rim = library.find_rim(library.rims[0].name)
    hub = library.find_hub(library.hubs[0].name)
    spoke = library.find_spoke(library.spokes[0].name)
    nipple = library.find_nipple(library.nipples[0].name)
    assert rim is library.rims[0]
    assert hub is library.hubs[0]
    assert spoke is library.spokes[0]
    assert nipple is library.nipples[0]
    with pytest.raises(ValueError, match="não encontrado"):
        library.find_rim("Aro inexistente")


def test_component_set_serializes_to_json():
    components = default_component_library().default_set()
    payload = components.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "Aro 700c" in encoded
    assert payload["rim"]["spoke_count"] == 32
    assert payload["hub"]["locknut_spacing_mm"] == pytest.approx(130.0)


def test_component_set_reports_compatibility_warnings():
    components = default_component_library().default_set()
    spec = components.to_spec(crossings=3)
    assert components.compatibility_warnings(spec, 2.0) == []

    changed = replace(spec, erd_mm=602.0)
    warnings = components.compatibility_warnings(changed, 1.8)
    assert any("ERD" in warning for warning in warnings)
    assert any("diâmetro" in warning.lower() for warning in warnings)


def test_component_set_rejects_mismatched_hub_and_rim():
    library = default_component_library()
    components = library.default_set()
    hub_36 = next(hub for hub in library.hubs if hub.spoke_count == 36)
    mismatched = replace(components, hub=hub_36)
    with pytest.raises(ValueError, match="números de furos"):
        mismatched.validate()
    with pytest.raises(ValueError, match="números de furos"):
        mismatched.to_spec(crossings=3)


def test_component_set_rejects_wrong_spoke_count_argument():
    components = default_component_library().default_set()
    with pytest.raises(ValueError, match="não coincide"):
        components.to_spec(crossings=3, spoke_count=36)


def test_component_library_rejects_duplicate_names():
    rim = RimComponent("Aro teste", 600.0, 32)
    hub = HubComponent(
        "Cubo teste",
        32,
        45.0,
        45.0,
        35.0,
        19.0,
    )
    spoke = SpokeComponent("Raio teste", 2.0)
    nipple = NippleComponent("Niple teste", 12.0)
    with pytest.raises(ValueError, match="repetidos"):
        ComponentLibrary(
            rims=(rim, rim),
            hubs=(hub,),
            spokes=(spoke,),
            nipples=(nipple,),
        ).validate()


def test_component_summary_contains_all_components():
    components = default_component_library().default_set()
    summary = components.summary_text()
    assert "Aro:" in summary
    assert "Cubo:" in summary
    assert "Raios:" in summary
    assert "Niples:" in summary
    assert components.rim.name in summary
