"""Diagnóstico avançado da montagem (Fase 4).

O diagnóstico reúne verificações geométricas, de tensão, de alinhamento, de
componentes, de tom e de rigidez em achados classificados. Ele não substitui a
inspeção visual nem o tensiômetro; serve para priorizar o que conferir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from html import escape
from typing import TYPE_CHECKING

from .audio import ToneReading
from .models import Side
from .stiffness import WheelStiffness
from .truing import TruingState

if TYPE_CHECKING:
    from .build_sheet import BuildSheet


class Severity(str, Enum):
    """Gravidade de um achado de diagnóstico."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def label_pt(self) -> str:
        return {
            Severity.INFO: "info",
            Severity.WARNING: "aviso",
            Severity.CRITICAL: "crítico",
        }[self]

    @property
    def rank(self) -> int:
        return {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.CRITICAL: 2,
        }[self]


@dataclass(frozen=True)
class DiagnosticFinding:
    """Um achado individual do diagnóstico."""

    code: str
    severity: Severity
    category: str
    message: str
    recommendation: str
    value: float | None = None
    unit: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "recommendation": self.recommendation,
            "value": self.value,
            "unit": self.unit,
        }

    def to_text(self) -> str:
        lines = [
            f"[{self.severity.label_pt.upper()}] {self.category}: {self.message}"
        ]
        if self.value is not None:
            lines.append(f"  Valor: {_fmt(self.value, 2)} {self.unit}".rstrip())
        lines.append(f"  Ação: {self.recommendation}")
        return "\n".join(lines)


