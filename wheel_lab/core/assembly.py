"""Assistente dos quatro conjuntos de montagem.

O padrão usado pelo Wheel Lab divide os raios em quatro conjuntos:

* esquerda *leading*;
* direita *leading*;
* esquerda *trailing*;
* direita *trailing*.

Para uma roda de ``N`` raios (``N`` múltiplo de 4), cada conjunto tem ``N/4``
raios. O assistente numera os furos do aro e dos flanges de forma relativa,
mostra os pares aro → cubo e gera instruções para a bancada. A numeração é
esquemática: comece no primeiro furo de raio ao lado da válvula e mantenha o
mesmo sentido em toda a montagem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape

from .geometry import spoke_angle_deg
from .lacing import build_spoke_table
from .models import Side, Spoke, SpokeDirection, WheelSpec

_GROUP_ORDER = (
    (Side.LEFT, SpokeDirection.LEADING),
    (Side.RIGHT, SpokeDirection.LEADING),
    (Side.LEFT, SpokeDirection.TRAILING),
    (Side.RIGHT, SpokeDirection.TRAILING),
)

_NOTES = (
    "A numeração dos furos é relativa ao primeiro furo de raio ao lado da "
    "válvula; mantenha o mesmo sentido em toda a montagem.",
    "O assistente é esquemático e não substitui as instruções do fabricante "
    "do aro, do cubo ou do raio.",
    "A direção de inserção dos raios (cabeça dentro ou fora do flange) "
    "depende do cubo; mantenha o padrão escolhido.",
)


def _fmt(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _side_title(side: Side) -> str:
    return "Esquerda" if side is Side.LEFT else "Direita"


def _format_number_list(values, max_items: int = 6) -> str:
    items = [str(int(value)) for value in values]
    if not items:
        return "—"
    if len(items) <= max_items:
        return ", ".join(items)
    return ", ".join(items[:4]) + ", ..., " + items[-1]


def _hub_hole_index(spoke: Spoke, spoke_count: int) -> int:
    """Converte o ângulo do cubo em um furo relativo do flange (0-based).

    O flange direito é escalonado meio passo em relação ao esquerdo, como nos
    cubos convencionais. A numeração é apenas uma referência de montagem.
    """

    hub_hole_count = spoke_count // 2
    hub_spacing = 360.0 / hub_hole_count
    stagger = 0.5 if spoke.side is Side.RIGHT else 0.0
    raw = spoke.hub_angle_deg / hub_spacing - stagger
    return int(round(raw)) % hub_hole_count


def _common_steps(spec: WheelSpec) -> tuple[str, ...]:
    group_size = spec.spoke_count // 4
    angle = spoke_angle_deg(spec.spoke_count, spec.crossings)
    steps = [
        (
            "Numere os furos do aro de 1 a "
            f"{spec.spoke_count} no sentido de rolagem, começando no primeiro "
            "furo de raio ao lado da válvula."
        ),
        (
            "Numere os furos de cada flange de 1 a "
            f"{spec.spoke_count // 2}; a numeração é relativa e serve para "
            "conferência."
        ),
        (
            f"Separe os raios em quatro conjuntos de {group_size} raios: "
            "esquerda leading, direita leading, esquerda trailing e direita "
            "trailing."
        ),
        (
            "Monte um conjunto por vez. Rosqueie os niples 2 voltas para "
            "segurar os raios; só tencione depois dos quatro conjuntos."
        ),
    ]
    if spec.crossings > 0:
        steps.append(
            f"Confira o padrão: T = {_fmt(angle, 1)}°; cada raio deve cruzar "
            f"{spec.crossings} raio(s)."
        )
        steps.append(
            "Ao instalar os raios trailing, mantenha o entrelaçamento "
            "constante no último cruzamento com os leading."
        )
    else:
        steps.append(
            "Montagem radial: não há cruzamentos; siga apenas os furos "
            "indicados e confira se os raios não se tocam."
        )
    return tuple(steps)


def _group_instructions(
    spec: WheelSpec,
    side: Side,
    direction: SpokeDirection,
    rim_holes: tuple[int, ...],
    hub_holes: tuple[int, ...],
) -> tuple[str, ...]:
    hub_set = sorted(set(hub_holes))
    lines = [
        f"Use os furos do aro: {_format_number_list(rim_holes)}.",
        (
            f"Use os furos do flange {side.label_pt}: "
            f"{_format_number_list(hub_set)}."
        ),
        (
            f"Coloque os {len(rim_holes)} raios deste conjunto no flange "
            f"{side.label_pt}, no sentido {direction.label_pt}, e leve cada "
            "um ao furo do aro correspondente."
        ),
        "Rosqueie o niple 2 voltas; não tencione ainda.",
    ]
    if spec.crossings == 0:
        lines.append(
            "Montagem radial: não há cruzamento; confira apenas se os raios "
            "não se tocam."
        )
    elif direction is SpokeDirection.TRAILING:
        lines.append(
            "Se já houver raios leading, passe o trailing pelo lado oposto no "
            "último cruzamento e mantenha o mesmo padrão em toda a roda."
        )
    return tuple(lines)


@dataclass(frozen=True)
class AssemblyGroup:
    """Um dos quatro conjuntos de raios."""

    number: int
    side: Side
    direction: SpokeDirection
    title: str
    spoke_indices: tuple[int, ...]
    rim_holes: tuple[int, ...]
    hub_holes: tuple[int, ...]
    instructions: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.spoke_indices)

    @property
    def rows(self) -> tuple[tuple[int, int, int], ...]:
        return tuple(zip(self.spoke_indices, self.rim_holes, self.hub_holes))

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "side": self.side.value,
            "direction": self.direction.value,
            "count": self.count,
            "spoke_indices": list(self.spoke_indices),
            "rim_holes": list(self.rim_holes),
            "hub_holes": list(self.hub_holes),
            "rows": [
                {"spoke_index": spoke, "rim_hole": rim, "hub_hole": hub}
                for spoke, rim, hub in self.rows
            ],
            "instructions": list(self.instructions),
        }

    def to_text(self) -> str:
        lines = [
            f"=== {self.title} ===",
            f"Raios: {self.count}",
            f"Furos do aro: {_format_number_list(self.rim_holes)}",
            (
                "Furos do flange: "
                f"{_format_number_list(sorted(set(self.hub_holes)))}"
            ),
            "",
            "Pares (raio: aro → cubo):",
        ]
        lines.extend(
            f"  raio {spoke:2d}: aro {rim:2d} → cubo {hub:2d}"
            for spoke, rim, hub in self.rows
        )
        lines.extend(["", "Instruções:"])
        lines.extend(f"• {instruction}" for instruction in self.instructions)
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"### {self.title}",
            "",
            f"- **Raios:** {self.count}",
            f"- **Furos do aro:** {_format_number_list(self.rim_holes)}",
            (
                "- **Furos do flange:** "
                f"{_format_number_list(sorted(set(self.hub_holes)))}"
            ),
            "",
            "| Raio | Furo do aro | Furo do cubo |",
            "| ---: | ---: | ---: |",
        ]
        lines.extend(
            f"| {spoke} | {rim} | {hub} |"
            for spoke, rim, hub in self.rows
        )
        lines.extend(["", "**Instruções:**", ""])
        lines.extend(f"- {instruction}" for instruction in self.instructions)
        return "\n".join(lines)

    def to_html(self) -> str:
        rows = "".join(
            f"<tr><td>{spoke}</td><td>{rim}</td><td>{hub}</td></tr>"
            for spoke, rim, hub in self.rows
        )
        instructions = "".join(
            f"<li>{escape(instruction)}</li>"
            for instruction in self.instructions
        )
        return f"""<h3>{escape(self.title)}</h3>
