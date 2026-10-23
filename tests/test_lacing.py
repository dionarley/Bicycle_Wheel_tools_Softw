import pytest

from wheel_lab.core import Side, SpokeDirection, build_spoke_table


def test_spoke_table_size_and_angles():
    spokes = build_spoke_table(32, 3)
    assert len(spokes) == 32
    assert spokes[0].rim_angle_deg == pytest.approx(0.0)
    assert spokes[0].side is Side.LEFT
    assert spokes[0].direction is SpokeDirection.LEADING
    assert spokes[0].hub_angle_deg == pytest.approx(67.5)

    assert spokes[1].side is Side.RIGHT
    assert spokes[1].direction is SpokeDirection.LEADING
    assert spokes[1].hub_angle_deg == pytest.approx(11.25 + 67.5)

    assert spokes[2].side is Side.LEFT
    assert spokes[2].direction is SpokeDirection.TRAILING
    assert spokes[2].hub_angle_deg == pytest.approx(22.5 - 67.5)


def test_radial_spoking_has_no_hub_offset():
    for spoke in build_spoke_table(32, 0):
        assert spoke.hub_angle_deg == pytest.approx(spoke.rim_angle_deg)


def test_alternating_sides_and_directions():
    spokes = build_spoke_table(36, 3)
    assert sum(s.side is Side.LEFT for s in spokes) == 18
    assert sum(s.side is Side.RIGHT for s in spokes) == 18
    assert sum(s.direction is SpokeDirection.LEADING for s in spokes) == 18
    assert sum(s.direction is SpokeDirection.TRAILING for s in spokes) == 18


def test_invalid_spoke_counts():
    with pytest.raises(ValueError):
        build_spoke_table(30, 3)
    with pytest.raises(ValueError):
        build_spoke_table(8, 3)  # 8 é múltiplo de 4, mas 3x dá T=270°
