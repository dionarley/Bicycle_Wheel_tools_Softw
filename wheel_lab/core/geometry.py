"""Geometria básica da roda.

Referência: Jobst Brandt, *The Bicycle Wheel*, 3ª ed., Parte III, eq. 1.
"""

from __future__ import annotations

import math


def spoke_angle_deg(spoke_count: int, crossings: int) -> float:
    """Ângulo de cruzamento ``T`` em graus.

    ``T = 360 * X / (N / 2)``, em que ``X`` é o número de cruzamentos e ``N``
    o número total de raios. Para raios radiais (X=0), T=0.
    """

    if not isinstance(spoke_count, int) or isinstance(spoke_count, bool):
        raise ValueError("O número de raios deve ser um inteiro.")
    if spoke_count <= 0 or spoke_count % 2 != 0:
        raise ValueError("O número de raios deve ser par e positivo.")
    if not isinstance(crossings, int) or isinstance(crossings, bool):
        raise ValueError("O número de cruzamentos deve ser um inteiro.")
    if crossings < 0:
        raise ValueError("O número de cruzamentos não pode ser negativo.")
    if 8 * crossings > spoke_count:
        raise ValueError(
            f"Padrão inválido: {crossings}x com {spoke_count} raios. "
            f"O máximo é {max_crossings(spoke_count)}x (T ≤ 90°)."
        )
    if crossings == 0:
        return 0.0
    return 720.0 * crossings / spoke_count


def max_crossings(spoke_count: int) -> int:
    """Maior número de cruzamentos que mantém ``T <= 90°``."""

    if not isinstance(spoke_count, int) or isinstance(spoke_count, bool):
        raise ValueError("O número de raios deve ser um inteiro.")
    if spoke_count < 8 or spoke_count % 2 != 0:
        raise ValueError("O número de raios deve ser par e maior ou igual a 8.")
    return spoke_count // 8


def is_valid_cross_pattern(spoke_count: int, crossings: int) -> bool:
    if crossings < 0:
        return False
    try:
        return crossings <= max_crossings(spoke_count)
    except ValueError:
        return False


def erd_from_outer_diameter(
    outer_diameter_mm: float, nipple_drop_mm: float
) -> float:
    """Calcula o ERD a partir do diâmetro externo e da profundidade do niple.

    Brandt (p. 126): mede-se quanto a cabeça do niple fica abaixo da borda
    externa do aro; esse valor é dobrado e subtraído do diâmetro externo.

    ``nipple_drop_mm`` é a distância da borda externa do aro até o ponto em
    que a ponta do raio fica flush com o fim do niple.
    """

    if not math.isfinite(outer_diameter_mm) or outer_diameter_mm <= 0:
        raise ValueError("O diâmetro externo do aro deve ser positivo.")
    if not math.isfinite(nipple_drop_mm) or nipple_drop_mm < 0:
        raise ValueError("A profundidade do niple não pode ser negativa.")

    erd = outer_diameter_mm - 2.0 * nipple_drop_mm
    if erd <= 0:
        raise ValueError("O ERD calculado é inválido; confira as medidas do aro.")
    return erd
