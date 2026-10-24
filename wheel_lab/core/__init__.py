"""Núcleo de cálculo do Wheel Lab.

O pacote ``wheel_lab.core`` não depende de Qt nem de NumPy: são apenas
dataclasses, validações e fórmulas. Isso permite testar a engenharia da roda
sem abrir uma janela.
"""

from .build_sheet import BuildSheet, create_build_sheet
from .geometry import (
    erd_from_outer_diameter,
    is_valid_cross_pattern,
    max_crossings,
    spoke_angle_deg,
)
from .lacing import build_spoke_table
from .models import (
    Side,
    Spoke,
    SpokeDirection,
    SpokeLengthResult,
    WheelSpec,
)
from .spoke_length import (
    calculate_spoke_lengths,
    purchase_length_mm,
    spoke_length_mm,
)
from .tension import (
    lateral_tension_ratio,
    linear_density_kg_per_m,
    rim_compression_from_sides,
    rim_compression_n,
    spoke_elongation_mm,
    target_tensions,
    tension_from_tone_hz,
    tire_constriction_n,
    tone_frequency_hz,
)
from .units import (
    MM_PER_INCH,
    QUARTER_TURN_MM,
    SPOKE_THREAD_PITCH_MM,
    SPOKE_THREADS_PER_INCH,
    inch_to_mm,
    mm_to_inch,
    mm_to_turns,
    turns_to_mm,
)

__all__ = [
    "MM_PER_INCH",
    "QUARTER_TURN_MM",
    "SPOKE_THREADS_PER_INCH",
    "SPOKE_THREAD_PITCH_MM",
    "BuildSheet",
    "Side",
    "Spoke",
    "SpokeDirection",
    "SpokeLengthResult",
    "WheelSpec",
    "build_spoke_table",
    "calculate_spoke_lengths",
    "create_build_sheet",
    "erd_from_outer_diameter",
    "inch_to_mm",
    "is_valid_cross_pattern",
    "lateral_tension_ratio",
    "linear_density_kg_per_m",
    "max_crossings",
    "mm_to_inch",
    "mm_to_turns",
    "purchase_length_mm",
    "rim_compression_from_sides",
    "rim_compression_n",
    "spoke_angle_deg",
    "spoke_elongation_mm",
    "spoke_length_mm",
    "target_tensions",
    "tension_from_tone_hz",
    "tire_constriction_n",
    "tone_frequency_hz",
    "turns_to_mm",
]