@dataclass(frozen=True)
class DiagnosticReport:
    """Conjunto de achados e pontuação da montagem."""

    findings: tuple[DiagnosticFinding, ...]

    @property
    def ordered_findings(self) -> tuple[DiagnosticFinding, ...]:
        return tuple(
            sorted(
                self.findings,
                key=lambda finding: (-finding.severity.rank, finding.code),
            )
        )

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            Severity.CRITICAL.value: 0,
            Severity.WARNING.value: 0,
            Severity.INFO.value: 0,
        }
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts

    @property
    def overall(self) -> Severity:
        if any(
            finding.severity is Severity.CRITICAL
            for finding in self.findings
        ):
            return Severity.CRITICAL
        if any(
            finding.severity is Severity.WARNING
            for finding in self.findings
        ):
            return Severity.WARNING
        return Severity.INFO

    @property
    def score(self) -> int:
        counts = self.counts
        value = (
            100
            - 30 * counts[Severity.CRITICAL.value]
            - 10 * counts[Severity.WARNING.value]
        )
        return max(0, min(100, value))

    def summary_text(self) -> str:
        counts = self.counts
        if not self.findings:
            return "Diagnóstico: nenhum achado relevante (100/100)."
        parts: list[str] = []
        critical = counts[Severity.CRITICAL.value]
        warning = counts[Severity.WARNING.value]
        info = counts[Severity.INFO.value]
        if critical:
            parts.append(f"{critical} crítico(s)")
        if warning:
            parts.append(f"{warning} aviso(s)")
        if info:
            parts.append(f"{info} informação(ões)")
        return f"Diagnóstico: {self.score}/100 — " + ", ".join(parts) + "."

    def to_text(self) -> str:
        lines = [
            "=== DIAGNÓSTICO DA RODA ===",
            self.summary_text(),
        ]
        if not self.findings:
            lines.append("Nenhum problema detectado pelas verificações automáticas.")
            return "\n".join(lines)
        for finding in self.ordered_findings:
            lines.extend(["", finding.to_text()])
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            "## Diagnóstico da roda",
            "",
            f"**{self.summary_text()}**",
            "",
        ]
        if not self.findings:
            lines.append("Nenhum problema detectado pelas verificações automáticas.")
            return "\n".join(lines)
        lines.extend(
            [
                "| Severidade | Categoria | Achado | Ação |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in self.ordered_findings:
            lines.append(
                "| "
                f"{finding.severity.label_pt} | "
                f"{_md_cell(finding.category)} | "
                f"{_md_cell(finding.message)} | "
                f"{_md_cell(finding.recommendation)} |"
            )
        return "\n".join(lines)

    def to_html(self) -> str:
        rows = "".join(
            "<tr>"
            f"<td class='{finding.severity.value}'>"
            f"{escape(finding.severity.label_pt)}</td>"
            f"<td>{escape(finding.category)}</td>"
            f"<td>{escape(finding.message)}</td>"
            f"<td>{escape(finding.recommendation)}</td>"
            "</tr>"
            for finding in self.ordered_findings
        )
        if rows:
            table = (
                "<table><tr><th>Severidade</th><th>Categoria</th>"
                "<th>Achado</th><th>Ação</th></tr>"
                f"{rows}</table>"
            )
        else:
            table = (
                "<p class='ok'>Nenhum problema detectado pelas verificações "
                "automáticas.</p>"
            )
        return (
            "<h2>Diagnóstico da roda</h2>"
            f"<p><strong>{escape(self.summary_text())}</strong></p>"
            f"{table}"
        )

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "overall": self.overall.value,
            "counts": self.counts,
            "summary": self.summary_text(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def diagnose_build_sheet(
    sheet: BuildSheet,
    truing_state: TruingState | None = None,
    tone_readings: ToneReading | Sequence[ToneReading] | None = None,
    stiffness: WheelStiffness | None = None,
) -> DiagnosticReport:
    """Executa as verificações disponíveis e devolve um relatório."""

    findings: list[DiagnosticFinding] = []

    def add(
        code: str,
        severity: Severity,
        category: str,
        message: str,
        recommendation: str,
        value: float | None = None,
        unit: str = "",
    ) -> None:
        findings.append(
            DiagnosticFinding(
                code=code,
                severity=severity,
                category=category,
                message=message,
                recommendation=recommendation,
                value=value,
                unit=unit,
            )
        )

    spec = sheet.spec
    offset = abs(spec.rim_offset_mm)
    if offset >= 2.0:
        add(
            "dish",
            Severity.CRITICAL,
            "Centralização",
            f"Roda descentralizada em {_fmt(offset, 1)} mm.",
            sheet.centering_action,
            value=spec.rim_offset_mm,
            unit="mm",
        )
    elif not spec.is_centered:
        add(
            "dish",
            Severity.WARNING,
            "Centralização",
            f"Desvio de centralização de {_fmt(offset, 1)} mm.",
            sheet.centering_action,
            value=spec.rim_offset_mm,
            unit="mm",
        )

    if math.isclose(sheet.result.angle_deg, 90.0, abs_tol=1e-6):
        add(
            "angle_90",
            Severity.WARNING,
            "Geometria",
            "Ângulo de cruzamento no limite de 90°.",
            "Confira a folga do raio no flange e reduza os cruzamentos se "
            "houver contato.",
            value=sheet.result.angle_deg,
            unit="°",
        )

    if spec.locknut_spacing_mm is None:
        add(
            "locknut_missing",
            Severity.INFO,
            "Cubo",
            "Distância entre locknuts (OLD) não informada.",
            "Informe a OLD para validar o dish e a posição do aro.",
        )
    elif spec.locknut_spacing_mm <= spec.flange_spacing_mm:
        add(
            "locknut_spacing",
            Severity.CRITICAL,
            "Cubo",
            "A distância entre locknuts é menor ou igual à distância entre "
            "flanges.",
            "Confira as medidas do cubo; os valores atuais são incompatíveis.",
            value=spec.locknut_spacing_mm,
            unit="mm",
        )

    if sheet.components is not None:
        for warning in sheet.components.compatibility_warnings(
            spec, sheet.spoke_diameter_mm
        ):
            add(
                "component_mismatch",
                Severity.WARNING,
                "Componentes",
                warning,
                "Revise o conjunto de componentes antes de comprar ou montar.",
            )

    if sheet.assembly_plan is None:
        if spec.spoke_count % 4 != 0:
            message = (
                "Assistente de montagem indisponível: o número de raios não é "
                "múltiplo de 4."
            )
        else:
            message = "Assistente de montagem indisponível para esta montagem."
        add(
            "assembly_missing",
            Severity.WARNING,
            "Montagem",
            message,
            "Use um padrão de montagem compatível ou confira os dados da roda.",
        )
    elif spec.crossings == 0:
        add(
            "radial_lacing",
            Severity.INFO,
            "Montagem",
            "Montagem radial: não há cruzamentos entre raios.",
            "Confira a orientação dos raios e a transmissão de torque do cubo.",
        )

    ratio = sheet.tension_ratio
    if ratio <= 0.0:
        add(
            "tension_ratio_invalid",
            Severity.CRITICAL,
            "Tensão",
            "A razão de tensão entre os lados é inválida.",
            "Confira offsets, comprimentos e dados do cubo.",
            value=ratio,
        )
    elif ratio < 0.35 or ratio > 2.0:
        add(
            "tension_ratio",
            Severity.WARNING,
            "Tensão",
            f"Razão de tensão esquerda/direita extrema: {_fmt(ratio, 3)}.",
            "Confira os offsets do cubo e a centralização; a diferença entre "
            "lados pode indicar medida errada.",
            value=ratio,
        )

    for side in (Side.LEFT, Side.RIGHT):
        tension = sheet.tensions_n.get(side)
        if tension is None:
            continue
        if tension <= 0.0:
            add(
                f"tension_{side.value}_invalid",
                Severity.CRITICAL,
                "Tensão",
                f"Tensão alvo do lado {side.label_pt} não é positiva.",
                "Revise a tensão alvo e a razão entre os lados.",
                value=tension,
                unit="N",
            )

    if truing_state is not None and truing_state.spec != spec:
        add(
            "truing_spec_mismatch",
            Severity.CRITICAL,
            "Modelo físico",
            "O estado de alinhamento não corresponde às medidas atuais da roda.",
            "Recalcule os raios e o estado físico antes de usar o diagnóstico.",
        )
        truing_state = None

    if truing_state is not None:
        lateral = truing_state.lateral_runout_mm
        radial = truing_state.radial_runout_mm
        if lateral > 1.0:
            add(
                "runout_lateral",
                Severity.CRITICAL,
                "Alinhamento",
                f"Desvio lateral de {_fmt(lateral, 2)} mm.",
                "Corrija o empeno lateral antes de finalizar a tensão.",
                value=lateral,
                unit="mm",
            )
        elif lateral > 0.5:
            add(
                "runout_lateral",
                Severity.WARNING,
                "Alinhamento",
                f"Desvio lateral de {_fmt(lateral, 2)} mm.",
                "Ajuste o empeno lateral com passos pequenos e recalcule.",
                value=lateral,
                unit="mm",
            )
        if radial > 1.0:
            add(
                "runout_radial",
                Severity.CRITICAL,
                "Alinhamento",
                f"Desvio radial de {_fmt(radial, 2)} mm.",
                "Corrija a ovalização antes de finalizar a tensão.",
                value=radial,
                unit="mm",
            )
        elif radial > 0.5:
            add(
                "runout_radial",
                Severity.WARNING,
                "Alinhamento",
                f"Desvio radial de {_fmt(radial, 2)} mm.",
                "Ajuste a ovalização com passos pequenos e recalcule.",
                value=radial,
                unit="mm",
            )
        if truing_state.slack_indices:
            indices = ", ".join(
                str(index + 1) for index in truing_state.slack_indices
            )
            add(
                "slack_spokes",
                Severity.CRITICAL,
                "Tensão",
                f"Raios frouxos: {indices}.",
                "Tencione ou substitua os raios frouxos antes de rodar.",
            )
        minimum = truing_state.min_tension_n
        maximum = truing_state.max_tension_n
        if minimum < 0.25 * sheet.target_tension_n:
            add(
                "tension_low",
                Severity.WARNING,
                "Tensão",
                f"Tensão mínima de {_fmt(minimum, 0)} N.",
                "Confira a tensão dos raios mais frouxos e o padrão de "
                "montagem.",
                value=minimum,
                unit="N",
            )
        if maximum > 1.5 * sheet.target_tension_n:
            add(
                "tension_high",
                Severity.WARNING,
                "Tensão",
                f"Tensão máxima de {_fmt(maximum, 0)} N.",
                "Confira o limite do aro e redistribua a tensão.",
                value=maximum,
                unit="N",
            )

    for reading in _normalize_readings(tone_readings):
        if reading.confidence < 0.5:
            add(
                "tone_confidence",
                Severity.WARNING,
                "Tom",
                "Leitura de tom com confiança baixa.",
                "Aproxime o microfone, reduza ruído e repita a gravação.",
                value=reading.confidence,
            )
        if reading.tension_n is not None:
            expected = reading.expected_tension_n
            if expected is None and reading.side is not None:
                expected = sheet.tensions_n.get(reading.side)
            if expected is not None and expected > 0.0:
                deviation = abs(reading.tension_n - expected) / expected
                severity = (
                    Severity.CRITICAL
                    if deviation > 0.35
                    else Severity.WARNING
                    if deviation > 0.20
                    else Severity.INFO
                )
                side_text = (
                    f" do lado {reading.side.label_pt}"
                    if reading.side is not None
                    else ""
                )
                add(
                    "tone_tension",
                    severity,
                    "Tom",
                    (
                        f"Tom indica {_fmt(reading.tension_n, 0)} N"
                        f"{side_text}; esperado {_fmt(expected, 0)} N "
                        f"(desvio {_fmt(deviation * 100.0, 0)}%)."
                    ),
                    "Confira o comprimento do raio, a densidade e a leitura "
                    "com tensiômetro.",
                    value=reading.tension_n,
                    unit="N",
                )
        for warning in reading.warnings:
            add(
                "tone_warning",
                Severity.INFO,
                "Tom",
                warning,
                "Repita a leitura se o resultado não for consistente.",
            )

    if stiffness is not None:
        add(
            "stiffness_metrics",
            Severity.INFO,
            "Rigidez",
            (
                f"Lateral média {_fmt(stiffness.lateral_n_per_mm, 1)} N/mm; "
                f"radial média {_fmt(stiffness.radial_n_per_mm, 1)} N/mm; "
                f"torsional {_fmt(stiffness.torsional_nm_per_deg, 2)} N·m/°."
            ),
            "Use como referência comparativa para o mesmo aro e cubo.",
        )
        for warning in stiffness.warnings:
            severity = (
                Severity.INFO
                if "Montagem radial" in warning
                else Severity.WARNING
            )
            add(
                "stiffness_warning",
                severity,
                "Rigidez",
                warning,
                "Revise tensões, padrão de montagem e propriedades do aro.",
            )

    return DiagnosticReport(findings=tuple(findings))


def _normalize_readings(
    tone_readings: ToneReading | Sequence[ToneReading] | None,
) -> tuple[ToneReading, ...]:
    if tone_readings is None:
        return ()
    if isinstance(tone_readings, ToneReading):
        return (tone_readings,)
    return tuple(tone_readings)


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _fmt(value: float, decimals: int = 0) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


__all__ = [
    "DiagnosticFinding",
    "DiagnosticReport",
    "Severity",
    "diagnose_build_sheet",
]
