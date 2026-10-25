"""Solver físico de alinhamento (Fase 2).

Modelo:
- o aro é um anel elástico discretizado nos furos dos raios, com rigidez de
  flexão lateral, flexão no plano e membrana (hoop);
- cada raio é uma mola axial só-tração entre o cubo fixo e o aro;
- o ajuste do niple encurta o comprimento livre do raio e aplica uma força;
- o equilíbrio é resolvido para deslocamentos radiais e laterais pequenos;
- raios que ficam frouxos são desativados e o sistema é resolvido de novo.

As propriedades do aro são rigidezes equivalentes calibradas para um aro de
alumínio de perfil médio, não a geometria literal da seção. O modelo é
incremental: parte da forma atual (runout medido ou didático) e calcula a
mudança causada pelos ajustes de niple. As sugestões são um passo linearizado:
aplique, recalcule e repita, como no truing real.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .lacing import build_spoke_table
from .models import Side, SpokeDirection, WheelSpec
from .spoke_length import calculate_spoke_lengths
from .tension import lateral_tension_ratio, target_tensions
from .units import SPOKE_THREAD_PITCH_MM, turns_to_mm

SPOKE_ELASTIC_MODULUS_MPA = 193_000.0
"""Módulo de elasticidade do aço dos raios, em N/mm²."""

SLACK_TOLERANCE_N = 1.0
"""Tensão abaixo da qual o raio é considerado frouxo."""


@dataclass(frozen=True)
class RimElasticProperties:
    """Propriedades elásticas equivalentes do aro.

    Os valores padrão são rigidezes equivalentes de um aro de alumínio de
    perfil médio. Para um aro muito leve ou muito rígido, ajuste
    ``lateral_inertia_mm4``, ``inplane_inertia_mm4`` e
    ``cross_section_area_mm2``.
    """

    elastic_modulus_mpa: float = 69_000.0
    lateral_inertia_mm4: float = 7_000.0
    inplane_inertia_mm4: float = 1_500.0
    cross_section_area_mm2: float = 40.0

    def validate(self) -> None:
        for name, value in (
            ("Módulo de elasticidade do aro", self.elastic_modulus_mpa),
            ("Inércia lateral do aro", self.lateral_inertia_mm4),
            ("Inércia no plano do aro", self.inplane_inertia_mm4),
            ("Área da seção do aro", self.cross_section_area_mm2),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} deve ser um número positivo.")


@dataclass(frozen=True)
class SpokeGeometry:
    """Geometria e rigidez de um raio na posição de montagem."""

    index: int
    side: Side
    direction: SpokeDirection
    rim_angle_deg: float
    hub_angle_deg: float
    free_length_mm: float
    radial_component: float
    lateral_component: float
    stiffness_n_per_mm: float
    initial_tension_n: float


@dataclass(frozen=True)
class TruingResult:
    """Resultado de um passo de ajuste."""

    lateral_mm: tuple[float, ...]
    radial_mm: tuple[float, ...]
    tensions_n: tuple[float, ...]
    active: tuple[bool, ...]
    delta_lateral_mm: tuple[float, ...]
    delta_radial_mm: tuple[float, ...]
    delta_tensions_n: tuple[float, ...]
    lateral_runout_before_mm: float
    radial_runout_before_mm: float
    lateral_runout_mm: float
    radial_runout_mm: float
    min_tension_n: float
    max_tension_n: float
    slack_indices: tuple[int, ...]
    iterations: int


@dataclass(frozen=True)
class SuggestedAdjustment:
    """Um ajuste de niple sugerido pelo solver."""

    index: int
    side: Side
    direction: SpokeDirection
    turns: float
    shortening_mm: float
    predicted_tension_n: float
    predicted_tension_change_n: float


@dataclass(frozen=True)
class TruingSuggestion:
    """Sugestão de ajustes para reduzir o runout atual."""

    adjustments: tuple[SuggestedAdjustment, ...]
    predicted_lateral_mm: tuple[float, ...]
    predicted_radial_mm: tuple[float, ...]
    predicted_tensions_n: tuple[float, ...]
    current_lateral_runout_mm: float
    current_radial_runout_mm: float
    predicted_lateral_runout_mm: float
    predicted_radial_runout_mm: float
    warnings: tuple[str, ...]


def build_spoke_geometries(
    spec: WheelSpec,
    spoke_diameter_mm: float,
    target_tension_n: float,
    spoke_elastic_modulus_mpa: float = SPOKE_ELASTIC_MODULUS_MPA,
) -> list[SpokeGeometry]:
    """Monta a geometria elástica de todos os raios.

    O componente radial é ``B/L``. O componente lateral é ``+C/L`` para
    raios esquerdos e ``-C/L`` para direitos, pois o eixo lateral positivo
    aponta para a direita.
    """

    if not math.isfinite(target_tension_n) or target_tension_n <= 0:
        raise ValueError("A tensão alvo deve ser um número positivo.")
    if not math.isfinite(spoke_diameter_mm) or spoke_diameter_mm <= 0:
        raise ValueError("O diâmetro do raio deve ser um número positivo.")
    if (
        not math.isfinite(spoke_elastic_modulus_mpa)
        or spoke_elastic_modulus_mpa <= 0
    ):
        raise ValueError("O módulo do raio deve ser um número positivo.")

    spec.validate()
    if spec.spoke_count % 4 != 0:
        raise ValueError(
            "O solver físico exige número de raios múltiplo de 4."
        )

    result = calculate_spoke_lengths(spec)
    ratio = lateral_tension_ratio(
        spec.effective_left_offset_mm,
        spec.effective_right_offset_mm,
        result.left_mm,
        result.right_mm,
    )
    tighter = Side.RIGHT if ratio <= 1.0 else Side.LEFT
    base_tensions = target_tensions(target_tension_n, ratio, tighter)

    radius = spec.erd_mm / 2.0
    angle_rad = math.radians(result.angle_deg)
    spoke_area_mm2 = math.pi * (spoke_diameter_mm / 2.0) ** 2
    spokes = build_spoke_table(spec.spoke_count, spec.crossings)

    geometries: list[SpokeGeometry] = []
    for spoke in spokes:
        if spoke.side is Side.LEFT:
            flange_diameter = spec.left_flange_diameter_mm
            offset = spec.effective_left_offset_mm
            lateral_sign = 1.0
        else:
            flange_diameter = spec.right_flange_diameter_mm
            offset = spec.effective_right_offset_mm
            lateral_sign = -1.0

        a = (flange_diameter / 2.0) * math.sin(angle_rad)
        b = radius - (flange_diameter / 2.0) * math.cos(angle_rad)
        c = offset
        geometric_length = math.sqrt(a * a + b * b + c * c)
        free_length = geometric_length - spec.hole_diameter_mm / 2.0
        if free_length <= 0 or not math.isfinite(free_length):
            raise ValueError("Comprimento de raio inválido no solver físico.")

        stiffness = (
            spoke_elastic_modulus_mpa * spoke_area_mm2 / free_length
        )
        geometries.append(
            SpokeGeometry(
                index=spoke.index,
                side=spoke.side,
                direction=spoke.direction,
                rim_angle_deg=spoke.rim_angle_deg,
                hub_angle_deg=spoke.hub_angle_deg,
                free_length_mm=free_length,
                radial_component=b / geometric_length,
                lateral_component=lateral_sign * c / geometric_length,
                stiffness_n_per_mm=stiffness,
                initial_tension_n=base_tensions[spoke.side],
            )
        )
    return geometries


class TruingState:
    """Estado físico de uma roda durante o alinhamento."""

    def __init__(
        self,
        spec: WheelSpec,
        target_tension_n: float,
        spoke_diameter_mm: float,
        rim_properties: RimElasticProperties | None = None,
        initial_lateral_mm: Sequence[float] | None = None,
        initial_radial_mm: Sequence[float] | None = None,
        initial_tensions_n: Sequence[float] | None = None,
        spoke_elastic_modulus_mpa: float = SPOKE_ELASTIC_MODULUS_MPA,
    ) -> None:
        self.spec = spec
        self.target_tension_n = float(target_tension_n)
        self.spoke_diameter_mm = float(spoke_diameter_mm)
        self.rim_properties = rim_properties or RimElasticProperties()
        self.rim_properties.validate()
        self.geometries = build_spoke_geometries(
            spec,
            spoke_diameter_mm,
            target_tension_n,
            spoke_elastic_modulus_mpa,
        )
        count = spec.spoke_count
        self.lateral_mm = _fit_sequence(
            initial_lateral_mm, count, "deslocamento lateral"
        )
        self.radial_mm = _fit_sequence(
            initial_radial_mm, count, "deslocamento radial"
        )
        if initial_tensions_n is None:
            self.tensions_n = [
                geometry.initial_tension_n for geometry in self.geometries
            ]
        else:
            self.tensions_n = _fit_sequence(
                initial_tensions_n, count, "tensão"
            )
            if any(value < 0 for value in self.tensions_n):
                raise ValueError("As tensões não podem ser negativas.")
        self.active = [
            tension > SLACK_TOLERANCE_N for tension in self.tensions_n
        ]
        self.slack_gap_mm = [0.0] * count

    @property
    def lateral_runout_mm(self) -> float:
        return max(self.lateral_mm) - min(self.lateral_mm)

    @property
    def radial_runout_mm(self) -> float:
        return max(self.radial_mm) - min(self.radial_mm)

    @property
    def min_tension_n(self) -> float:
        return min(self.tensions_n)

    @property
    def max_tension_n(self) -> float:
        return max(self.tensions_n)

    @property
    def slack_indices(self) -> tuple[int, ...]:
        return tuple(
            index for index, active in enumerate(self.active) if not active
        )

    def tension_for(self, index: int) -> float:
        self._check_index(index)
        return self.tensions_n[index]

    def apply_turns(self, turns: Mapping[int, float]) -> TruingResult:
        """Aplica voltas de niple (positivo = apertar)."""

        adjustments_mm: dict[int, float] = {}
        for index, value in turns.items():
            if not math.isfinite(value):
                raise ValueError("O número de voltas deve ser finito.")
            adjustments_mm[int(index)] = turns_to_mm(float(value))
        return self.apply_adjustments(adjustments_mm)

    def apply_adjustments(
        self, adjustments_mm: Mapping[int, float]
    ) -> TruingResult:
        """Aplica encurtamentos do comprimento livre, em mm.

        ``adjustments_mm[i] > 0`` significa apertar o niple do raio ``i``.
        """

        self._check_adjustments(adjustments_mm)
        before_lateral = self.lateral_runout_mm
        before_radial = self.radial_runout_mm
        before_tensions = list(self.tensions_n)
        delta, tensions, active, gaps, iterations = self._solve(
            adjustments_mm
        )

        self.lateral_mm = [
            value + delta[2 * index + 1]
            for index, value in enumerate(self.lateral_mm)
        ]
        self.radial_mm = [
            value + delta[2 * index]
            for index, value in enumerate(self.radial_mm)
        ]
        self.tensions_n = tensions
        self.active = active
        self.slack_gap_mm = gaps

        return TruingResult(
            lateral_mm=tuple(self.lateral_mm),
            radial_mm=tuple(self.radial_mm),
            tensions_n=tuple(self.tensions_n),
            active=tuple(self.active),
            delta_lateral_mm=tuple(delta[1::2]),
            delta_radial_mm=tuple(delta[0::2]),
            delta_tensions_n=tuple(
                after - before
                for after, before in zip(self.tensions_n, before_tensions)
            ),
            lateral_runout_before_mm=before_lateral,
            radial_runout_before_mm=before_radial,
            lateral_runout_mm=self.lateral_runout_mm,
            radial_runout_mm=self.radial_runout_mm,
            min_tension_n=self.min_tension_n,
            max_tension_n=self.max_tension_n,
            slack_indices=self.slack_indices,
            iterations=iterations,
        )

    def influence_matrix(self) -> tuple[tuple[float, ...], ...]:
        """Resposta do aro a 1 mm de aperto em cada raio.

        Cada coluna tem ``2*N`` valores: deslocamento radial e lateral de cada
        nó do aro. A matriz é calculada no estado atual de tensões. Raios
        frouxos têm coluna nula, pois ainda não respondem ao aperto.
        """

        if not any(self.active):
            raise ValueError(
                "Não há raios tensionados; aperte ao menos um raio antes de "
                "calcular a influência."
            )
        count = len(self.geometries)
        stiffness = self._assemble_stiffness(self.active, self.tensions_n)
        factor = _cholesky_factor(stiffness)
        columns: list[tuple[float, ...]] = []
        for index, geometry in enumerate(self.geometries):
            if not self.active[index]:
                # Um raio frouxo não responde até a folga ser fechada; a
                # sugestão linear não deve contar com ele.
                columns.append(tuple([0.0] * (2 * count)))
                continue
            load = [0.0] * (2 * count)
            load[2 * index] = (
                -geometry.stiffness_n_per_mm * geometry.radial_component
            )
            load[2 * index + 1] = (
                -geometry.stiffness_n_per_mm * geometry.lateral_component
            )
            columns.append(tuple(_cholesky_solve(factor, load)))
        return tuple(columns)

    def stiffness_matrix(self) -> tuple[tuple[float, ...], ...]:
        """Matriz de rigidez tangente do aro com os raios ativos.

        A ordem dos graus de liberdade é ``[radial, lateral]`` por nó. A
        matriz é montada no estado atual de tensões e pode ser usada para
        estimar a rigidez da roda a cargas laterais e radiais.
        """

        if not any(self.active):
            raise ValueError(
                "Não há raios tensionados; aperte ao menos um raio antes de "
                "calcular a rigidez."
            )
        matrix = self._assemble_stiffness(self.active, self.tensions_n)
        return tuple(tuple(row) for row in matrix)

    def point_stiffnesses(
        self,
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Rigidez radial e lateral em cada nó do aro, em N/mm.

        Aplica 1 N no nó e mede o deslocamento correspondente. O resultado
        representa a rigidez de ponto da roda montada; não é uma rigidez
        global de corpo rígido. Raios frouxos não contribuem.
        """

        count = len(self.geometries)
        stiffness = [list(row) for row in self.stiffness_matrix()]
        factor = _cholesky_factor(stiffness)
        radial: list[float] = []
        lateral: list[float] = []
        for index in range(count):
            radial_load = [0.0] * (2 * count)
            radial_load[2 * index] = 1.0
            radial_delta = _cholesky_solve(factor, radial_load)
            radial.append(_inverse_compliance(radial_delta[2 * index]))

            lateral_load = [0.0] * (2 * count)
            lateral_load[2 * index + 1] = 1.0
            lateral_delta = _cholesky_solve(factor, lateral_load)
            lateral.append(_inverse_compliance(lateral_delta[2 * index + 1]))
        return tuple(radial), tuple(lateral)

    def suggest_adjustments(
        self,
        target_lateral_mm: Sequence[float] | None = None,
        target_radial_mm: Sequence[float] | None = None,
        lateral_weight: float = 1.0,
        radial_weight: float = 0.5,
        regularization: float = 1e-4,
        max_turns: float = 1.0,
        min_turns: float = 0.05,
        round_to_quarter_turn: bool = True,
    ) -> TruingSuggestion:
        """Calcula um passo de ajustes para reduzir o runout.

        O alvo padrão é zero. A solução é um mínimo quadrado regularizado;
        o passo inteiro é reduzido para respeitar ``max_turns`` e arredondado
        para 1/4 de volta. Aplique o passo e recalcule, como no alinhamento
        real.
        """

        if not math.isfinite(max_turns) or max_turns <= 0:
            raise ValueError("O limite de voltas deve ser positivo.")
        if not math.isfinite(min_turns) or min_turns < 0:
            raise ValueError("O mínimo de voltas não pode ser negativo.")
        if not math.isfinite(regularization) or regularization < 0:
            raise ValueError("A regularização não pode ser negativa.")
        for name, value in (
            ("peso lateral", lateral_weight),
            ("peso radial", radial_weight),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"O {name} não pode ser negativo.")

        count = len(self.geometries)
        target_lateral = _fit_sequence(
            target_lateral_mm, count, "alvo lateral"
        )
        target_radial = _fit_sequence(target_radial_mm, count, "alvo radial")
        desired = [0.0] * (2 * count)
        for index in range(count):
            desired[2 * index] = (
                target_radial[index] - self.radial_mm[index]
            ) * radial_weight
            desired[2 * index + 1] = (
                target_lateral[index] - self.lateral_mm[index]
            ) * lateral_weight

        influence = self.influence_matrix()
        weighted_columns: list[list[float]] = []
        for column in influence:
            weighted = list(column)
            for index in range(count):
                weighted[2 * index] *= radial_weight
                weighted[2 * index + 1] *= lateral_weight
            weighted_columns.append(weighted)

        normal = [[0.0] * count for _ in range(count)]
        rhs = [0.0] * count
        for row in range(count):
            column = weighted_columns[row]
            for col in range(count):
                normal[row][col] = sum(
                    column[dof] * weighted_columns[col][dof]
                    for dof in range(2 * count)
                )
            rhs[row] = sum(
                column[dof] * desired[dof] for dof in range(2 * count)
            )
        for index in range(count):
            normal[index][index] += regularization

        shortening = _solve_linear_system(normal, rhs)

        # O mínimo quadrado costuma pedir ajustes grandes e espalhados. Em vez
        # de limitar cada raio isoladamente (o que destrói o padrão da solução),
        # reduzimos o passo inteiro por um fator comum. Assim o padrão espacial
        # é preservado e o runout cai de forma monotônica na região linear.
        max_shortening = max_turns * SPOKE_THREAD_PITCH_MM
        peak = max((abs(value) for value in shortening), default=0.0)
        was_limited = peak > max_shortening > 0.0
        if was_limited:
            scale = max_shortening / peak
            shortening = [value * scale for value in shortening]

        if round_to_quarter_turn:
            quarter_limit = math.floor(max_turns * 4.0 + 1e-9) / 4.0
            for index, value in enumerate(shortening):
                turns = value / SPOKE_THREAD_PITCH_MM
                turns = round(turns * 4.0) / 4.0
                if abs(turns) > quarter_limit:
                    turns = math.copysign(quarter_limit, turns)
                shortening[index] = turns * SPOKE_THREAD_PITCH_MM

        predicted_delta = [0.0] * (2 * count)
        for spoke_index, column in enumerate(influence):
            value = shortening[spoke_index]
            if value == 0.0:
                continue
            for dof in range(2 * count):
                predicted_delta[dof] += column[dof] * value

        predicted_lateral = tuple(
            self.lateral_mm[index] + predicted_delta[2 * index + 1]
            for index in range(count)
        )
        predicted_radial = tuple(
            self.radial_mm[index] + predicted_delta[2 * index]
            for index in range(count)
        )
        predicted_tensions: list[float] = []
        for index, geometry in enumerate(self.geometries):
            gap = 0.0 if self.active[index] else self.slack_gap_mm[index]
            stretch = (
                geometry.radial_component * predicted_delta[2 * index]
                + geometry.lateral_component * predicted_delta[2 * index + 1]
                + shortening[index]
                - gap
            )
            base = self.tensions_n[index] if self.active[index] else 0.0
            predicted_tensions.append(
                max(0.0, base + geometry.stiffness_n_per_mm * stretch)
            )

        adjustments: list[SuggestedAdjustment] = []
        for index, geometry in enumerate(self.geometries):
            turns = shortening[index] / SPOKE_THREAD_PITCH_MM
            if abs(turns) < min_turns:
                continue
            adjustments.append(
                SuggestedAdjustment(
                    index=index,
                    side=geometry.side,
                    direction=geometry.direction,
                    turns=turns,
                    shortening_mm=shortening[index],
                    predicted_tension_n=predicted_tensions[index],
                    predicted_tension_change_n=(
                        predicted_tensions[index] - self.tensions_n[index]
                    ),
                )
            )
        adjustments.sort(key=lambda item: abs(item.turns), reverse=True)

        warnings: list[str] = []
        if self.slack_indices:
            warnings.append(
                "Há raios frouxos; aperte-os antes de usar as sugestões."
            )
        if any(tension <= SLACK_TOLERANCE_N for tension in predicted_tensions):
            warnings.append(
                "Alguns raios ficariam frouxos; aplique um passo menor."
            )
        if self.target_tension_n > 0 and adjustments:
            if max(predicted_tensions) > 1.5 * self.target_tension_n:
                warnings.append(
                    "A tensão máxima prevista passa de 150% da tensão alvo; "
                    "aplique um passo menor e confira o limite do aro."
                )
            if min(predicted_tensions) < 0.25 * self.target_tension_n:
                warnings.append(
                    "A tensão mínima prevista fica abaixo de 25% da tensão "
                    "alvo; aplique um passo menor."
                )
        if was_limited and adjustments:
            warnings.append(
                f"Ajustes limitados a {max_turns:.2f} volta(s); repita após "
                "aplicar."
            )
        predicted_lateral_runout = max(predicted_lateral) - min(
            predicted_lateral
        )
        predicted_radial_runout = max(predicted_radial) - min(
            predicted_radial
        )
        if adjustments and (
            predicted_lateral_runout >= self.lateral_runout_mm
            and predicted_radial_runout >= self.radial_runout_mm
        ):
            warnings.append(
                "O passo calculado não reduziu o runout; confira o modelo ou "
                "a tolerância."
            )
        if not adjustments:
            warnings.append(
                "Nenhum ajuste acima do mínimo; a roda já está próxima do alvo."
            )

        return TruingSuggestion(
            adjustments=tuple(adjustments),
            predicted_lateral_mm=predicted_lateral,
            predicted_radial_mm=predicted_radial,
            predicted_tensions_n=tuple(predicted_tensions),
            current_lateral_runout_mm=self.lateral_runout_mm,
            current_radial_runout_mm=self.radial_runout_mm,
            predicted_lateral_runout_mm=predicted_lateral_runout,
            predicted_radial_runout_mm=predicted_radial_runout,
            warnings=tuple(warnings),
        )

    def _solve(
        self, adjustments_mm: Mapping[int, float]
    ) -> tuple[list[float], list[float], list[bool], list[float], int]:
        count = len(self.geometries)
        initial_active = list(self.active)
        initial_tensions = list(self.tensions_n)
        initial_gaps = list(self.slack_gap_mm)
        adjustments = {
            index: float(value) for index, value in adjustments_mm.items()
        }
        zero = [0.0] * (2 * count)

        def tensions_for(delta: Sequence[float]) -> list[float]:
            values: list[float] = []
            for index, geometry in enumerate(self.geometries):
                shortening = adjustments.get(index, 0.0)
                stretch = (
                    geometry.radial_component * delta[2 * index]
                    + geometry.lateral_component * delta[2 * index + 1]
                    + shortening
                )
                if initial_active[index]:
                    value = (
                        initial_tensions[index]
                        + geometry.stiffness_n_per_mm * stretch
                    )
                else:
                    value = geometry.stiffness_n_per_mm * (
                        stretch - initial_gaps[index]
                    )
                values.append(max(0.0, value))
            return values

        closes_gap = any(
            adjustments.get(index, 0.0) > initial_gaps[index]
            for index in range(count)
        )
        if not any(initial_active) and not closes_gap:
            return (
                zero,
                list(initial_tensions),
                list(initial_active),
                list(initial_gaps),
                0,
            )

        delta = zero
        active = list(initial_active)
        iterations = 0
        for iteration in range(count + 2):
            iterations = iteration + 1
            final_tensions = tensions_for(delta)
            new_active = [
                value > SLACK_TOLERANCE_N for value in final_tensions
            ]
            if not any(new_active):
                active = new_active
                break

            stiffness = self._assemble_stiffness(new_active, final_tensions)
            load = [0.0] * (2 * count)
            for index, geometry in enumerate(self.geometries):
                shortening = adjustments.get(index, 0.0)
                if new_active[index]:
                    gap = 0.0 if initial_active[index] else initial_gaps[index]
                    force = -geometry.stiffness_n_per_mm * (
                        shortening - gap
                    )
                elif initial_active[index]:
                    # O raio estava tensionado e ficou frouxo: a força que ele
                    # deixou de exercer é a tensão inicial.
                    force = initial_tensions[index]
                else:
                    force = 0.0
                load[2 * index] += force * geometry.radial_component
                load[2 * index + 1] += force * geometry.lateral_component

            new_delta = _solve_linear_system(stiffness, load)
            change = max(
                (
                    abs(after - before)
                    for after, before in zip(new_delta, delta)
                ),
                default=0.0,
            )
            delta = new_delta
            active = new_active

            next_tensions = tensions_for(delta)
            next_active = [
                value > SLACK_TOLERANCE_N for value in next_tensions
            ]
            if next_active == active and change < 1e-9:
                break

        final_tensions = tensions_for(delta)
        active = [value > SLACK_TOLERANCE_N for value in final_tensions]
        gaps: list[float] = []
        for index, geometry in enumerate(self.geometries):
            shortening = adjustments.get(index, 0.0)
            stretch = (
                geometry.radial_component * delta[2 * index]
                + geometry.lateral_component * delta[2 * index + 1]
                + shortening
            )
            if active[index]:
                gaps.append(0.0)
            elif initial_active[index]:
                gap = -(
                    initial_tensions[index]
                    / geometry.stiffness_n_per_mm
                    + stretch
                )
                gaps.append(max(0.0, gap))
            else:
                gaps.append(max(0.0, initial_gaps[index] - stretch))
        return delta, final_tensions, active, gaps, iterations

    def _assemble_stiffness(
        self, active: Sequence[bool], tensions: Sequence[float]
    ) -> list[list[float]]:
        count = len(self.geometries)
        size = 2 * count
        stiffness = [[0.0] * size for _ in range(size)]
        radius = self.spec.erd_mm / 2.0
        spacing = 2.0 * math.pi * radius / count
        modulus = self.rim_properties.elastic_modulus_mpa
        bend_lateral = (
            modulus * self.rim_properties.lateral_inertia_mm4 / spacing**3
        )
        bend_radial = (
            modulus * self.rim_properties.inplane_inertia_mm4 / spacing**3
        )
        hoop = (
            modulus
            * self.rim_properties.cross_section_area_mm2
            * spacing
            / radius**2
        )

        fourth_difference = (
            (0, 6.0),
            (-1, -4.0),
            (1, -4.0),
            (-2, 1.0),
            (2, 1.0),
        )
        for index in range(count):
            for offset, coefficient in fourth_difference:
                other = (index + offset) % count
                stiffness[2 * index][2 * other] += bend_radial * coefficient
                stiffness[2 * index + 1][2 * other + 1] += (
                    bend_lateral * coefficient
                )
            stiffness[2 * index][2 * index] += hoop

        for index, geometry in enumerate(self.geometries):
            if not active[index]:
                continue
            tension = max(tensions[index], 0.0)
            radial = geometry.radial_component
            lateral = geometry.lateral_component
            spring = geometry.stiffness_n_per_mm
            stiffness[2 * index][2 * index] += spring * radial * radial
            stiffness[2 * index][2 * index + 1] += spring * radial * lateral
            stiffness[2 * index + 1][2 * index] += spring * lateral * radial
            stiffness[2 * index + 1][2 * index + 1] += spring * lateral * lateral

            geometric = tension / geometry.free_length_mm
            stiffness[2 * index][2 * index] += geometric * (1.0 - radial * radial)
            stiffness[2 * index][2 * index + 1] += -geometric * radial * lateral
            stiffness[2 * index + 1][2 * index] += -geometric * lateral * radial
            stiffness[2 * index + 1][2 * index + 1] += geometric * (
                1.0 - lateral * lateral
            )
        return stiffness

    def _check_index(self, index: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("O índice do raio deve ser um inteiro.")
        if not 0 <= index < len(self.geometries):
            raise ValueError(
                f"O índice deve estar entre 0 e {len(self.geometries) - 1}."
            )

    def _check_adjustments(self, adjustments: Mapping[int, float]) -> None:
        for index, value in adjustments.items():
            self._check_index(index)
            if not math.isfinite(value):
                raise ValueError("O ajuste deve ser um número finito.")


def _inverse_compliance(displacement: float) -> float:
    """Converte deslocamento (mm/N) em rigidez de ponto (N/mm)."""

    magnitude = abs(displacement)
    if magnitude < 1e-12:
        return math.inf
    return 1.0 / magnitude


def _fit_sequence(
    values: Sequence[float] | None, size: int, label: str
) -> list[float]:
    if values is None:
        return [0.0] * size
    if len(values) != size:
        raise ValueError(
            f"{label}: esperados {size} valores, recebidos {len(values)}."
        )
    fitted: list[float] = []
    for value in values:
        if not math.isfinite(value):
            raise ValueError(f"{label}: todos os valores devem ser finitos.")
        fitted.append(float(value))
    return fitted


def _cholesky_factor(matrix: list[list[float]]) -> list[list[float]]:
    """Fatoração de Cholesky com pequena regularização numérica."""

    size = len(matrix)
    scale = max(
        (abs(matrix[index][index]) for index in range(size)),
        default=1.0,
    )
    jitter = max(scale * 1e-12, 1e-12)
    factor = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for col in range(row + 1):
            value = matrix[row][col]
            if row == col:
                value += jitter
            total = value - sum(
                factor[row][k] * factor[col][k] for k in range(col)
            )
            if row == col:
                if total <= 0:
                    raise ValueError(
                        "Matriz de rigidez não é positiva definida; "
                        "confira as tensões e o padrão de montagem."
                    )
                factor[row][col] = math.sqrt(total)
            else:
                factor[row][col] = total / factor[col][col]
    return factor


def _cholesky_solve(
    factor: list[list[float]], rhs: Sequence[float]
) -> list[float]:
    size = len(rhs)
    forward = [0.0] * size
    for row in range(size):
        total = rhs[row] - sum(
            factor[row][col] * forward[col] for col in range(row)
        )
        forward[row] = total / factor[row][row]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = forward[row] - sum(
            factor[col][row] * solution[col]
            for col in range(row + 1, size)
        )
        solution[row] = total / factor[row][row]
    return solution


def _solve_linear_system(
    matrix: list[list[float]], rhs: Sequence[float]
) -> list[float]:
    """Resolve ``A x = b`` por Cholesky, com fallback para Gauss."""

    try:
        return _cholesky_solve(_cholesky_factor(matrix), rhs)
    except ValueError:
        return _gaussian_solve(matrix, rhs)


def _gaussian_solve(
    matrix: list[list[float]], rhs: Sequence[float]
) -> list[float]:
    size = len(rhs)
    augmented = [
        list(matrix[row]) + [float(rhs[row])] for row in range(size)
    ]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-14:
            raise ValueError(
                "Sistema de equilíbrio singular; confira as tensões dos raios."
            )
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for row in range(col + 1, size):
            factor = augmented[row][col] / pivot_value
            if factor == 0.0:
                continue
            for index in range(col, size + 1):
                augmented[row][index] -= factor * augmented[col][index]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = augmented[row][size] - sum(
            augmented[row][col] * solution[col]
            for col in range(row + 1, size)
        )
        solution[row] = total / augmented[row][row]
    return solution
