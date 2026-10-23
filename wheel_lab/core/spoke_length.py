"""Cálculo do comprimento dos raios (equação 1 de Brandt)."""

from __future__ import annotations

import math

from .geometry import spoke_angle_deg
from .models import SpokeLengthResult, WheelSpec


def spoke_length_mm(
    erd_mm: float,
    flange_diameter_mm: float,
    flange_offset_mm: float,
    hole_diameter_mm: float,
    spoke_count: int,
    crossings: int,
) -> float:
    """Comprimento de um raio para um lado, em milímetros.

    Equação 1 do livro::

        L = sqrt(A² + B² + C²) - S/2
        A = (d/2) * sin(T)
        B = D/2 - (d/2) * cos(T)
        C = W/2   (aqui, o offset do flange ao plano do aro)
        T = 360 * X / (N/2)

    ``S`` é o diâmetro do furo do flange. O resultado **não** é arredondado;
    use :func:`purchase_length_mm` para escolher o tamanho comercial.
    """

    for name, value in (
        ("ERD", erd_mm),
        ("diâmetro do flange", flange_diameter_mm),
        ("offset do flange", flange_offset_mm),
        ("diâmetro do furo", hole_diameter_mm),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")

    if flange_diameter_mm >= erd_mm:
        raise ValueError("O diâmetro do flange deve ser menor que o ERD.")
    if hole_diameter_mm >= flange_diameter_mm:
        raise ValueError(
            "O diâmetro do furo deve ser menor que o diâmetro do flange."
        )

    angle_deg = spoke_angle_deg(spoke_count, crossings)
    angle_rad = math.radians(angle_deg)

    a = (flange_diameter_mm / 2.0) * math.sin(angle_rad)
    b = (erd_mm / 2.0) - ((flange_diameter_mm / 2.0) * math.cos(angle_rad))
    c = flange_offset_mm

    length = math.sqrt(a * a + b * b + c * c) - (hole_diameter_mm / 2.0)
    if length <= 0 or not math.isfinite(length):
        raise ValueError("Comprimento de raio calculado inválido; confira as medidas.")
    return length


def calculate_spoke_lengths(spec: WheelSpec) -> SpokeLengthResult:
    """Calcula os comprimentos dos dois lados de uma roda."""

    spec.validate()
    angle = spoke_angle_deg(spec.spoke_count, spec.crossings)
    left = spoke_length_mm(
        spec.erd_mm,
        spec.left_flange_diameter_mm,
        spec.left_flange_offset_mm,
        spec.hole_diameter_mm,
        spec.spoke_count,
        spec.crossings,
    )
    right = spoke_length_mm(
        spec.erd_mm,
        spec.right_flange_diameter_mm,
        spec.right_flange_offset_mm,
        spec.hole_diameter_mm,
        spec.spoke_count,
        spec.crossings,
    )
    return SpokeLengthResult(
        spec=spec,
        angle_deg=angle,
        left_mm=left,
        right_mm=right,
        left_purchase_mm=purchase_length_mm(left),
        right_purchase_mm=purchase_length_mm(right),
    )


def purchase_length_mm(length_mm: float, step_mm: float = 1.0) -> int:
    """Arredonda **para baixo** o comprimento para um tamanho comercial.

    Brandt (p. 126): o raio estica até ~1 mm sob tensão e o aro pode encolher
    até ~2 mm; por isso o comprimento calculado deve ser arredondado para
    baixo, nunca para cima.

    ``step_mm`` permite arredondar em passos de 2 mm, por exemplo.
    """

    if not math.isfinite(length_mm) or length_mm <= 0:
        raise ValueError("O comprimento do raio deve ser positivo.")
    if not math.isfinite(step_mm) or step_mm <= 0:
        raise ValueError("O passo de arredondamento deve ser positivo.")
    return int(math.floor(length_mm / step_mm) * step_mm)
