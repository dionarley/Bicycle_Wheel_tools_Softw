"""Biblioteca de componentes para a montagem da roda.

Os componentes são dados puros (sem Qt e sem NumPy) e servem para preencher
as medidas do cálculo e para registrar o que foi usado na ficha de montagem.
Os presets são exemplos de referência: confira sempre as medidas reais do aro,
do cubo e do raio antes de comprar ou montar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _fmt(value: float, decimals: int = 1) -> str:
    """Formata número no padrão brasileiro."""

    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} deve ter um nome.")


def _require_positive(name: str, value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} deve ser um número positivo.")


def _require_spoke_count(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} deve ser um inteiro.")
    if value < 8 or value % 4 != 0:
        raise ValueError(
            f"{name} deve ser múltiplo de 4 e maior ou igual a 8."
        )


@dataclass(frozen=True)
class RimComponent:
    """Aro com ERD e furação."""

    name: str
    erd_mm: float
    spoke_count: int
    material: str = "alumínio"
    notes: str = ""

    def validate(self) -> None:
        _require_text("O aro", self.name)
        _require_positive("O ERD do aro", self.erd_mm)
        _require_spoke_count("O número de furos do aro", self.spoke_count)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "erd_mm": self.erd_mm,
            "spoke_count": self.spoke_count,
            "material": self.material,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HubComponent:
    """Cubo com PCD, offsets e distância entre locknuts."""

    name: str
    spoke_count: int
    left_flange_diameter_mm: float
    right_flange_diameter_mm: float
    left_flange_offset_mm: float
    right_flange_offset_mm: float
    hole_diameter_mm: float = 2.6
    locknut_spacing_mm: float | None = None
    notes: str = ""

    def validate(self) -> None:
        _require_text("O cubo", self.name)
        _require_spoke_count("O número de furos do cubo", self.spoke_count)
        _require_positive(
            "O diâmetro do flange esquerdo", self.left_flange_diameter_mm
        )
        _require_positive(
            "O diâmetro do flange direito", self.right_flange_diameter_mm
        )
        _require_positive(
            "O offset do flange esquerdo", self.left_flange_offset_mm
        )
        _require_positive(
            "O offset do flange direito", self.right_flange_offset_mm
        )
        _require_positive("O diâmetro do furo do flange", self.hole_diameter_mm)
        if self.hole_diameter_mm >= min(
            self.left_flange_diameter_mm, self.right_flange_diameter_mm
        ):
            raise ValueError(
                "O diâmetro do furo do flange deve ser menor que o diâmetro "
                "do flange."
            )
        if self.locknut_spacing_mm is not None:
            _require_positive(
                "A distância entre locknuts", self.locknut_spacing_mm
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "spoke_count": self.spoke_count,
            "left_flange_diameter_mm": self.left_flange_diameter_mm,
            "right_flange_diameter_mm": self.right_flange_diameter_mm,
            "left_flange_offset_mm": self.left_flange_offset_mm,
            "right_flange_offset_mm": self.right_flange_offset_mm,
            "hole_diameter_mm": self.hole_diameter_mm,
            "locknut_spacing_mm": self.locknut_spacing_mm,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SpokeComponent:
    """Raio. ``diameter_mm`` é o diâmetro equivalente usado no cálculo."""

    name: str
    diameter_mm: float
    material: str = "aço inox"
    butted: bool = False
    notes: str = ""

    def validate(self) -> None:
        _require_text("O raio", self.name)
        _require_positive("O diâmetro do raio", self.diameter_mm)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "diameter_mm": self.diameter_mm,
            "material": self.material,
            "butted": self.butted,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class NippleComponent:
    """Niple usado no aro."""

    name: str
    length_mm: float
    material: str = "latão"
    notes: str = ""

    def validate(self) -> None:
        _require_text("O niple", self.name)
        _require_positive("O comprimento do niple", self.length_mm)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "length_mm": self.length_mm,
            "material": self.material,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ComponentSet:
    """Conjunto de componentes selecionado para uma montagem."""

    rim: RimComponent
    hub: HubComponent
    spoke: SpokeComponent
    nipple: NippleComponent
    notes: str = ""

    def validate(self) -> None:
        self.rim.validate()
        self.hub.validate()
        self.spoke.validate()
        self.nipple.validate()
        if self.rim.spoke_count != self.hub.spoke_count:
            raise ValueError(
                "O aro e o cubo têm números de furos diferentes: "
                f"{self.rim.spoke_count} e {self.hub.spoke_count}."
            )
        if self.rim.erd_mm <= max(
            self.hub.left_flange_diameter_mm,
            self.hub.right_flange_diameter_mm,
        ):
            raise ValueError(
                "O ERD do aro deve ser maior que os diâmetros dos flanges."
            )

    def to_spec(
        self,
        crossings: int = 3,
        rim_offset_mm: float = 0.0,
        spoke_count: int | None = None,
    ):
        """Monta um :class:`WheelSpec` a partir dos componentes.

        O número de raios é o do aro/cubo; ``spoke_count`` existe apenas para
        conferência e precisa coincidir com os dois.
        """

        from .models import WheelSpec

        self.validate()
        count = self.rim.spoke_count if spoke_count is None else int(spoke_count)
        if count != self.rim.spoke_count or count != self.hub.spoke_count:
            raise ValueError(
                "O número de raios informado não coincide com a furação do "
                "aro e do cubo."
            )

        spec = WheelSpec(
            erd_mm=self.rim.erd_mm,
            left_flange_diameter_mm=self.hub.left_flange_diameter_mm,
            right_flange_diameter_mm=self.hub.right_flange_diameter_mm,
            left_flange_offset_mm=self.hub.left_flange_offset_mm,
            right_flange_offset_mm=self.hub.right_flange_offset_mm,
            hole_diameter_mm=self.hub.hole_diameter_mm,
            spoke_count=count,
            crossings=int(crossings),
            rim_offset_mm=float(rim_offset_mm),
            locknut_spacing_mm=self.hub.locknut_spacing_mm,
        )
        spec.validate()
        return spec

    def compatibility_warnings(
        self, spec, spoke_diameter_mm: float | None = None
    ) -> list[str]:
        """Lista diferenças entre os componentes e as medidas do cálculo."""

        warnings: list[str] = []
        if self.rim.spoke_count != spec.spoke_count:
            warnings.append(
                f"O aro selecionado é de {self.rim.spoke_count} furos, mas o "
                f"cálculo usa {spec.spoke_count} raios."
            )
        if self.hub.spoke_count != spec.spoke_count:
            warnings.append(
                f"O cubo selecionado é de {self.hub.spoke_count} furos, mas o "
                f"cálculo usa {spec.spoke_count} raios."
            )
        if not math.isclose(self.rim.erd_mm, spec.erd_mm, abs_tol=0.01):
            warnings.append(
                f"O aro selecionado tem ERD {_fmt(self.rim.erd_mm, 1)} mm, "
                f"mas o cálculo usa {_fmt(spec.erd_mm, 1)} mm."
            )
        for label, component_value, spec_value in (
            (
                "PCD do flange esquerdo",
                self.hub.left_flange_diameter_mm,
                spec.left_flange_diameter_mm,
            ),
            (
                "PCD do flange direito",
                self.hub.right_flange_diameter_mm,
                spec.right_flange_diameter_mm,
            ),
            (
                "offset do flange esquerdo",
                self.hub.left_flange_offset_mm,
                spec.left_flange_offset_mm,
            ),
            (
                "offset do flange direito",
                self.hub.right_flange_offset_mm,
                spec.right_flange_offset_mm,
            ),
            (
                "diâmetro do furo do flange",
                self.hub.hole_diameter_mm,
                spec.hole_diameter_mm,
            ),
        ):
            if not math.isclose(component_value, spec_value, abs_tol=0.01):
                warnings.append(
                    f"O cubo selecionado tem {label} "
                    f"{_fmt(component_value, 1)} mm, mas o cálculo usa "
                    f"{_fmt(spec_value, 1)} mm."
                )
        if self.hub.locknut_spacing_mm is None:
            if spec.locknut_spacing_mm is not None:
                warnings.append(
                    "O cubo selecionado não informa a distância entre "
                    "locknuts; o cálculo usa "
                    f"{_fmt(spec.locknut_spacing_mm, 1)} mm."
                )
        elif spec.locknut_spacing_mm is None:
            warnings.append(
                "O cubo selecionado tem OLD "
                f"{_fmt(self.hub.locknut_spacing_mm, 1)} mm, mas a distância "
                "entre locknuts não foi informada no cálculo."
            )
        elif not math.isclose(
            self.hub.locknut_spacing_mm,
            spec.locknut_spacing_mm,
            abs_tol=0.01,
        ):
            warnings.append(
                "O cubo selecionado tem OLD "
                f"{_fmt(self.hub.locknut_spacing_mm, 1)} mm, mas o cálculo "
                f"usa {_fmt(spec.locknut_spacing_mm, 1)} mm."
            )
        if (
            spoke_diameter_mm is not None
            and not math.isclose(
                self.spoke.diameter_mm,
                spoke_diameter_mm,
                abs_tol=0.01,
            )
        ):
            warnings.append(
                f"O raio selecionado tem diâmetro "
                f"{_fmt(self.spoke.diameter_mm, 2)} mm, mas o cálculo usa "
                f"{_fmt(spoke_diameter_mm, 2)} mm."
            )
        return warnings

    def summary_lines(self) -> list[str]:
        """Linhas curtas para a interface e para a ficha."""

        locknuts = (
            "não informado"
            if self.hub.locknut_spacing_mm is None
            else f"{_fmt(self.hub.locknut_spacing_mm, 1)} mm"
        )
        return [
            (
                f"Aro: {self.rim.name} — ERD {_fmt(self.rim.erd_mm, 1)} mm, "
                f"{self.rim.spoke_count} furos, {self.rim.material}"
            ),
            (
                f"Cubo: {self.hub.name} — {self.hub.spoke_count} furos, PCD "
                f"{_fmt(self.hub.left_flange_diameter_mm, 1)} / "
                f"{_fmt(self.hub.right_flange_diameter_mm, 1)} mm, offsets "
                f"{_fmt(self.hub.left_flange_offset_mm, 1)} / "
                f"{_fmt(self.hub.right_flange_offset_mm, 1)} mm, OLD "
                f"{locknuts}"
            ),
            (
                f"Raios: {self.spoke.name} — Ø "
                f"{_fmt(self.spoke.diameter_mm, 2)} mm, {self.spoke.material}"
                + (" (butted)" if self.spoke.butted else "")
            ),
            (
                f"Niples: {self.nipple.name} — "
                f"{_fmt(self.nipple.length_mm, 1)} mm, {self.nipple.material}"
            ),
        ]

    def summary_text(self) -> str:
        return "\n".join(self.summary_lines())

    def to_dict(self) -> dict:
        return {
            "rim": self.rim.to_dict(),
            "hub": self.hub.to_dict(),
            "spoke": self.spoke.to_dict(),
            "nipple": self.nipple.to_dict(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ComponentLibrary:
    """Coleção de presets de componentes."""

    rims: tuple[RimComponent, ...]
    hubs: tuple[HubComponent, ...]
    spokes: tuple[SpokeComponent, ...]
    nipples: tuple[NippleComponent, ...]

    def validate(self) -> None:
        for label, items in (
            ("aros", self.rims),
            ("cubos", self.hubs),
            ("raios", self.spokes),
            ("niples", self.nipples),
        ):
            if not items:
                raise ValueError(f"A biblioteca precisa ter pelo menos um {label}.")
            names = [item.name for item in items]
            if len(set(names)) != len(names):
                raise ValueError(f"Há nomes repetidos na lista de {label}.")
            for item in items:
                item.validate()

    def default_set(self) -> ComponentSet:
        self.validate()
        return ComponentSet(
            rim=self.rims[0],
            hub=self.hubs[0],
            spoke=self.spokes[0],
            nipple=self.nipples[0],
        )

    def find_rim(self, name: str) -> RimComponent:
        return _find(self.rims, name, "aro")

    def find_hub(self, name: str) -> HubComponent:
        return _find(self.hubs, name, "cubo")

    def find_spoke(self, name: str) -> SpokeComponent:
        return _find(self.spokes, name, "raio")

    def find_nipple(self, name: str) -> NippleComponent:
        return _find(self.nipples, name, "niple")

    def to_dict(self) -> dict:
        return {
            "rims": [rim.to_dict() for rim in self.rims],
            "hubs": [hub.to_dict() for hub in self.hubs],
            "spokes": [spoke.to_dict() for spoke in self.spokes],
            "nipples": [nipple.to_dict() for nipple in self.nipples],
        }


def _find(items, name: str, label: str):
    for item in items:
        if item.name == name:
            return item
    raise ValueError(f"{label.capitalize()} não encontrado na biblioteca: {name}")


def default_component_library() -> ComponentLibrary:
    """Biblioteca de presets de exemplo, em unidades métricas."""

    library = ComponentLibrary(
        rims=(
            RimComponent(
                "Aro 700c alumínio 32h (ERD 600 mm)",
                600.0,
                32,
                "alumínio",
                "Preset de referência para estrada/ciclocrismo.",
            ),
            RimComponent(
                "Aro 700c alumínio 36h (ERD 602 mm)",
                602.0,
                36,
                "alumínio",
                "Furação 36h para carga maior ou tandem.",
            ),
            RimComponent(
                "Aro 700c alumínio 28h (ERD 601 mm)",
                601.0,
                28,
                "alumínio",
                "Furação 28h; confira o ERD real do lote.",
            ),
            RimComponent(
                "Aro 700c carbono 24h (ERD 595 mm)",
                595.0,
                24,
                "carbono",
                "Perfil profundo; use niples compatíveis.",
            ),
            RimComponent(
                "Aro 29\" alumínio 32h (ERD 590 mm)",
                590.0,
                32,
                "alumínio",
                "MTB 29er; confira a largura interna.",
            ),
            RimComponent(
                "Aro 26\" alumínio 36h (ERD 540 mm)",
                540.0,
                36,
                "alumínio",
                "MTB clássica 26\"; ERD típico de perfil baixo.",
            ),
        ),
        hubs=(
            HubComponent(
                "Cubo traseiro 32h, 130 mm (PCD 45/45, offsets 35/19)",
                32,
                45.0,
                45.0,
                35.0,
                19.0,
                2.6,
                130.0,
                "Estrada/gravel; OLD 130 mm.",
            ),
            HubComponent(
                "Cubo dianteiro 32h, 100 mm (PCD 45/45, offsets 35/35)",
                32,
                45.0,
                45.0,
                35.0,
                35.0,
                2.6,
                100.0,
                "Dianteiro estrada/MTB; OLD 100 mm.",
            ),
            HubComponent(
                "Cubo traseiro 36h, 135 mm (PCD 45/45, offsets 36/20)",
                36,
                45.0,
                45.0,
                36.0,
                20.0,
                2.6,
                135.0,
                "MTB/trekking; OLD 135 mm.",
            ),
            HubComponent(
                "Cubo dianteiro 36h, 100 mm (PCD 45/45, offsets 35/35)",
                36,
                45.0,
                45.0,
                35.0,
                35.0,
                2.6,
                100.0,
                "Dianteiro 36h; OLD 100 mm.",
            ),
            HubComponent(
                "Cubo traseiro 28h, 130 mm (PCD 45/45, offsets 35/19)",
                28,
                45.0,
                45.0,
                35.0,
                19.0,
                2.6,
                130.0,
                "Traseiro 28h; OLD 130 mm.",
            ),
            HubComponent(
                "Cubo traseiro 24h, 130 mm (PCD 45/45, offsets 35/19)",
                24,
                45.0,
                45.0,
                35.0,
                19.0,
                2.6,
                130.0,
                "Traseiro 24h; OLD 130 mm.",
            ),
            HubComponent(
                "Cubo dianteiro 32h disco, 100 mm (PCD 58/58, offsets 33/33)",
                32,
                58.0,
                58.0,
                33.0,
                33.0,
                2.6,
                100.0,
                "Freio a disco; confira o offset do rotor.",
            ),
            HubComponent(
                "Cubo traseiro 32h boost, 148 mm (PCD 58/58, offsets 37/22)",
                32,
                58.0,
                58.0,
                37.0,
                22.0,
                2.6,
                148.0,
                "Boost 148 mm; confira a linha de corrente.",
            ),
        ),
        spokes=(
            SpokeComponent(
                "Raio reto 2,0 mm",
                2.0,
                "aço inox",
                False,
                "Comprimento calculado pela equação de Brandt.",
            ),
            SpokeComponent(
                "Raio butted 2,0/1,8/2,0 mm",
                1.8,
                "aço inox",
                True,
                "Diâmetro equivalente da seção fina para alongamento/tom.",
            ),
            SpokeComponent(
                "Raio butted 2,0/1,5/2,0 mm",
                1.5,
                "aço inox",
                True,
                "Mais leve; a seção fina alonga mais sob a mesma tensão.",
            ),
            SpokeComponent(
                "Raio reto 1,8 mm",
                1.8,
                "aço inox",
                False,
                "Alternativa mais leve ao raio reto 2,0 mm.",
            ),
        ),
        nipples=(
            NippleComponent(
                "Niple latão 12 mm",
                12.0,
                "latão",
                "Padrão; boa resistência e lubrificação.",
            ),
            NippleComponent(
                "Niple alumínio 12 mm",
                12.0,
                "alumínio",
                "Leve; menor resistência ao aperto repetido.",
            ),
            NippleComponent(
                "Niple latão 14 mm",
                14.0,
                "latão",
                "Para aros com furação profunda.",
            ),
            NippleComponent(
                "Niple latão 16 mm",
                16.0,
                "latão",
                "Aros profundos; confira o ERD e o comprimento do raio.",
            ),
        ),
    )
    library.validate()
    return library


__all__ = [
    "ComponentLibrary",
    "ComponentSet",
    "HubComponent",
    "NippleComponent",
    "RimComponent",
    "SpokeComponent",
    "default_component_library",
]