<ul>
<li><strong>Raios:</strong> {self.count}</li>
<li><strong>Furos do aro:</strong> {escape(_format_number_list(self.rim_holes))}</li>
<li><strong>Furos do flange:</strong> {escape(_format_number_list(sorted(set(self.hub_holes))))}</li>
</ul>
<table>
<tr><th>Raio</th><th>Furo do aro</th><th>Furo do cubo</th></tr>
{rows}
</table>
<p><strong>Instruções:</strong></p>
<ul>{instructions}</ul>
"""


@dataclass(frozen=True)
class AssemblyPlan:
    """Plano completo dos quatro conjuntos."""

    spec: WheelSpec
    groups: tuple[AssemblyGroup, ...]
    steps: tuple[str, ...]
    warnings: tuple[str, ...]
    notes: tuple[str, ...] = _NOTES

    @property
    def group_size(self) -> int:
        return self.spec.spoke_count // 4

    @property
    def angle_deg(self) -> float:
        return spoke_angle_deg(self.spec.spoke_count, self.spec.crossings)

    def group_by_number(self, number: int) -> AssemblyGroup:
        for group in self.groups:
            if group.number == number:
                return group
        raise ValueError(f"Conjunto {number} não existe no plano.")

    def to_text(self, focus_group: int | None = None) -> str:
        lines = [
            "=== ASSISTENTE DOS 4 CONJUNTOS ===",
            (
                f"Roda: {self.spec.spoke_count} raios, "
                f"{self.spec.crossings}x, T = {_fmt(self.angle_deg, 1)}°"
            ),
            f"Cada conjunto: {self.group_size} raios.",
            "",
            "Passos gerais:",
        ]
        lines.extend(
            f"{number}. {step}" for number, step in enumerate(self.steps, start=1)
        )
        if focus_group is None:
            groups = self.groups
        else:
            groups = (self.group_by_number(focus_group),)
            lines.extend(
                [
                    "",
                    f"Conjunto {focus_group} de {len(self.groups)}.",
                ]
            )
        for group in groups:
            lines.extend(["", group.to_text()])
        if self.warnings:
            lines.extend(["", "Avisos:"])
            lines.extend(f"• {warning}" for warning in self.warnings)
        lines.extend(["", "Notas:"])
        lines.extend(f"• {note}" for note in self.notes)
        return "\n".join(lines)

    def to_markdown(self, include_warnings: bool = True) -> str:
        lines = [
            "## Assistente de montagem (4 conjuntos)",
            "",
            (
                f"Roda de {self.spec.spoke_count} raios, "
                f"{self.spec.crossings}x, T = {_fmt(self.angle_deg, 1)}°. "
                f"Cada conjunto tem {self.group_size} raios."
            ),
            "",
            "| Conjunto | Lado | Sentido | Raios | Furos do aro | Furos do cubo |",
            "| ---: | --- | --- | ---: | --- | --- |",
        ]
        for group in self.groups:
            lines.append(
                f"| {group.number} | {_side_title(group.side)} | "
                f"{group.direction.label_pt} | {group.count} | "
                f"{_format_number_list(group.rim_holes)} | "
                f"{_format_number_list(sorted(set(group.hub_holes)))} |"
            )
        lines.extend(["", "### Passos gerais", ""])
        lines.extend(
            f"{number}. {step}" for number, step in enumerate(self.steps, start=1)
        )
        for group in self.groups:
            lines.extend(["", group.to_markdown()])
        if include_warnings and self.warnings:
            lines.extend(["", "### Avisos", ""])
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.extend(["", "### Notas", ""])
        lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)

    def to_html(self, include_warnings: bool = True) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{group.number}</td>"
            f"<td>{escape(_side_title(group.side))}</td>"
            f"<td>{escape(group.direction.label_pt)}</td>"
            f"<td>{group.count}</td>"
            f"<td>{escape(_format_number_list(group.rim_holes))}</td>"
            f"<td>{escape(_format_number_list(sorted(set(group.hub_holes))))}</td>"
            "</tr>"
            for group in self.groups
        )
        steps = "".join(
            f"<li>{escape(step)}</li>" for step in self.steps
        )
        groups = "".join(group.to_html() for group in self.groups)
        warnings = ""
        if include_warnings and self.warnings:
            warnings = (
                "<h3>Avisos</h3><ul class='warn'>"
                + "".join(f"<li>{escape(warning)}</li>" for warning in self.warnings)
                + "</ul>"
            )
        notes = "".join(
            f"<li>{escape(note)}</li>" for note in self.notes
        )
        return f"""<h2>Assistente de montagem (4 conjuntos)</h2>
