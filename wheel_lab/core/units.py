"""Conversões de unidades e constantes de montagem."""

from __future__ import annotations

import math

MM_PER_INCH = 25.4
SPOKE_THREADS_PER_INCH = 56.0
SPOKE_THREAD_PITCH_MM = MM_PER_INCH / SPOKE_THREADS_PER_INCH
QUARTER_TURN_MM = SPOKE_THREAD_PITCH_MM / 4.0


def turns_to_mm(turns: float) -> float:
    """Converte voltas de niple em deslocamento axial do raio (mm).

    Um niple de 56 TPI avança 25,4/56 ≈ 0,4536 mm por volta.
    """

    if not math.isfinite(turns):
        raise ValueError("O número de voltas deve ser finito.")
    return turns * SPOKE_THREAD_PITCH_MM


def mm_to_turns(mm: float) -> float:
    """Converte um deslocamento em mm para voltas de niple."""

    if not math.isfinite(mm):
        raise ValueError("O deslocamento deve ser finito.")
    return mm / SPOKE_THREAD_PITCH_MM


def mm_to_inch(mm: float) -> float:
    if not math.isfinite(mm):
        raise ValueError("O valor em mm deve ser finito.")
    return mm / MM_PER_INCH


def inch_to_mm(inch: float) -> float:
    if not math.isfinite(inch):
        raise ValueError("O valor em polegadas deve ser finito.")
    return inch * MM_PER_INCH
