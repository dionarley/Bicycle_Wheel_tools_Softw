"""Tensão, alongamento, tom e compressão do aro.

As fórmulas seguem a Parte III de Brandt. Elas são estimativas de engenharia:
o valor absoluto de tensão deve ser medido com tensiômetro; o tom é útil para
comparar raios, não para medir tensão absoluta.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from .models import Side

STEEL_ELASTIC_MODULUS_PA = 193e9
STEEL_DENSITY_KG_M3 = 7850.0


def lateral_tension_ratio(
    left_offset_mm: float,
    right_offset_mm: float,
    left_length_mm: float,
    right_length_mm: float,
) -> float:
    """Razão ``T_esquerda / T_direita`` para equilíbrio lateral.

    Em uma roda com offsets diferentes, o lado mais próximo do plano do aro
    (geralmente o direito, com cassete) fica mais tenso. Aproximação de
    equilíbrio: ``T_L * (offset_L / L_L) = T_R * (offset_R / L_R)``.
    """

    for name, value in (
        ("offset esquerdo", left_offset_mm),
        ("offset direito", right_offset_mm),
        ("comprimento esquerdo", left_length_mm),
        ("comprimento direito", right_length_mm),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")

    return (right_offset_mm / right_length_mm) / (
        left_offset_mm / left_length_mm
    )


def target_tensions(
    target_tension_n: float,
    ratio_left_over_right: float,
    tighter_side: Side = Side.RIGHT,
) -> dict[Side, float]:
    """Distribui uma tensão alvo entre os dois lados.

    ``target_tension_n`` é a tensão do lado mais tenso. O outro lado recebe
    ``target * ratio`` (se o direito for o mais tenso) ou ``target / ratio``
    (se o esquerdo for).
    """

    if not math.isfinite(target_tension_n) or target_tension_n <= 0:
        raise ValueError("A tensão alvo deve ser um número positivo.")
    if not math.isfinite(ratio_left_over_right) or ratio_left_over_right <= 0:
        raise ValueError("A razão de tensão deve ser um número positivo.")

    if tighter_side is Side.RIGHT:
        right = target_tension_n
        left = target_tension_n * ratio_left_over_right
    else:
        left = target_tension_n
        right = target_tension_n / ratio_left_over_right

    return {Side.LEFT: left, Side.RIGHT: right}


def rim_compression_n(tensions_n: Iterable[float]) -> float:
    """Compressão total no aro, em newtons.

    Para tensões iguais, ``C = N * T / (2π)`` (eq. 7). Para tensões
    diferentes, usa-se a soma das tensões de **todos os raios** dividida por
    ``2π``.
    """

    total = 0.0
    for tension in tensions_n:
        if not math.isfinite(tension) or tension < 0:
            raise ValueError("As tensões devem ser números não negativos.")
        total += tension
    return total / (2.0 * math.pi)


def rim_compression_from_sides(
    left_tension_n: float,
    right_tension_n: float,
    spoke_count: int,
) -> float:
    """Compressão do aro a partir da tensão de cada lado.

    Expande a tensão de cada lado para ``N/2`` raios antes de aplicar a
    equação 7. É o que a UI deve usar: passar apenas dois valores para
    :func:`rim_compression_n` subestimaria a compressão por um fator ``N/2``.
    """

    if not isinstance(spoke_count, int) or isinstance(spoke_count, bool):
        raise ValueError("O número de raios deve ser um inteiro.")
    if spoke_count < 2 or spoke_count % 2 != 0:
        raise ValueError("O número de raios deve ser par e maior ou igual a 2.")

    half = spoke_count // 2
    return rim_compression_n(
        [left_tension_n] * half + [right_tension_n] * half
    )


def spoke_elongation_mm(
    tension_n: float,
    length_mm: float,
    diameter_mm: float,
    elastic_modulus_pa: float = STEEL_ELASTIC_MODULUS_PA,
) -> float:
    """Alongamento elástico de um raio sob tensão, em milímetros.

    ``ΔL = T * L / (E * A)``. Exemplo do livro: raio de 1,6 mm com 290 mm a
    1000 N alonga ~0,75 mm.
    """

    for name, value in (
        ("tensão", tension_n),
        ("comprimento", length_mm),
        ("diâmetro", diameter_mm),
        ("módulo de elasticidade", elastic_modulus_pa),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")

    area_m2 = math.pi * (diameter_mm / 2000.0) ** 2
    length_m = length_mm / 1000.0
    return tension_n * length_m / (elastic_modulus_pa * area_m2) * 1000.0


def linear_density_kg_per_m(
    diameter_mm: float, density_kg_m3: float = STEEL_DENSITY_KG_M3
) -> float:
    """Massa por metro de um raio cilíndrico."""

    if not math.isfinite(diameter_mm) or diameter_mm <= 0:
        raise ValueError("O diâmetro do raio deve ser positivo.")
    if not math.isfinite(density_kg_m3) or density_kg_m3 <= 0:
        raise ValueError("A densidade deve ser positiva.")
    area_m2 = math.pi * (diameter_mm / 2000.0) ** 2
    return density_kg_m3 * area_m2


def tone_frequency_hz(
    tension_n: float,
    length_mm: float,
    linear_density_kg_per_m_value: float,
) -> float:
    """Frequência fundamental de um raio tensionado (corda fixa).

    ``f = (1 / 2L) * sqrt(T / μ)``. O valor é aproximado: comprimento livre,
    rigidez do niple e massa do aro alteram o resultado.
    """

    for name, value in (
        ("tensão", tension_n),
        ("comprimento", length_mm),
        ("densidade linear", linear_density_kg_per_m_value),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")

    length_m = length_mm / 1000.0
    return (1.0 / (2.0 * length_m)) * math.sqrt(
        tension_n / linear_density_kg_per_m_value
    )


def tension_from_tone_hz(
    frequency_hz: float,
    length_mm: float,
    linear_density_kg_per_m_value: float,
) -> float:
    """Inverso de :func:`tone_frequency_hz`: tensão a partir do tom."""

    for name, value in (
        ("frequência", frequency_hz),
        ("comprimento", length_mm),
        ("densidade linear", linear_density_kg_per_m_value),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")

    length_m = length_mm / 1000.0
    return (
        4.0
        * linear_density_kg_per_m_value
        * length_m**2
        * frequency_hz**2
    )


def tire_constriction_n(
    pressure_pa: float,
    cross_section_diameter_mm: float,
    cord_angle_deg: float = 45.0,
) -> float:
    """Força de constrição do pneu sobre o aro (eq. 8).

    ``T = P * A * (2 * tan²(a) - 1)``, em que ``a`` é o ângulo das cordas
    (45° típico). Para ``a = 35,27°`` a força é zero; abaixo disso o pneu
    tenderia a se alongar. O resultado pode ser negativo nessa faixa.
    """

    for name, value in (
        ("pressão", pressure_pa),
        ("diâmetro da seção do pneu", cross_section_diameter_mm),
        ("ângulo das cordas", cord_angle_deg),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser um número positivo.")
    if cord_angle_deg >= 90:
        raise ValueError("O ângulo das cordas deve ser menor que 90°.")

    radius_m = cross_section_diameter_mm / 2000.0
    area_m2 = math.pi * radius_m**2
    angle_rad = math.radians(cord_angle_deg)
    return pressure_pa * area_m2 * (2.0 * math.tan(angle_rad) ** 2 - 1.0)