<p>Roda de {self.spec.spoke_count} raios, {self.spec.crossings}x,
T = {_fmt(self.angle_deg, 1)}°. Cada conjunto tem {self.group_size} raios.</p>
<table>
<tr><th>Conjunto</th><th>Lado</th><th>Sentido</th><th>Raios</th>
<th>Furos do aro</th><th>Furos do cubo</th></tr>
{rows}
</table>
<h3>Passos gerais</h3>
<ol>{steps}</ol>
{groups}
{warnings}
<h3>Notas</h3>
<ul>{notes}</ul>
"""

    def to_dict(self) -> dict:
        return {
            "wheel": {
                "spoke_count": self.spec.spoke_count,
                "crossings": self.spec.crossings,
                "angle_deg": self.angle_deg,
                "group_size": self.group_size,
                "erd_mm": self.spec.erd_mm,
            },
            "steps": list(self.steps),
            "groups": [group.to_dict() for group in self.groups],
            "warnings": list(self.warnings),
            "notes": list(self.notes),
        }


def _assembly_warnings(
    spec: WheelSpec, groups: tuple[AssemblyGroup, ...]
) -> tuple[str, ...]:
    warnings: list[str] = []
    if spec.crossings == 0:
        warnings.append(
            "Montagem radial: leading/trailing são apenas referências de "
            "furação; não há cruzamentos."
        )
    if math.isclose(
        spoke_angle_deg(spec.spoke_count, spec.crossings),
        90.0,
        abs_tol=1e-6,
    ):
        warnings.append(
            "Ângulo de cruzamento no limite de 90°; confira a folga do raio "
            "no flange."
        )
    if any(group.count != spec.spoke_count // 4 for group in groups):
        warnings.append(
            "Os quatro conjuntos não têm o mesmo número de raios; confira o "
            "padrão de montagem."
        )
    if spec.locknut_spacing_mm is None:
        warnings.append(
            "Distância entre locknuts não informada; o assistente não valida "
            "o dish."
        )
    return tuple(warnings)


def build_assembly_plan(spec: WheelSpec) -> AssemblyPlan:
    """Gera o plano dos quatro conjuntos para ``spec``."""

    spec.validate()
    if spec.spoke_count % 4 != 0:
        raise ValueError(
            "O assistente dos 4 conjuntos exige número de raios múltiplo de 4."
        )

    spokes = build_spoke_table(spec.spoke_count, spec.crossings)
    groups: list[AssemblyGroup] = []
    for number, (side, direction) in enumerate(_GROUP_ORDER, start=1):
        selected = [
            spoke
            for spoke in spokes
            if spoke.side is side and spoke.direction is direction
        ]
        if not selected:
            raise ValueError(
                f"Não foi possível montar o conjunto {number} "
                f"({side.label_pt}, {direction.label_pt})."
            )
        indices = tuple(spoke.index for spoke in selected)
        rim_holes = tuple(index + 1 for index in indices)
        hub_holes = tuple(
            _hub_hole_index(spoke, spec.spoke_count) + 1 for spoke in selected
        )
        title = (
            f"Conjunto {number} — {_side_title(side)} / "
            f"{direction.label_pt}"
        )
        groups.append(
            AssemblyGroup(
                number=number,
                side=side,
                direction=direction,
                title=title,
                spoke_indices=indices,
                rim_holes=rim_holes,
                hub_holes=hub_holes,
                instructions=_group_instructions(
                    spec,
                    side,
                    direction,
                    rim_holes,
                    hub_holes,
                ),
            )
        )

    return AssemblyPlan(
        spec=spec,
        groups=tuple(groups),
        steps=_common_steps(spec),
        warnings=_assembly_warnings(spec, tuple(groups)),
        notes=_NOTES,
    )


__all__ = [
    "AssemblyGroup",
    "AssemblyPlan",
    "build_assembly_plan",
]
