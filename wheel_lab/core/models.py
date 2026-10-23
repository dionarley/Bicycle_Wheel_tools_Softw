"""Modelos de dados do Wheel Lab."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    """Lado da roda em relação ao plano central."""

    LEFT = "left"
    RIGHT = "right"

    @property
    def label_pt(self) -> str:
        return "esquerdo" if self is Side.LEFT else "direito"

    @property
    def sign(self) -> int:
        """Sinal usado para deslocamentos laterais (esquerda = -1)."""
        return -1 if self is Side.LEFT else 1


class SpokeDirection(str, Enum):
    """Sentido do raio em relação ao sentido de rolagem (leading/trailing)."""

    LEADING = "leading"
    TRAILING = "trailing"

    @property
    def label_pt(self) -> str:
        return "leading" if self is SpokeDirection.LEADING else "trailing"

    @property
    def sign(self) -> int:
        return 1 if self is SpokeDirection.LEADING else -1


@dataclass(frozen=True)
class WheelSpec:
    """Medidas necessárias para calcular os comprimentos dos raios.

    Os offsets são as distâncias **do plano do aro ao flange** (o ``C`` da
    equação 1 de Brandt). Em uma roda centralizada, isso equivale à distância
    do centro do cubo ao flange.

    ``erd_mm`` é o *effective rim diameter*: o diâmetro em que as pontas dos
    raios ficam flush com a extremidade do niple.
    """

    erd_mm: float
    left_flange_diameter_mm: float
    right_flange_diameter_mm: float
    left_flange_offset_mm: float
    right_flange_offset_mm: float
    hole_diameter_mm: float = 2.6
    spoke_count: int = 32
    crossings: int = 3

    def validate(self) -> None:
        """Valida as medidas e o padrão de cruzamentos.

        Levanta ``ValueError`` com uma mensagem em português para a UI.
        """

        _require_positive("ERD", self.erd_mm)
        _require_positive("Diâmetro do flange esquerdo", self.left_flange_diameter_mm)
        _require_positive("Diâmetro do flange direito", self.right_flange_diameter_mm)
        _require_positive("Offset do flange esquerdo", self.left_flange_offset_mm)
        _require_positive("Offset do flange direito", self.right_flange_offset_mm)
        _require_positive("Diâmetro do furo do flange", self.hole_diameter_mm)

        if self.left_flange_diameter_mm >= self.erd_mm:
            raise ValueError("O diâmetro do flange esquerdo deve ser menor que o ERD.")
        if self.right_flange_diameter_mm >= self.erd_mm:
            raise ValueError("O diâmetro do flange direito deve ser menor que o ERD.")
        if self.hole_diameter_mm >= min(
            self.left_flange_diameter_mm, self.right_flange_diameter_mm
        ):
            raise ValueError(
                "O diâmetro do furo do flange deve ser menor que o diâmetro do flange."
            )

        if not isinstance(self.spoke_count, int) or isinstance(self.spoke_count, bool):
            raise ValueError("O número de raios deve ser um inteiro.")
        if self.spoke_count < 8 or self.spoke_count % 2 != 0:
            raise ValueError("O número de raios deve ser par e maior ou igual a 8.")

        if not isinstance(self.crossings, int) or isinstance(self.crossings, bool):
            raise ValueError("O número de cruzamentos deve ser um inteiro.")
        if self.crossings < 0:
            raise ValueError("O número de cruzamentos não pode ser negativo.")

        max_x = self.spoke_count // 8
        if self.crossings > max_x:
            raise ValueError(
                f"Padrão inválido: {self.crossings}x com {self.spoke_count} raios. "
                f"O máximo é {max_x}x (ângulo de cruzamento ≤ 90°)."
            )


@dataclass(frozen=True)
class SpokeLengthResult:
    """Resultado do cálculo de comprimento para os dois lados."""

    spec: WheelSpec
    angle_deg: float
    left_mm: float
    right_mm: float
    left_purchase_mm: int
    right_purchase_mm: int

    def length_for(self, side: Side) -> float:
        return self.left_mm if side is Side.LEFT else self.right_mm

    def purchase_for(self, side: Side) -> int:
        return self.left_purchase_mm if side is Side.LEFT else self.right_purchase_mm


@dataclass(frozen=True)
class Spoke:
    """Um raio posicionado no padrão de montagem (para desenho e simulação)."""

    index: int
    side: Side
    direction: SpokeDirection
    rim_angle_deg: float
    hub_angle_deg: float

    @property
    def is_leading(self) -> bool:
        return self.direction is SpokeDirection.LEADING


def _require_positive(name: str, value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} deve ser um número positivo.")
