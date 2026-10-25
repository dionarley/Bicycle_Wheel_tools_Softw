"""Ficha de montagem: resumo, JSON, Markdown e HTML para PDF."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import datetime
from html import escape
from pathlib import Path

from .assembly import AssemblyPlan, build_assembly_plan
from .components import ComponentSet
from .diagnostics import DiagnosticReport, diagnose_build_sheet
from .models import Side, SpokeLengthResult, WheelSpec
from .spoke_length import calculate_spoke_lengths
from .tension import (
    lateral_tension_ratio,
    linear_density_kg_per_m,
    rim_compression_from_sides,
    spoke_elongation_mm,
    target_tensions,
    tone_frequency_hz,
)


def _fmt(value: float, decimals: int = 0) -> str:
    """Formata número no padrão brasileiro."""

    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _tighter_side(ratio_left_over_right: float) -> Side:
    return Side.RIGHT if ratio_left_over_right <= 1.0 else Side.LEFT


def _side_label(side: Side) -> str:
    return "esquerdo" if side is Side.LEFT else "direito"


@dataclass(frozen=True)
class BuildSheet:
    """Todos os dados de uma montagem calculada."""

    spec: WheelSpec
    result: SpokeLengthResult
    target_tension_n: float
    spoke_diameter_mm: float
    tension_ratio: float
    tensions_n: dict[Side, float]
    compression_n: float
    elongation_left_mm: float
    elongation_right_mm: float
    tone_left_hz: float
    tone_right_hz: float
    created_at: datetime
    notes: str = ""
    components: ComponentSet | None = None
    assembly_plan: AssemblyPlan | None = None
    diagnostics: DiagnosticReport | None = None

    @property
    def tighter_side(self) -> Side:
        return _tighter_side(self.tension_ratio)

    @property
    def centering_action(self) -> str:
        """Texto da correção de centralização."""

        offset = self.spec.rim_offset_mm
        if self.spec.is_centered:
            return "centralizada (desvio ≤ 0,5 mm)"
        direction = "esquerda" if offset > 0 else "direita"
        return (
            f"mover o aro {_fmt(abs(offset), 1)} mm para a {direction}"
        )

    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.spec.is_centered:
            warnings.append(
                "Roda descentralizada em "
                f"{_fmt(abs(self.spec.rim_offset_mm), 1)} mm; "
                f"{self.centering_action}."
            )
        if math.isclose(self.result.angle_deg, 90.0, abs_tol=1e-6):
            warnings.append(
                "Ângulo de cruzamento no limite de 90°; confira a folga do "
                "raio no flange."
            )
        if (
            self.spec.locknut_spacing_mm is not None
            and self.spec.locknut_spacing_mm <= self.spec.flange_spacing_mm
        ):
            warnings.append(
                "A distância entre locknuts é menor ou igual à distância entre "
                "flanges; confira as medidas do cubo."
            )
        if self.components is not None:
            warnings.extend(
                self.components.compatibility_warnings(
                    self.spec, self.spoke_diameter_mm
                )
            )
        if self.assembly_plan is None:
            if self.spec.spoke_count % 4 != 0:
                warnings.append(
                    "Assistente de montagem indisponível: ele exige número de "
                    "raios múltiplo de 4."
                )
            else:
                warnings.append(
                    "Assistente de montagem indisponível para esta montagem."
                )
        else:
            warnings.extend(self.assembly_plan.warnings)
        return list(dict.fromkeys(warnings))

    def to_summary_text(self) -> str:
        """Resumo curto para o painel da interface."""

        lines = [
            "=== COMPRIMENTO DOS RAIOS ===",
            f"Ângulo de cruzamento (T): {_fmt(self.result.angle_deg, 1)}°",
            (
                f"Esquerdo: {_fmt(self.result.left_mm, 2)} mm "
                f"→ comprar {self.result.left_purchase_mm} mm"
            ),
            (
                f"Direito:  {_fmt(self.result.right_mm, 2)} mm "
                f"→ comprar {self.result.right_purchase_mm} mm"
            ),
            (
                "Diferença L-R: "
                f"{_fmt(abs(self.result.left_mm - self.result.right_mm), 2)} mm"
            ),
            "",
            "=== TENSÃO (estimativa) ===",
            (
                f"Razão T_esq / T_dir: {_fmt(self.tension_ratio, 3)} "
                f"(lado {_side_label(self.tighter_side)} mais tenso)"
            ),
            (
                f"Alvo esquerdo: {_fmt(self.tensions_n[Side.LEFT], 0)} N | "
                f"direito: {_fmt(self.tensions_n[Side.RIGHT], 0)} N "
                f"(lado mais tenso: {_side_label(self.tighter_side)})"
            ),
            f"Compressão no aro: {_fmt(self.compression_n, 0)} N",
            (
                f"Alongamento: esq. {_fmt(self.elongation_left_mm, 2)} mm | "
                f"dir. {_fmt(self.elongation_right_mm, 2)} mm"
            ),
            (
                f"Tom aproximado: esq. {_fmt(self.tone_left_hz, 0)} Hz | "
                f"dir. {_fmt(self.tone_right_hz, 0)} Hz"
            ),
            "",
            "=== CENTRALIZAÇÃO ===",
            (
                f"Dish: {_fmt(self.spec.rim_offset_mm, 1)} mm — "
                f"{self.centering_action}"
            ),
            (
                f"Flange esq.: {_fmt(self.spec.effective_left_offset_mm, 1)} mm "
                f"do plano do aro | dir.: "
                f"{_fmt(self.spec.effective_right_offset_mm, 1)} mm"
            ),
        ]
        if self.spec.locknut_spacing_mm is not None:
            lines.append(
                f"Distância entre locknuts: "
                f"{_fmt(self.spec.locknut_spacing_mm, 1)} mm"
            )
        if self.components is not None:
            lines.extend(["", "=== COMPONENTES ==="])
            lines.extend(self.components.summary_lines())
        if self.assembly_plan is not None:
            lines.extend(
                [
                    "",
                    "=== ASSISTENTE DE MONTAGEM ===",
                    (
                        f"4 conjuntos de {self.assembly_plan.group_size} raios; "
                        f"T = {_fmt(self.assembly_plan.angle_deg, 1)}°."
                    ),
                    "Veja a aba 'Assistente de montagem' ou a ficha completa.",
                ]
            )
        if self.diagnostics is not None:
            lines.extend(["", self.diagnostics.summary_text()])
        warnings = self.warnings()
        if warnings:
            lines.extend(["", "Avisos:"])
            lines.extend(f"• {warning}" for warning in warnings)
        lines.extend(
            [
                "",
                "Notas:",
                "• Comprimento arredondado para baixo (raio estica, aro encolhe).",
                "• Tom é aproximado; use tensiômetro para tensão absoluta.",
                "• Offsets medidos do centro do cubo ao flange.",
            ]
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Estrutura serializável em JSON."""

        spec = self.spec
        locknuts = spec.locknut_positions_mm()
        flange_left, flange_right = spec.flange_positions_mm()
        return {
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "spec": {
                "erd_mm": spec.erd_mm,
                "left_flange_diameter_mm": spec.left_flange_diameter_mm,
                "right_flange_diameter_mm": spec.right_flange_diameter_mm,
                "left_flange_offset_mm": spec.left_flange_offset_mm,
                "right_flange_offset_mm": spec.right_flange_offset_mm,
                "hole_diameter_mm": spec.hole_diameter_mm,
                "spoke_count": spec.spoke_count,
                "crossings": spec.crossings,
                "rim_offset_mm": spec.rim_offset_mm,
                "locknut_spacing_mm": spec.locknut_spacing_mm,
                "effective_left_offset_mm": spec.effective_left_offset_mm,
                "effective_right_offset_mm": spec.effective_right_offset_mm,
                "flange_spacing_mm": spec.flange_spacing_mm,
                "hub_center_mm": spec.hub_center_mm,
                "is_centered": spec.is_centered,
            },
            "result": {
                "angle_deg": self.result.angle_deg,
                "left_mm": self.result.left_mm,
                "right_mm": self.result.right_mm,
                "left_purchase_mm": self.result.left_purchase_mm,
                "right_purchase_mm": self.result.right_purchase_mm,
            },
            "tension": {
                "target_n": self.target_tension_n,
                "ratio_left_over_right": self.tension_ratio,
                "tighter_side": self.tighter_side.value,
                "left_n": self.tensions_n[Side.LEFT],
                "right_n": self.tensions_n[Side.RIGHT],
                "rim_compression_n": self.compression_n,
            },
            "spoke": {
                "diameter_mm": self.spoke_diameter_mm,
                "elongation_left_mm": self.elongation_left_mm,
                "elongation_right_mm": self.elongation_right_mm,
                "tone_left_hz": self.tone_left_hz,
                "tone_right_hz": self.tone_right_hz,
            },
            "centering": {
                "is_centered": spec.is_centered,
                "rim_offset_mm": spec.rim_offset_mm,
                "correction_mm": spec.centering_correction_mm,
                "action": self.centering_action,
                "hub_center_mm": spec.hub_center_mm,
                "flange_left_mm": flange_left,
                "flange_right_mm": flange_right,
                "locknut_left_mm": locknuts[0] if locknuts else None,
                "locknut_right_mm": locknuts[1] if locknuts else None,
            },
            "warnings": self.warnings(),
            "notes": self.notes,
            "components": (
                self.components.to_dict() if self.components is not None else None
            ),
            "assembly": (
                self.assembly_plan.to_dict()
                if self.assembly_plan is not None
                else None
            ),
            "diagnostics": (
                self.diagnostics.to_dict()
                if self.diagnostics is not None
                else None
            ),
        }

    def to_markdown(self) -> str:
        """Ficha em Markdown, para leitura e versionamento."""

        spec = self.spec
        lines = [
            "# Ficha de montagem — Wheel Lab",
            "",
            f"Gerada em {self.created_at:%d/%m/%Y %H:%M}",
            "",
            "## Roda",
            "",
            f"- **Aro (ERD):** {_fmt(spec.erd_mm, 1)} mm",
            (
                f"- **Cubo:** PCD esq./dir. {_fmt(spec.left_flange_diameter_mm, 1)} / "
                f"{_fmt(spec.right_flange_diameter_mm, 1)} mm; offsets esq./dir. "
                f"{_fmt(spec.left_flange_offset_mm, 1)} / "
                f"{_fmt(spec.right_flange_offset_mm, 1)} mm"
            ),
            (
                f"- **Locknuts (OLD):** "
                f"{_fmt(spec.locknut_spacing_mm, 1) + ' mm' if spec.locknut_spacing_mm is not None else 'não informado'}"
            ),
            f"- **Dish:** {_fmt(spec.rim_offset_mm, 1)} mm — {self.centering_action}",
            (
                f"- **Raios:** {spec.spoke_count}; **cruzamentos:** "
                f"{spec.crossings} (T = {_fmt(self.result.angle_deg, 1)}°)"
            ),
            f"- **Diâmetro do raio:** {_fmt(self.spoke_diameter_mm, 2)} mm",
            "",
            "## Comprimentos",
            "",
            "| Lado | Comprimento | Comprar |",
            "| --- | ---: | ---: |",
            (
                f"| Esquerdo | {_fmt(self.result.left_mm, 2)} mm | "
                f"{self.result.left_purchase_mm} mm |"
            ),
            (
                f"| Direito | {_fmt(self.result.right_mm, 2)} mm | "
                f"{self.result.right_purchase_mm} mm |"
            ),
            "",
            "## Tensão",
            "",
            (
                f"- **Razão T_esq / T_dir:** {_fmt(self.tension_ratio, 3)} "
                f"(lado {_side_label(self.tighter_side)} mais tenso)"
            ),
            (
                f"- **Alvo:** esquerdo {_fmt(self.tensions_n[Side.LEFT], 0)} N; "
                f"direito {_fmt(self.tensions_n[Side.RIGHT], 0)} N"
            ),
            f"- **Compressão no aro:** {_fmt(self.compression_n, 0)} N",
            (
                f"- **Alongamento:** esquerdo "
                f"{_fmt(self.elongation_left_mm, 2)} mm; direito "
                f"{_fmt(self.elongation_right_mm, 2)} mm"
            ),
            (
                f"- **Tom aproximado:** esquerdo {_fmt(self.tone_left_hz, 0)} Hz; "
                f"direito {_fmt(self.tone_right_hz, 0)} Hz"
            ),
            "",
            "## Centralização",
            "",
            f"- **Deslocamento do aro:** {_fmt(spec.rim_offset_mm, 1)} mm",
            f"- **Correção:** {self.centering_action}",
            (
                f"- **Flanges (do plano do aro):** esquerdo "
                f"{_fmt(spec.effective_left_offset_mm, 1)} mm; direito "
                f"{_fmt(spec.effective_right_offset_mm, 1)} mm"
            ),
            "",
            "## Avisos",
            "",
        ]
        warnings = self.warnings()
        if warnings:
            lines.extend(f"- {warning}" for warning in warnings)
        else:
            lines.append("- Nenhum aviso.")
        lines.extend(
            [
                "",
                "## Notas",
                "",
                self.notes or "—",
                "",
                "---",
                "",
                "Referência: Jobst Brandt, *The Bicycle Wheel*, 3ª ed.",
                "",
            ]
        )
        if self.components is not None:
            insert_at = lines.index("## Comprimentos")
            component_lines = [
                "## Componentes",
                "",
                *[f"- {line}" for line in self.components.summary_lines()],
                "",
            ]
            lines[insert_at:insert_at] = component_lines
        if self.assembly_plan is not None:
            insert_at = lines.index("## Avisos")
            assembly_lines = (
                self.assembly_plan.to_markdown(
                    include_warnings=False
                ).splitlines()
                + [""]
            )
            lines[insert_at:insert_at] = assembly_lines
        if self.diagnostics is not None:
            insert_at = lines.index("## Avisos")
            diagnostic_lines = (
                self.diagnostics.to_markdown().splitlines() + [""]
            )
            lines[insert_at:insert_at] = diagnostic_lines
        return "\n".join(lines)

    def to_html(self) -> str:
        """Ficha em HTML, usada para gerar PDF."""

        spec = self.spec
        warnings = self.warnings()
        warning_html = (
            "<ul>"
            + "".join(f"<li>{escape(w)}</li>" for w in warnings)
            + "</ul>"
            if warnings
            else "<p class='ok'>Nenhum aviso.</p>"
        )
        notes = escape(self.notes) if self.notes else "—"
        components_html = ""
        if self.components is not None:
            component_items = "".join(
                f"<li>{escape(line)}</li>"
                for line in self.components.summary_lines()
            )
            components_html = f"<h2>Componentes</h2><ul>{component_items}</ul>"
        assembly_html = (
            self.assembly_plan.to_html(include_warnings=False)
            if self.assembly_plan is not None
            else ""
        )
        diagnostics_html = (
            self.diagnostics.to_html()
            if self.diagnostics is not None
            else ""
        )
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 10pt; color: #222; }}
  h1 {{ font-size: 18pt; margin-bottom: 2pt; }}
  h2 {{ font-size: 13pt; border-bottom: 1px solid #999; padding-bottom: 2pt; }}
  table {{ border-collapse: collapse; width: 100%; margin: 6pt 0; }}
  th, td {{ border: 1px solid #999; padding: 4pt; text-align: left; }}
  th {{ background: #eee; }}
  .ok {{ color: #1a7f37; }}
  .warn {{ color: #b42318; }}
  .critical {{ color: #b42318; font-weight: bold; }}
  .warning {{ color: #b54708; }}
  .info {{ color: #175cd3; }}
  .muted {{ color: #666; }}
</style>
</head>
<body>
<h1>Ficha de montagem — Wheel Lab</h1>
<p class="muted">Gerada em {self.created_at:%d/%m/%Y %H:%M}</p>

<h2>Roda</h2>
<table>
<tr><th>Aro (ERD)</th><td>{_fmt(spec.erd_mm, 1)} mm</td></tr>
<tr><th>Cubo (PCD esq./dir.)</th><td>{_fmt(spec.left_flange_diameter_mm, 1)} / {_fmt(spec.right_flange_diameter_mm, 1)} mm</td></tr>
<tr><th>Offsets esq./dir. ao centro</th><td>{_fmt(spec.left_flange_offset_mm, 1)} / {_fmt(spec.right_flange_offset_mm, 1)} mm</td></tr>
<tr><th>Locknuts (OLD)</th><td>{_fmt(spec.locknut_spacing_mm, 1) + ' mm' if spec.locknut_spacing_mm is not None else 'não informado'}</td></tr>
<tr><th>Dish</th><td>{_fmt(spec.rim_offset_mm, 1)} mm — {escape(self.centering_action)}</td></tr>
<tr><th>Raios / cruzamentos</th><td>{spec.spoke_count} / {spec.crossings} (T = {_fmt(self.result.angle_deg, 1)}°)</td></tr>
<tr><th>Diâmetro do raio</th><td>{_fmt(self.spoke_diameter_mm, 2)} mm</td></tr>
</table>

{components_html}

<h2>Comprimentos</h2>
<table>
<tr><th>Lado</th><th>Comprimento</th><th>Comprar</th></tr>
<tr><td>Esquerdo</td><td>{_fmt(self.result.left_mm, 2)} mm</td><td>{self.result.left_purchase_mm} mm</td></tr>
<tr><td>Direito</td><td>{_fmt(self.result.right_mm, 2)} mm</td><td>{self.result.right_purchase_mm} mm</td></tr>
</table>

<h2>Tensão</h2>
<table>
<tr><th>Razão T_esq / T_dir</th><td>{_fmt(self.tension_ratio, 3)} (lado {_side_label(self.tighter_side)} mais tenso)</td></tr>
<tr><th>Alvo esquerdo / direito</th><td>{_fmt(self.tensions_n[Side.LEFT], 0)} / {_fmt(self.tensions_n[Side.RIGHT], 0)} N</td></tr>
<tr><th>Compressão no aro</th><td>{_fmt(self.compression_n, 0)} N</td></tr>
<tr><th>Alongamento esq./dir.</th><td>{_fmt(self.elongation_left_mm, 2)} / {_fmt(self.elongation_right_mm, 2)} mm</td></tr>
<tr><th>Tom aprox. esq./dir.</th><td>{_fmt(self.tone_left_hz, 0)} / {_fmt(self.tone_right_hz, 0)} Hz</td></tr>
</table>

<h2>Centralização</h2>
<table>
<tr><th>Deslocamento do aro</th><td>{_fmt(spec.rim_offset_mm, 1)} mm</td></tr>
<tr><th>Correção</th><td>{escape(self.centering_action)}</td></tr>
<tr><th>Flanges (do plano do aro)</th><td>{_fmt(spec.effective_left_offset_mm, 1)} / {_fmt(spec.effective_right_offset_mm, 1)} mm</td></tr>
</table>

{assembly_html}

{diagnostics_html}

<h2>Avisos</h2>
{warning_html}

<h2>Notas</h2>
<p>{notes}</p>
<p class="muted">Referência: Jobst Brandt, The Bicycle Wheel, 3ª ed.</p>
</body>
</html>
"""

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_markdown(self, path: str | Path) -> None:
        Path(path).write_text(self.to_markdown(), encoding="utf-8")


def create_build_sheet(
    spec: WheelSpec,
    target_tension_n: float,
    spoke_diameter_mm: float,
    notes: str = "",
    created_at: datetime | None = None,
    components: ComponentSet | None = None,
) -> BuildSheet:
    """Calcula a montagem completa e devolve uma ficha pronta."""

    if not math.isfinite(target_tension_n) or target_tension_n <= 0:
        raise ValueError("A tensão alvo deve ser um número positivo.")
    if not math.isfinite(spoke_diameter_mm) or spoke_diameter_mm <= 0:
        raise ValueError("O diâmetro do raio deve ser um número positivo.")

    spec.validate()
    if components is not None:
        components.validate()
    result = calculate_spoke_lengths(spec)
    ratio = lateral_tension_ratio(
        spec.effective_left_offset_mm,
        spec.effective_right_offset_mm,
        result.left_mm,
        result.right_mm,
    )
    tighter = _tighter_side(ratio)
    tensions = target_tensions(target_tension_n, ratio, tighter)
    compression = rim_compression_from_sides(
        tensions[Side.LEFT],
        tensions[Side.RIGHT],
        spec.spoke_count,
    )
    mu = linear_density_kg_per_m(spoke_diameter_mm)

    sheet = BuildSheet(
        spec=spec,
        result=result,
        target_tension_n=target_tension_n,
        spoke_diameter_mm=spoke_diameter_mm,
        tension_ratio=ratio,
        tensions_n=tensions,
        compression_n=compression,
        elongation_left_mm=spoke_elongation_mm(
            tensions[Side.LEFT], result.left_mm, spoke_diameter_mm
        ),
        elongation_right_mm=spoke_elongation_mm(
            tensions[Side.RIGHT], result.right_mm, spoke_diameter_mm
        ),
        tone_left_hz=tone_frequency_hz(
            tensions[Side.LEFT], result.left_mm, mu
        ),
        tone_right_hz=tone_frequency_hz(
            tensions[Side.RIGHT], result.right_mm, mu
        ),
        created_at=created_at or datetime.now(),
        notes=notes,
        components=components,
        assembly_plan=_safe_assembly_plan(spec),
    )
    return replace(sheet, diagnostics=diagnose_build_sheet(sheet))


def _safe_assembly_plan(spec: WheelSpec) -> AssemblyPlan | None:
    try:
        return build_assembly_plan(spec)
    except ValueError:
        return None
