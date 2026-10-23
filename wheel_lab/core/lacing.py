"""Padrão de montagem (lacing) para desenho e simulação.

O padrão implementado é o mais comum em rodas de 24 a 48 raios: os raios
alternam de lado a cada furo do aro e alternam leading/trailing a cada dois
furos. É um modelo esquemático, suficiente para o visualizador e para a
simulação didática; a geometria exata dos furos do cubo entra na Fase 2.
"""

from __future__ import annotations

from .geometry import spoke_angle_deg
from .models import Side, Spoke, SpokeDirection


def build_spoke_table(spoke_count: int, crossings: int) -> list[Spoke]:
    """Monta a tabela de raios em ordem ao redor do aro.

    Índices pares ficam à esquerda e ímpares à direita. A cada dois raios o
    sentido muda: leading, leading, trailing, trailing, ...
    """

    if not isinstance(spoke_count, int) or isinstance(spoke_count, bool):
        raise ValueError("O número de raios deve ser um inteiro.")
    if spoke_count < 8 or spoke_count % 4 != 0:
        raise ValueError(
            "O padrão visual exige número de raios múltiplo de 4 (24, 28, 32, 36...)."
        )

    angle = spoke_angle_deg(spoke_count, crossings)
    spokes: list[Spoke] = []

    for index in range(spoke_count):
        rim_angle = 360.0 * index / spoke_count
        side = Side.LEFT if index % 2 == 0 else Side.RIGHT
        direction = (
            SpokeDirection.LEADING
            if (index // 2) % 2 == 0
            else SpokeDirection.TRAILING
        )
        hub_angle = rim_angle + direction.sign * angle
        spokes.append(
            Spoke(
                index=index,
                side=side,
                direction=direction,
                rim_angle_deg=rim_angle,
                hub_angle_deg=hub_angle,
            )
        )

    return spokes
