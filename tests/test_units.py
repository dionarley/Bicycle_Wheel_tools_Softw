import pytest

from wheel_lab.core import (
    QUARTER_TURN_MM,
    SPOKE_THREAD_PITCH_MM,
    mm_to_inch,
    mm_to_turns,
    turns_to_mm,
)


def test_thread_pitch():
    assert SPOKE_THREAD_PITCH_MM == pytest.approx(0.4536, abs=0.0001)
    assert QUARTER_TURN_MM == pytest.approx(0.1134, abs=0.0001)


def test_turns_and_mm_are_inverse():
    assert turns_to_mm(1.0) == pytest.approx(SPOKE_THREAD_PITCH_MM)
    assert turns_to_mm(0.25) == pytest.approx(QUARTER_TURN_MM)
    assert mm_to_turns(turns_to_mm(0.5)) == pytest.approx(0.5)


def test_inches():
    assert mm_to_inch(25.4) == pytest.approx(1.0)


def test_invalid_turns():
    with pytest.raises(ValueError):
        turns_to_mm(float("nan"))
    with pytest.raises(ValueError):
        mm_to_turns(float("inf"))
