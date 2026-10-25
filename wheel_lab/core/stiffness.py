"""Estimativas de rigidez da roda (Fase 4).

A rigidez lateral e a radial vêm do mesmo modelo de anel + raios do solver de
alinhamento: aplica-se 1 N em cada nó do aro e mede-se o deslocamento
correspondente. A rigidez torsional é uma estimativa analítica separada, pois o
modelo de truing tem apenas graus de liberdade radial e lateral.

Os valores são de **ponto** e dependem das propriedades equivalentes do aro.
Use-os para comparar montagens e detectar configurações muito flexíveis, não
como substituto de um ensaio de rigidez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Side, WheelSpec
from .spoke_length import calculate_spoke_lengths
from .truing import (
    SPOKE_ELASTIC_MODULUS_MPA,
    RimElasticProperties,
    TruingState,
)


@dataclass(frozen=True)
class WheelStiffness:
    """Rigidez estimada de uma roda montada."""

    lateral_n_per_mm: float
    lateral_min_n_per_mm: float
    lateral_max_n_per_mm: float
    radial_n_per_mm: float
    radial_min_n_per_mm: float
    radial_max_n_per_mm: float
    torsional_nm_per_deg: float
    lateral_point_n_per_mm: tuple[float, ...]
    radial_point_n_per_mm: tuple[float, ...]
    spoke_count: int
    active_spoke_count: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "lateral_n_per_mm": self.lateral_n_per_mm,
            "lateral_min_n_per_mm": self.lateral_min_n_per_mm,
            "lateral_max_n_per_mm": self.lateral_max_n_per_mm,
            "radial_n_per_mm": self.radial_n_per_mm,
            "radial_min_n_per_mm": self.radial_min_n_per_mm,
            "radial_max_n_per_mm": self.radial_max_n_per_mm,
            "torsional_nm_per_deg": self.torsional_nm_per_deg,
            "lateral_point_n_per_mm": list(self.lateral_point_n_per_mm),
            "radial_point_n_per_mm": list(self.radial_point_n_per_mm),
            "spoke_count": self.spoke_count,
            "active_spoke_count": self.active_spoke_count,
            "warnings": list(self.warnings),
        }

    def summary_lines(self) -> list[str]:
        lines = [
            "=== RIGIDEZ DA RODA ===",
            (
                f"Lateral: {_fmt(self.lateral_n_per_mm, 1)} N/mm "
                f"(mín. {_fmt(self.lateral_min_n_per_mm, 1)}, "
                f"máx. {_fmt(self.lateral_max_n_per_mm, 1)})"
            ),
            (
                f"Radial: {_fmt(self.radial_n_per_mm, 1)} N/mm "
                f"(mín. {_fmt(self.radial_min_n_per_mm, 1)}, "
                f"máx. {_fmt(self.radial_max_n_per_mm, 1)})"
            ),
            (
                "Torsional: "
                f"{_fmt(self.torsional_nm_per_deg, 2)} N·m/° "
                "(estimativa analítica)"
            ),
            (
                f"Raios ativos: {self.active_spoke_count} de "
                f"{self.spoke_count}"
            ),
        ]
        if self.warnings:
            lines.append("")
            lines.append("Avisos:")
            lines.extend(f"• {warning}" for warning in self.warnings)
        return lines

    def summary_text(self) -> str:
        return "\n".join(self.summary_lines())


def estimate_wheel_stiffness(
    spec: WheelSpec,
    target_tension_n: float,
    spoke_diameter_mm: float,
    rim_properties: RimElasticProperties | None = None,
    spoke_elastic_modulus_mpa: float = SPOKE_ELASTIC_MODULUS_MPA,
) -> WheelStiffness:
    """Estima a rigidez lateral, radial e torsional da roda.

    A rigidez lateral/radial é a média das rigidezes de ponto nos furos do aro.
    A torsional usa a componente tangencial dos raios e a rotação relativa
    cubo↔aro; é uma estimativa de ordem de grandeza.
    """

    state = TruingState(
        spec,
        target_tension_n,
        spoke_diameter_mm,
        rim_properties=rim_properties,
        spoke_elastic_modulus_mpa=spoke_elastic_modulus_mpa,
    )
    radial_points, lateral_points = state.point_stiffnesses()
    lateral_values = _positive_finite_values(
        lateral_points, "rigidez lateral"
    )
    radial_values = _positive_finite_values(
        radial_points, "rigidez radial"
    )
    if not lateral_values or not radial_values:
        raise ValueError(
            "Não foi possível estimar a rigidez: deslocamentos nulos ou "
            "inválidos."
        )

    torsional = _torsional_stiffness_nm_per_deg(state)
    warnings: list[str] = []
    if state.slack_indices:
        warnings.append(
            "Há raios frouxos; a rigidez estimada usa apenas os raios ativos."
        )
    if spec.crossings == 0:
        warnings.append(
            "Montagem radial: a componente tangencial é nula e a rigidez "
            "torsional estimada é zero."
        )
    if min(lateral_values) < 10.0:
        warnings.append(
            "Rigidez lateral de ponto muito baixa em alguns furos; confira "
            "tensões, aro e padrão de montagem."
        )
    if min(radial_values) < 100.0:
        warnings.append(
            "Rigidez radial de ponto muito baixa em alguns furos; confira "
            "tensões e propriedades do aro."
        )

    return WheelStiffness(
        lateral_n_per_mm=sum(lateral_values) / len(lateral_values),
        lateral_min_n_per_mm=min(lateral_values),
        lateral_max_n_per_mm=max(lateral_values),
        radial_n_per_mm=sum(radial_values) / len(radial_values),
        radial_min_n_per_mm=min(radial_values),
        radial_max_n_per_mm=max(radial_values),
        torsional_nm_per_deg=torsional,
        lateral_point_n_per_mm=lateral_points,
        radial_point_n_per_mm=radial_points,
        spoke_count=spec.spoke_count,
        active_spoke_count=sum(1 for active in state.active if active),
        warnings=tuple(warnings),
    )


def _torsional_stiffness_nm_per_deg(state: TruingState) -> float:
    """Rigidez torsional aproximada a partir da componente tangencial."""

    spec = state.spec
    result = calculate_spoke_lengths(spec)
    angle_rad = math.radians(result.angle_deg)
    total_n_mm_per_rad = 0.0
    for index, geometry in enumerate(state.geometries):
        if not state.active[index]:
            continue
        if geometry.side is Side.LEFT:
            flange_radius = spec.left_flange_diameter_mm / 2.0
        else:
            flange_radius = spec.right_flange_diameter_mm / 2.0
        tangential_offset = flange_radius * math.sin(angle_rad)
        geometric_length = (
            geometry.free_length_mm + spec.hole_diameter_mm / 2.0
        )
        if geometric_length <= 0:
            continue
        tangential_component = tangential_offset / geometric_length
        moment_arm = flange_radius * tangential_component
        total_n_mm_per_rad += (
            geometry.stiffness_n_per_mm * moment_arm * moment_arm
        )
    return total_n_mm_per_rad * math.pi / 180_000.0


def _positive_finite_values(
    values: tuple[float, ...], label: str
) -> list[float]:
    result = [
        value
        for value in values
        if math.isfinite(value) and value > 0.0
    ]
    if len(result) != len(values):
        # Não é um erro: alguns pontos podem ter deslocamento nulo por
        # simetria. A média usa apenas os valores finitos.
        return result
    if not result:
        raise ValueError(f"Não foi possível estimar a {label}.")
    return result


def _fmt(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


__all__ = ["WheelStiffness", "estimate_wheel_stiffness"]
