#!/usr/bin/env python3
"""Wheel Lab — calculador e alinhador de rodas de bicicleta.

Fase 1: calculadora completa, visualizador de montagem, dish/centralização e
ficha de montagem (JSON, Markdown e PDF). Fase 2: solver elástico de truing
(aro + raios só-tração), tensões, runout e sugestões de ajuste.
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPen,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPrintSupport import QPrinter
except ImportError:  # pragma: no cover - depende da instalação do PySide6
    QPrinter = None  # type: ignore[assignment]

from wheel_lab.core import (
    AssemblyPlan,
    BuildSheet,
    ComponentSet,
    Side,
    SpokeDirection,
    TruingState,
    TruingSuggestion,
    WheelSpec,
    build_spoke_table,
    create_build_sheet,
    default_component_library,
    erd_from_outer_diameter,
    is_valid_cross_pattern,
    max_crossings,
    turns_to_mm,
)

EXAGGERATION = 20.0
"""Fator de exageração dos desvios no desenho (1 mm real = 20 mm na tela)."""


def _fmt(value: float, decimals: int = 0) -> str:
    """Formata número no padrão brasileiro (vírgula decimal, ponto de milhar)."""

    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


class WheelVisualizer(QWidget):
    """Desenho esquemático da roda, dos raios e dos desvios."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spoke_count = 32
        self.crossings = 3
        self.erd_mm = 600.0
        self.lateral_offsets: list[float] = []
        self.radial_offsets: list[float] = []
        self.spokes = []
        self.error_message = ""
        self.show_left = True
        self.show_right = True
        self.show_leading = True
        self.show_trailing = True
        self.selected_index: int | None = None
        self.highlighted_indices: set[int] = set()
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(440, 440)

    def set_wheel(
        self,
        spoke_count: int,
        crossings: int,
        erd_mm: float,
        lateral_offsets: list[float],
        radial_offsets: list[float],
    ) -> None:
        self.spoke_count = int(spoke_count)
        self.crossings = int(crossings)
        try:
            erd_value = float(erd_mm)
        except (TypeError, ValueError):
            erd_value = 600.0
        self.erd_mm = erd_value if math.isfinite(erd_value) and erd_value > 0 else 600.0
        self.lateral_offsets = self._fit(lateral_offsets, self.spoke_count)
        self.radial_offsets = self._fit(radial_offsets, self.spoke_count)

        try:
            self.spokes = build_spoke_table(self.spoke_count, self.crossings)
            self.error_message = ""
        except ValueError as exc:
            self.spokes = []
            self.error_message = str(exc)

        if self.selected_index is not None and self.selected_index >= len(self.spokes):
            self.selected_index = None
        self.highlighted_indices = {
            index
            for index in self.highlighted_indices
            if 0 <= index < len(self.spokes)
        }
        self.update()

    def set_visibility(
        self,
        show_left: bool,
        show_right: bool,
        show_leading: bool,
        show_trailing: bool,
    ) -> None:
        """Mostra ou esconde raios por lado e por sentido."""
        self.show_left = bool(show_left)
        self.show_right = bool(show_right)
        self.show_leading = bool(show_leading)
        self.show_trailing = bool(show_trailing)
        self.update()

    def set_selected_index(self, index: int | None) -> None:
        """Destaca um raio pelo índice; ``None`` remove o destaque."""
        if index is None:
            self.selected_index = None
        else:
            try:
                value = int(index)
            except (TypeError, ValueError):
                value = -1
            self.selected_index = value if 0 <= value < len(self.spokes) else None
        self.update()

    def set_highlighted_indices(self, indices) -> None:
        """Destaca um conjunto de raios (usado pelo assistente de montagem)."""

        if indices is None:
            self.highlighted_indices = set()
        else:
            values = set()
            for index in indices:
                try:
                    value = int(index)
                except (TypeError, ValueError):
                    continue
                if 0 <= value < len(self.spokes):
                    values.add(value)
            self.highlighted_indices = values
        self.update()

    def _spoke_visible(self, spoke) -> bool:
        if spoke.side is Side.LEFT and not self.show_left:
            return False
        if spoke.side is Side.RIGHT and not self.show_right:
            return False
        if spoke.direction is SpokeDirection.LEADING and not self.show_leading:
            return False
        if spoke.direction is SpokeDirection.TRAILING and not self.show_trailing:
            return False
        return True

    @staticmethod
    def _fit(values: list[float], size: int) -> list[float]:
        fitted = [float(value) for value in values[:size]]
        if len(fitted) < size:
            fitted.extend([0.0] * (size - len(fitted)))
        return fitted

    def paintEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor(250, 250, 252))

            if self.error_message:
                self._draw_centered_message(painter, self.error_message)
                return
            if not self.spokes:
                self._draw_centered_message(painter, "Padrão de montagem inválido.")
                return

            width = self.width()
            height = self.height()
            center = QPointF(width / 2.0, height / 2.0)
            base_radius = min(width, height) * 0.36
            px_per_mm = base_radius / max(self.erd_mm / 2.0, 1.0)

            # Aro ideal (referência).
            painter.setPen(
                QPen(QColor(150, 150, 150), 1.0, Qt.PenStyle.DashLine)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, base_radius, base_radius)

            # Perfil deformado: raio deslocado radialmente; cor indica lateral.
            rim_points: list[QPointF] = []
            for index, spoke in enumerate(self.spokes):
                angle = math.radians(spoke.rim_angle_deg)
                radius = base_radius + (
                    self.radial_offsets[index] * px_per_mm * EXAGGERATION
                )
                rim_points.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )

            for index in range(self.spoke_count):
                lateral = 0.5 * (
                    self.lateral_offsets[index]
                    + self.lateral_offsets[(index + 1) % self.spoke_count]
                )
                painter.setPen(
                    QPen(
                        self._lateral_color(lateral),
                        3.0,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.drawLine(
                    rim_points[index],
                    rim_points[(index + 1) % self.spoke_count],
                )

            # Raios. O conjunto em destaque vem por cima dos demais; o raio
            # selecionado é desenhado por último, para ficar no topo.
            hub_radius = base_radius * 0.18
            selected = self.selected_index
            highlighted = self.highlighted_indices
            for index, spoke in enumerate(self.spokes):
                if (
                    not self._spoke_visible(spoke)
                    or index == selected
                    or index in highlighted
                ):
                    continue
                self._draw_spoke(
                    painter, index, spoke, rim_points, center, hub_radius
                )
            for index in sorted(highlighted):
                if index == selected or not 0 <= index < len(self.spokes):
                    continue
                spoke = self.spokes[index]
                if not self._spoke_visible(spoke):
                    continue
                self._draw_spoke(
                    painter,
                    index,
                    spoke,
                    rim_points,
                    center,
                    hub_radius,
                    highlighted=True,
                )
            if (
                selected is not None
                and 0 <= selected < len(self.spokes)
                and self._spoke_visible(self.spokes[selected])
            ):
                self._draw_spoke(
                    painter,
                    selected,
                    self.spokes[selected],
                    rim_points,
                    center,
                    hub_radius,
                    selected=True,
                )

            # Cubo.
            painter.setPen(QPen(QColor(70, 70, 70), 1.5))
            painter.setBrush(QColor(225, 225, 230))
            painter.drawEllipse(center, hub_radius, hub_radius)
            painter.setBrush(QColor(160, 160, 165))
            painter.drawEllipse(center, hub_radius * 0.35, hub_radius * 0.35)

            # Furo da válvula (referência de montagem).
            valve_point = QPointF(
                center.x(),
                center.y() - base_radius,
            )
            painter.setPen(QPen(QColor(30, 30, 30), 1.0))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(valve_point, 4.0, 4.0)
            painter.setFont(QFont("Sans", 8))
            painter.setPen(QColor(30, 30, 30))
            painter.drawText(
                QRectF(
                    valve_point.x() - 20,
                    valve_point.y() - 22,
                    40,
                    16,
                ),
                Qt.AlignmentFlag.AlignCenter,
                "V",
            )

            self._draw_legend(painter)
        finally:
            painter.end()

    def _draw_centered_message(self, painter: QPainter, message: str) -> None:
        painter.setPen(QColor(120, 40, 40))
        painter.setFont(QFont("Sans", 10))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.TextWordWrap,
            message,
        )

    def _draw_spoke(
        self,
        painter: QPainter,
        index: int,
        spoke,
        rim_points: list[QPointF],
        center: QPointF,
        hub_radius: float,
        selected: bool = False,
        highlighted: bool = False,
    ) -> None:
        hub_angle = math.radians(spoke.hub_angle_deg)
        hub_point = QPointF(
            center.x() + hub_radius * math.cos(hub_angle),
            center.y() + hub_radius * math.sin(hub_angle),
        )
        rim_point = rim_points[index]

        if highlighted and not selected:
            painter.setPen(
                QPen(
                    QColor(0, 180, 190, 150),
                    7.5,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(hub_point, rim_point)

        if selected:
            painter.setPen(
                QPen(
                    QColor(255, 190, 0),
                    7.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(hub_point, rim_point)

        color = (
            QColor(55, 105, 220)
            if spoke.side is Side.LEFT
            else QColor(220, 65, 60)
        )
        if spoke.direction is SpokeDirection.TRAILING:
            color = color.darker(130)
        width = 2.2 if spoke.is_leading else 1.3
        if highlighted and not selected:
            width += 0.6
        if selected:
            color = QColor(255, 215, 45)
            width = 3.0
        painter.setPen(
            QPen(
                color,
                width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(hub_point, rim_point)

        if highlighted and not selected:
            painter.setBrush(QColor(0, 190, 200))
            painter.setPen(QPen(QColor(30, 30, 30), 1.0))
            painter.drawEllipse(rim_point, 3.5, 3.5)

        if selected:
            painter.setBrush(QColor(255, 215, 45))
            painter.setPen(QPen(QColor(40, 40, 40), 1.2))
            painter.drawEllipse(rim_point, 5.5, 5.5)
            painter.setFont(QFont("Sans", 8))
            painter.setPen(QColor(30, 30, 30))
            painter.drawText(
                QRectF(rim_point.x() - 32, rim_point.y() - 24, 64, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"raio {index}",
            )

    def _draw_legend(self, painter: QPainter) -> None:
        legend = (
            f"Raios: azul = esquerda, vermelho = direita\n"
            "Claro = leading, escuro = trailing\n"
            "Amarelo = raio selecionado\n"
            "Ciano = conjunto em destaque\n"
            "Aro: azul = desvio p/ esquerda, vermelho = p/ direita\n"
            f"Deslocamentos exagerados {EXAGGERATION:.0f}×"
        )
        painter.setPen(QColor(70, 70, 70))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(
            QRectF(8, self.height() - 108, self.width() - 16, 100),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            legend,
        )

    @staticmethod
    def _lateral_color(offset_mm: float) -> QColor:
        if abs(offset_mm) < 0.05:
            return QColor(110, 110, 110)
        intensity = min(1.0, abs(offset_mm) / 2.0)
        if offset_mm < 0:
            color = QColor(60, 120, 230)
        else:
            color = QColor(230, 70, 60)
        color.setAlpha(int(130 + 125 * intensity))
        return color


class CenteringView(QWidget):
    """Corte axial esquemático: aro, flanges, locknuts e dish."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec: WheelSpec | None = None
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(440, 300)

    def set_spec(self, spec: WheelSpec | None) -> None:
        self.spec = spec
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor(250, 250, 252))

            if self.spec is None:
                self._draw_message(
                    painter,
                    "Calcule os comprimentos para ver o corte e a centralização.",
                )
                return

            spec = self.spec
            width = self.width()
            height = self.height()
            margin = 50.0
            plot_top = 44.0
            plot_bottom = height - 62.0
            center_y = (plot_top + plot_bottom) / 2.0

            hub_center = spec.hub_center_mm
            flange_left = hub_center - spec.left_flange_offset_mm
            flange_right = hub_center + spec.right_flange_offset_mm
            locknuts = spec.locknut_positions_mm()

            positions = [0.0, flange_left, flange_right]
            if locknuts:
                positions.extend(locknuts)
            min_x = min(positions)
            max_x = max(positions)
            span = max(max_x - min_x, 1.0)
            min_x -= span * 0.12
            max_x += span * 0.12
            span = max(max_x - min_x, 1.0)

            def screen_x(value: float) -> float:
                return margin + (value - min_x) / span * (width - 2.0 * margin)

            scale = (width - 2.0 * margin) / span
            rim_width = max(12.0, min(18.0 * scale, 40.0))
            rim_height = min((plot_bottom - plot_top) * 0.84, 170.0)
            hub_height = rim_height * 0.56

            # Raios vistos no corte: mostram o ângulo de bracing e o dish.
            for flange_x, color in (
                (flange_left, QColor(55, 105, 220, 115)),
                (flange_right, QColor(220, 65, 60, 115)),
            ):
                for rim_sign in (-1, 1):
                    painter.setPen(
                        QPen(
                            color,
                            1.6,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                        )
                    )
                    painter.drawLine(
                        QPointF(screen_x(flange_x), center_y + rim_sign * hub_height * 0.30),
                        QPointF(screen_x(0.0), center_y + rim_sign * rim_height * 0.42),
                    )

            # Eixo e corpo do cubo.
            axle_left = locknuts[0] if locknuts else flange_left
            axle_right = locknuts[1] if locknuts else flange_right
            painter.setPen(QPen(QColor(120, 120, 125), 1.2))
            painter.drawLine(
                QPointF(screen_x(axle_left), center_y),
                QPointF(screen_x(axle_right), center_y),
            )
            painter.setPen(QPen(QColor(80, 80, 85), 1.2))
            painter.setBrush(QColor(190, 190, 198))
            painter.drawRoundedRect(
                QRectF(
                    screen_x(flange_left),
                    center_y - 7.0,
                    max(screen_x(flange_right) - screen_x(flange_left), 2.0),
                    14.0,
                ),
                4.0,
                4.0,
            )

            # Flanges.
            painter.setPen(QPen(QColor(70, 70, 80), 3.0))
            for flange_x in (flange_left, flange_right):
                painter.drawLine(
                    QPointF(screen_x(flange_x), center_y - hub_height / 2.0),
                    QPointF(screen_x(flange_x), center_y + hub_height / 2.0),
                )

            # Locknuts.
            if locknuts:
                painter.setPen(QPen(QColor(45, 45, 50), 2.0))
                for locknut_x in locknuts:
                    painter.drawLine(
                        QPointF(
                            screen_x(locknut_x),
                            center_y - hub_height * 0.42,
                        ),
                        QPointF(
                            screen_x(locknut_x),
                            center_y + hub_height * 0.42,
                        ),
                    )

            # Aro em corte.
            painter.setPen(QPen(QColor(80, 80, 90), 1.5))
            painter.setBrush(QColor(225, 225, 232))
            painter.drawRoundedRect(
                QRectF(
                    screen_x(0.0) - rim_width / 2.0,
                    center_y - rim_height / 2.0,
                    rim_width,
                    rim_height,
                ),
                5.0,
                5.0,
            )

            # Linhas de referência: plano do aro e centro do cubo.
            if abs(hub_center) < 0.05:
                painter.setPen(
                    QPen(QColor(30, 140, 70), 1.4, Qt.PenStyle.DashLine)
                )
                painter.drawLine(
                    QPointF(screen_x(0.0), plot_top - 4.0),
                    QPointF(screen_x(0.0), plot_bottom + 2.0),
                )
            else:
                painter.setPen(
                    QPen(QColor(30, 120, 210), 1.4, Qt.PenStyle.DashLine)
                )
                painter.drawLine(
                    QPointF(screen_x(0.0), plot_top - 4.0),
                    QPointF(screen_x(0.0), plot_bottom + 2.0),
                )
                painter.setPen(
                    QPen(QColor(205, 70, 60), 1.4, Qt.PenStyle.DashLine)
                )
                painter.drawLine(
                    QPointF(screen_x(hub_center), plot_top - 4.0),
                    QPointF(screen_x(hub_center), plot_bottom + 2.0),
                )

            self._draw_status(painter, spec)
            self._draw_dimension(painter, spec, screen_x, width, height)
            self._draw_labels(painter, spec, screen_x, plot_top, plot_bottom)
        finally:
            painter.end()

    def _draw_message(self, painter: QPainter, message: str) -> None:
        painter.setPen(QColor(120, 40, 40))
        painter.setFont(QFont("Sans", 10))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.TextWordWrap,
            message,
        )

    def _draw_status(self, painter: QPainter, spec: WheelSpec) -> None:
        offset = spec.rim_offset_mm
        if spec.is_centered:
            text = "Centralizada (dish ≈ 0)"
            color = QColor(25, 120, 60)
        else:
            direction = "esquerda" if offset > 0 else "direita"
            sign = "+" if offset > 0 else ""
            text = (
                f"Deslocada {sign}{_fmt(offset, 1)} mm — mover o aro "
                f"{_fmt(abs(offset), 1)} mm para a {direction}"
            )
            color = QColor(175, 45, 40)
        painter.setPen(color)
        painter.setFont(QFont("Sans", 9, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(10, 8, self.width() - 20, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )

    def _draw_dimension(
        self,
        painter: QPainter,
        spec: WheelSpec,
        screen_x,
        width: float,
        height: float,
    ) -> None:
        y = height - 30.0
        x_rim = screen_x(0.0)
        x_hub = screen_x(spec.hub_center_mm)
        painter.setPen(QPen(QColor(90, 90, 95), 1.0))
        if abs(spec.hub_center_mm) >= 0.05:
            painter.drawLine(QPointF(x_rim, y), QPointF(x_hub, y))
            for x, direction in ((x_rim, -1.0), (x_hub, 1.0)):
                painter.drawLine(
                    QPointF(x, y), QPointF(x + direction * 5.0, y - 3.0)
                )
                painter.drawLine(
                    QPointF(x, y), QPointF(x + direction * 5.0, y + 3.0)
                )
        sign = "+" if spec.rim_offset_mm > 0 else ""
        text = f"dish {sign}{_fmt(spec.rim_offset_mm, 1)} mm"
        painter.setFont(QFont("Sans", 8))
        painter.setPen(QColor(70, 70, 75))
        left = min(max((x_rim + x_hub) / 2.0 - 60.0, 2.0), width - 122.0)
        painter.drawText(
            QRectF(left, y - 18.0, 120.0, 14.0),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

    def _draw_labels(
        self,
        painter: QPainter,
        spec: WheelSpec,
        screen_x,
        plot_top: float,
        plot_bottom: float,
    ) -> None:
        self._label(
            painter, screen_x(0.0), plot_top - 18.0, "aro", QColor(70, 70, 80)
        )
        self._label(
            painter,
            screen_x(spec.hub_center_mm),
            plot_top + 18.0,
            "centro do cubo",
            QColor(25, 120, 60)
            if spec.is_centered
            else QColor(170, 60, 55),
        )

        flange_left = spec.hub_center_mm - spec.left_flange_offset_mm
        flange_right = spec.hub_center_mm + spec.right_flange_offset_mm
        self._label(
            painter,
            screen_x(flange_left),
            plot_bottom + 2.0,
            "flange E",
            QColor(55, 105, 220),
        )
        self._label(
            painter,
            screen_x(flange_right),
            plot_bottom + 2.0,
            "flange D",
            QColor(220, 65, 60),
        )

        locknuts = spec.locknut_positions_mm()
        if locknuts:
            self._label(
                painter,
                screen_x(locknuts[0]),
                plot_top + 2.0,
                "locknut E",
                QColor(50, 50, 55),
            )
            self._label(
                painter,
                screen_x(locknuts[1]),
                plot_top + 2.0,
                "locknut D",
                QColor(50, 50, 55),
            )

    def _label(
        self,
        painter: QPainter,
        x: float,
        y: float,
        text: str,
        color: QColor,
    ) -> None:
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QColor(250, 250, 252, 225))
        left = min(max(x - 50.0, 2.0), self.width() - 102.0)
        painter.drawRect(QRectF(left, y, 100.0, 14.0))
        painter.setPen(color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setFont(QFont("Sans", 7))
        painter.drawText(
            QRectF(left, y, 100.0, 14.0),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )


class WheelCalculatorApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wheel Lab — Calculador e Alinhador de Rodas")
        self.resize(1050, 720)

        self.lat_offsets: list[float] = []
        self.rad_offsets: list[float] = []
        self.last_sheet: BuildSheet | None = None
        self.truing_state: TruingState | None = None
        self.last_suggestion: TruingSuggestion | None = None

        self.component_library = default_component_library()
        self.current_components: ComponentSet | None = None
        self.assembly_plan: AssemblyPlan | None = None
        self.assembly_completed: set[int] = set()
        self._updating_assembly_list = False
        self._updating_component_combos = False

        self._build_ui()
        self.reset_sim()
        self.statusBar().showMessage(
            "Pronto. Ajuste as medidas e calcule os raios.", 5000
        )

    def _build_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tabs = QTabWidget()
        self.init_calculator_tab()
        self.init_truing_sim_tab()
        self.init_assembly_tab()
        self.init_build_sheet_tab()
        splitter.addWidget(self.tabs)

        visualizer_group = QGroupBox("Visualizador de montagem e desvios")
        viz_layout = QVBoxLayout(visualizer_group)

        display_row = QHBoxLayout()
        self.show_left_cb = QCheckBox("Esquerda")
        self.show_right_cb = QCheckBox("Direita")
        self.show_leading_cb = QCheckBox("Leading")
        self.show_trailing_cb = QCheckBox("Trailing")
        for checkbox in (
            self.show_left_cb,
            self.show_right_cb,
            self.show_leading_cb,
            self.show_trailing_cb,
        ):
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._update_view_flags)
            display_row.addWidget(checkbox)
        display_row.addStretch()
        viz_layout.addLayout(display_row)

        viz_splitter = QSplitter(Qt.Orientation.Vertical)
        self.visualizer = WheelVisualizer()
        self.centering_view = CenteringView()
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.visualizer, "Vista superior")
        self.view_tabs.addTab(self.centering_view, "Corte / dish")

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumHeight(170)
        self.info_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        viz_splitter.addWidget(self.view_tabs)
        viz_splitter.addWidget(self.info_text)
        viz_splitter.setStretchFactor(0, 3)
        viz_splitter.setStretchFactor(1, 2)
        viz_layout.addWidget(viz_splitter)

        splitter.addWidget(visualizer_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        self.spokes_count_combo.currentTextChanged.connect(
            self._on_spoke_count_changed
        )
        self.cross_combo.currentIndexChanged.connect(self._on_cross_changed)

    def init_calculator_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        rim_group = QGroupBox("Aro")
        rim_form = QFormLayout(rim_group)
        self.erd_input = QLineEdit("600.0")
        self.erd_input.setToolTip(
            "Diâmetro efetivo do aro: diâmetro em que as pontas dos raios "
            "ficam flush com a extremidade do niple."
        )
        erd_row = QWidget()
        erd_row_layout = QHBoxLayout(erd_row)
        erd_row_layout.setContentsMargins(0, 0, 0, 0)
        erd_row_layout.addWidget(self.erd_input)
        self.erd_help_btn = QPushButton("Calcular ERD...")
        self.erd_help_btn.setToolTip(
            "Calcula o ERD a partir do diâmetro externo do aro e da "
            "profundidade do niple."
        )
        self.erd_help_btn.clicked.connect(self.calculate_erd_dialog)
        erd_row_layout.addWidget(self.erd_help_btn)
        rim_form.addRow("ERD do aro (mm):", erd_row)
        layout.addWidget(rim_group)

        hub_group = QGroupBox("Cubo")
        hub_form = QFormLayout(hub_group)
        self.pcd_left_input = QLineEdit("45.0")
        self.pcd_right_input = QLineEdit("45.0")
        self.flange_left_input = QLineEdit("35.0")
        self.flange_right_input = QLineEdit("19.0")
        self.hole_dia_input = QLineEdit("2.6")

        self.pcd_left_input.setToolTip(
            "Diâmetro da circunferência dos furos do flange esquerdo "
            "(centro a centro dos furos), não o diâmetro externo do flange."
        )
        self.pcd_right_input.setToolTip(
            "Diâmetro da circunferência dos furos do flange direito "
            "(centro a centro dos furos), não o diâmetro externo do flange."
        )
        self.flange_left_input.setToolTip(
            "Distância do centro do cubo ao flange esquerdo, medida no eixo. "
            "O plano do aro é ajustado pelo dish."
        )
        self.flange_right_input.setToolTip(
            "Distância do centro do cubo ao flange direito, medida no eixo. "
            "O plano do aro é ajustado pelo dish."
        )
        self.hole_dia_input.setToolTip(
            "Diâmetro do furo do flange (comum 2,6 mm). O comprimento do "
            "raio é reduzido em metade desse valor."
        )

        self.dish_input = QLineEdit("0.0")
        self.dish_input.setToolTip(
            "Deslocamento do plano do aro em relação ao centro do cubo, em mm. "
            "Positivo = aro à direita. Use 0 para uma roda centralizada."
        )
        self.locknut_input = QLineEdit("130.0")
        self.locknut_input.setToolTip(
            "Distância entre as faces externas dos locknuts (OLD). Ex.: 130 mm "
            "no traseiro e 100 mm no dianteiro. Usada no desenho de "
            "centralização; pode ficar em branco."
        )

        hub_form.addRow("PCD esquerdo (mm):", self.pcd_left_input)
        hub_form.addRow("PCD direito (mm):", self.pcd_right_input)
        hub_form.addRow("Flange esq. ao centro (mm):", self.flange_left_input)
        hub_form.addRow("Flange dir. ao centro (mm):", self.flange_right_input)
        hub_form.addRow("Diâmetro do furo (mm):", self.hole_dia_input)
        hub_form.addRow("Dish / desloc. do aro (mm):", self.dish_input)
        hub_form.addRow("Distância entre locknuts (mm):", self.locknut_input)
        layout.addWidget(hub_group)

        pattern_group = QGroupBox("Padrão e tensão")
        pattern_form = QFormLayout(pattern_group)
        self.spokes_count_combo = QComboBox()
        self.spokes_count_combo.addItems(["24", "28", "32", "36", "40", "48"])
        self.spokes_count_combo.setCurrentText("32")
        self.spokes_count_combo.setToolTip(
            "Número total de raios. O visualizador exige múltiplo de 4."
        )

        self.cross_combo = QComboBox()
        for label, value in (
            ("0 (radial)", 0),
            ("2", 2),
            ("3", 3),
            ("4", 4),
        ):
            self.cross_combo.addItem(label, value)
        self.cross_combo.setCurrentIndex(self.cross_combo.findData(3))
        self.cross_combo.setToolTip(
            "Número de cruzamentos. O máximo é N/8 para manter T ≤ 90°."
        )

        self.target_tension_input = QLineEdit("1000")
        self.target_tension_input.setToolTip(
            "Tensão do lado mais tenso, em newtons. O outro lado é calculado "
            "pelo equilíbrio lateral."
        )
        self.spoke_diameter_input = QLineEdit("2.0")
        self.spoke_diameter_input.setToolTip(
            "Diâmetro do raio em mm (2,0 mm é comum; 1,6/1,8 mm em raios "
            "butted). Usado para alongamento e tom."
        )

        pattern_form.addRow("Número de raios:", self.spokes_count_combo)
        pattern_form.addRow("Cruzamentos:", self.cross_combo)
        pattern_form.addRow(
            "Tensão alvo do lado mais tenso (N):", self.target_tension_input
        )
        pattern_form.addRow("Diâmetro do raio (mm):", self.spoke_diameter_input)
        layout.addWidget(pattern_group)

        calc_btn = QPushButton("Calcular comprimento dos raios")
        calc_btn.clicked.connect(self.calculate_spokes)
        layout.addWidget(calc_btn)

        note = QLabel(
            "O livro manda arredondar o comprimento sempre para baixo: o raio "
            "estica sob tensão e o aro pode encolher. Os offsets são medidos do "
            "centro do cubo ao flange; o dish desloca o plano do aro."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)
        layout.addStretch()

        self.tabs.addTab(tab, "Cálculo de raios")

    def init_truing_sim_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        self.sim_spoke_idx = QLineEdit("0")
        self.sim_spoke_idx.setToolTip(
            "Índice do raio, de 0 a N-1, na ordem do padrão de montagem."
        )
        self.sim_turn_val = QComboBox()
        for label, turns in (
            ("+1/4 volta (apertar)", 0.25),
            ("-1/4 volta (soltar)", -0.25),
            ("+1/2 volta", 0.5),
            ("-1/2 volta", -0.5),
            ("+1 volta", 1.0),
            ("-1 volta", -1.0),
        ):
            self.sim_turn_val.addItem(label, turns)
        self.sim_turn_val.setToolTip(
            "1 volta ≈ 0,45 mm (56 TPI); 1/4 volta ≈ 0,11 mm."
        )

        form.addRow("Índice do raio (0 a N-1):", self.sim_spoke_idx)
        form.addRow("Ajuste no niple:", self.sim_turn_val)
        layout.addLayout(form)

        self.sim_selected_info = QLabel("Selecione um raio para ver a tensão.")
        self.sim_selected_info.setWordWrap(True)
        self.sim_selected_info.setStyleSheet("color: #555;")
        layout.addWidget(self.sim_selected_info)
        self.sim_spoke_idx.textChanged.connect(self._on_sim_index_changed)

        apply_btn = QPushButton("Aplicar ajuste")
        apply_btn.clicked.connect(self.apply_sim_adjustment)
        layout.addWidget(apply_btn)

        suggest_btn = QPushButton("Sugerir ajustes")
        suggest_btn.clicked.connect(self.suggest_sim_adjustments)
        layout.addWidget(suggest_btn)

        self.apply_suggestions_btn = QPushButton("Aplicar sugestões")
        self.apply_suggestions_btn.clicked.connect(self.apply_sim_suggestions)
        self.apply_suggestions_btn.setEnabled(False)
        layout.addWidget(self.apply_suggestions_btn)

        reset_btn = QPushButton("Resetar desvios da roda")
        reset_btn.clicked.connect(self.reset_sim)
        layout.addWidget(reset_btn)

        example_btn = QPushButton("Carregar exemplo de empeno")
        example_btn.clicked.connect(self.load_example)
        layout.addWidget(example_btn)

        note = QLabel(
            "Modelo físico da Fase 2: o aro é um anel elástico (flexão lateral, "
            "flexão no plano e hoop) e cada raio é uma mola só-tração. O ajuste "
            "encurta o comprimento livre do raio; o equilíbrio é resolvido e "
            "raios frouxos são desativados. As sugestões são um passo "
            "linearizado: aplique, recalcule e repita."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)
        layout.addStretch()

        self.tabs.addTab(tab, "Simulador de alinhamento")

    def init_assembly_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        components_group = QGroupBox("Biblioteca de componentes")
        components_form = QFormLayout(components_group)

        self.component_rim_combo = QComboBox()
        self.component_hub_combo = QComboBox()
        self.component_spoke_combo = QComboBox()
        self.component_nipple_combo = QComboBox()
        for rim in self.component_library.rims:
            self.component_rim_combo.addItem(rim.name)
        for hub in self.component_library.hubs:
            self.component_hub_combo.addItem(hub.name)
        for spoke in self.component_library.spokes:
            self.component_spoke_combo.addItem(spoke.name)
        for nipple in self.component_library.nipples:
            self.component_nipple_combo.addItem(nipple.name)

        components_form.addRow("Aro:", self.component_rim_combo)
        components_form.addRow("Cubo:", self.component_hub_combo)
        components_form.addRow("Raio:", self.component_spoke_combo)
        components_form.addRow("Niple:", self.component_nipple_combo)

        self.component_summary = QLabel()
        self.component_summary.setWordWrap(True)
        self.component_summary.setStyleSheet("color: #555;")
        components_form.addRow(self.component_summary)

        apply_components_btn = QPushButton("Aplicar componentes ao cálculo")
        apply_components_btn.clicked.connect(self.apply_components)
        components_form.addRow(apply_components_btn)
        layout.addWidget(components_group)

        assembly_group = QGroupBox("Assistente dos 4 conjuntos")
        assembly_layout = QVBoxLayout(assembly_group)

        self.assembly_progress = QLabel("Calcule os raios para gerar o plano.")
        self.assembly_progress.setWordWrap(True)
        assembly_layout.addWidget(self.assembly_progress)

        self.assembly_group_list = QListWidget()
        self.assembly_group_list.setMaximumHeight(115)
        self.assembly_group_list.currentRowChanged.connect(
            self._show_assembly_group
        )
        assembly_layout.addWidget(self.assembly_group_list)

        self.assembly_text = QTextEdit()
        self.assembly_text.setReadOnly(True)
        self.assembly_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.assembly_text.setPlainText(
            "O plano aparecerá aqui depois do cálculo."
        )
        assembly_layout.addWidget(self.assembly_text, 1)

        buttons = QHBoxLayout()
        generate_btn = QPushButton("Gerar plano")
        generate_btn.clicked.connect(self.generate_assembly_plan)
        complete_btn = QPushButton("Marcar conjunto concluído")
        complete_btn.clicked.connect(self.complete_assembly_group)
        clear_btn = QPushButton("Limpar progresso")
        clear_btn.clicked.connect(self.clear_assembly_progress)
        buttons.addWidget(generate_btn)
        buttons.addWidget(complete_btn)
        buttons.addWidget(clear_btn)
        assembly_layout.addLayout(buttons)
        layout.addWidget(assembly_group, 1)

        note = QLabel(
            "O assistente divide os raios em esquerda/direita e "
            "leading/trailing, mostra os furos do aro e do flange e destaca "
            "o conjunto atual no visualizador. A numeração é relativa: "
            "comece no primeiro furo de raio ao lado da válvula."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)

        self.tabs.addTab(tab, "Assistente de montagem")

        for combo in (
            self.component_rim_combo,
            self.component_hub_combo,
            self.component_spoke_combo,
            self.component_nipple_combo,
        ):
            combo.currentTextChanged.connect(
                self._on_component_selection_changed
            )
        self._update_component_summary()

    def init_build_sheet_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.sheet_preview = QTextEdit()
        self.sheet_preview.setReadOnly(True)
        self.sheet_preview.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.sheet_preview.setPlainText(
            "Calcule os raios para gerar a ficha de montagem."
        )
        layout.addWidget(self.sheet_preview, 1)

        buttons = QHBoxLayout()
        json_btn = QPushButton("Salvar JSON...")
        json_btn.clicked.connect(self.save_sheet_json)
        md_btn = QPushButton("Salvar Markdown...")
        md_btn.clicked.connect(self.save_sheet_markdown)
        pdf_btn = QPushButton("Exportar PDF...")
        pdf_btn.clicked.connect(self.export_sheet_pdf)
        buttons.addWidget(json_btn)
        buttons.addWidget(md_btn)
        buttons.addWidget(pdf_btn)
        layout.addLayout(buttons)

        note = QLabel(
            "A ficha reúne medidas, comprimentos, tensões, centralização e "
            "avisos. JSON serve para reutilizar os dados; Markdown e PDF, para "
            "levar para a bancada."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)

        self.tabs.addTab(tab, "Ficha de montagem")

    def _component_set_from_ui(self) -> ComponentSet:
        rim = self.component_library.find_rim(
            self.component_rim_combo.currentText()
        )
        hub = self.component_library.find_hub(
            self.component_hub_combo.currentText()
        )
        spoke = self.component_library.find_spoke(
            self.component_spoke_combo.currentText()
        )
        nipple = self.component_library.find_nipple(
            self.component_nipple_combo.currentText()
        )
        return ComponentSet(rim=rim, hub=hub, spoke=spoke, nipple=nipple)

    def _sync_component_spoke_counts(self) -> None:
        try:
            rim = self.component_library.find_rim(
                self.component_rim_combo.currentText()
            )
            hub = self.component_library.find_hub(
                self.component_hub_combo.currentText()
            )
        except ValueError:
            return
        if rim.spoke_count == hub.spoke_count:
            return

        self._updating_component_combos = True
        try:
            if self.sender() is self.component_rim_combo:
                match = next(
                    (
                        candidate
                        for candidate in self.component_library.hubs
                        if candidate.spoke_count == rim.spoke_count
                    ),
                    None,
                )
                if match is not None:
                    self.component_hub_combo.setCurrentText(match.name)
            else:
                match = next(
                    (
                        candidate
                        for candidate in self.component_library.rims
                        if candidate.spoke_count == hub.spoke_count
                    ),
                    None,
                )
                if match is not None:
                    self.component_rim_combo.setCurrentText(match.name)
        finally:
            self._updating_component_combos = False

    def _on_component_selection_changed(self, *args) -> None:
        if self._updating_component_combos:
            return
        self._sync_component_spoke_counts()
        self.current_components = None
        self._update_component_summary()

    def _update_component_summary(self, applied: bool = False) -> None:
        try:
            components = self._component_set_from_ui()
            components.validate()
        except ValueError as exc:
            self.component_summary.setText(
                f"Componentes incompatíveis: {exc}"
            )
            return
        lines = components.summary_lines()
        lines.append("")
        if applied:
            lines.append("Componentes aplicados ao cálculo.")
        else:
            lines.append(
                "Seleção ainda não aplicada; use 'Aplicar componentes ao "
                "cálculo'."
            )
        self.component_summary.setText("\n".join(lines))

    def apply_components(self) -> None:
        try:
            components = self._component_set_from_ui()
            components.validate()
            crossings = self.cross_combo.currentData()
            if crossings is None:
                raise ValueError("Selecione o número de cruzamentos.")

            dish_text = self.dish_input.text().strip().replace(",", ".")
            if dish_text:
                try:
                    dish = float(dish_text)
                except ValueError as exc:
                    raise ValueError(
                        "Dish / deslocamento do aro: informe um número válido."
                    ) from exc
                if not math.isfinite(dish):
                    raise ValueError(
                        "Dish / deslocamento do aro: informe um número finito."
                    )
            else:
                dish = 0.0

            components.to_spec(
                crossings=int(crossings),
                rim_offset_mm=dish,
            )

            self.erd_input.setText(f"{components.rim.erd_mm:.1f}")
            self.pcd_left_input.setText(
                f"{components.hub.left_flange_diameter_mm:.1f}"
            )
            self.pcd_right_input.setText(
                f"{components.hub.right_flange_diameter_mm:.1f}"
            )
            self.flange_left_input.setText(
                f"{components.hub.left_flange_offset_mm:.1f}"
            )
            self.flange_right_input.setText(
                f"{components.hub.right_flange_offset_mm:.1f}"
            )
            self.hole_dia_input.setText(
                f"{components.hub.hole_diameter_mm:.1f}"
            )
            if components.hub.locknut_spacing_mm is None:
                self.locknut_input.setText("")
            else:
                self.locknut_input.setText(
                    f"{components.hub.locknut_spacing_mm:.1f}"
                )
            self.spoke_diameter_input.setText(
                f"{components.spoke.diameter_mm:.2f}"
            )

            target_index = self.spokes_count_combo.findText(
                str(components.rim.spoke_count)
            )
            if target_index < 0:
                raise ValueError(
                    "O cálculo não oferece "
                    f"{components.rim.spoke_count} raios."
                )
            self.spokes_count_combo.setCurrentIndex(target_index)

            self.current_components = components
            self.calculate_spokes()
            if self.last_sheet is not None:
                self._update_component_summary(applied=True)
                self.statusBar().showMessage(
                    "Componentes aplicados e ficha recalculada.", 5000
                )
            else:
                self.current_components = None
                self._update_component_summary()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Biblioteca de componentes", str(exc))

    @staticmethod
    def _assembly_item_text(group, completed: bool) -> str:
        prefix = "✓ " if completed else ""
        return f"{prefix}{group.title} ({group.count} raios)"

    def _set_assembly_plan(
        self, plan: AssemblyPlan | None, reset: bool = True
    ) -> None:
        self.assembly_plan = plan
        if reset:
            self.assembly_completed.clear()

        self._updating_assembly_list = True
        try:
            self.assembly_group_list.clear()
            if plan is not None:
                for group in plan.groups:
                    self.assembly_group_list.addItem(
                        self._assembly_item_text(
                            group,
                            group.number in self.assembly_completed,
                        )
                    )
        finally:
            self._updating_assembly_list = False

        if plan is None:
            self.assembly_text.setPlainText(
                "O plano aparecerá aqui depois do cálculo."
            )
            self.assembly_progress.setText(
                "Calcule os raios para gerar o plano."
            )
            if hasattr(self, "visualizer"):
                self.visualizer.set_highlighted_indices(())
            return

        row = 0
        for index, group in enumerate(plan.groups):
            if group.number not in self.assembly_completed:
                row = index
                break
        self.assembly_group_list.setCurrentRow(row)
        self._show_assembly_group(row)
        self._update_assembly_progress()

    def _show_assembly_group(self, row: int) -> None:
        if self._updating_assembly_list:
            return
        plan = self.assembly_plan
        if plan is None or row < 0 or row >= len(plan.groups):
            self.assembly_text.setPlainText(
                "Selecione um conjunto para ver as instruções."
            )
            if hasattr(self, "visualizer"):
                self.visualizer.set_highlighted_indices(())
            self._update_assembly_progress()
            return

        group = plan.groups[row]
        self.assembly_text.setPlainText(
            plan.to_text(focus_group=group.number)
        )
        if hasattr(self, "visualizer"):
            self.visualizer.set_highlighted_indices(group.spoke_indices)
        self._update_assembly_progress()

    def _update_assembly_progress(self) -> None:
        plan = self.assembly_plan
        if plan is None:
            self.assembly_progress.setText(
                "Calcule os raios para gerar o plano."
            )
            return
        done = len(self.assembly_completed)
        total = len(plan.groups)
        row = self.assembly_group_list.currentRow()
        if done >= total:
            text = (
                f"Montagem completa: {done} de {total} conjuntos concluídos. "
                "Confira tensão e centralização."
            )
        elif 0 <= row < total:
            text = (
                f"Concluídos: {done} de {total} conjuntos. "
                f"Conjunto atual: {plan.groups[row].number}."
            )
        else:
            text = f"Concluídos: {done} de {total} conjuntos."
        self.assembly_progress.setText(text)

    def _refresh_assembly_list(self) -> None:
        plan = self.assembly_plan
        if plan is None:
            return
        row = self.assembly_group_list.currentRow()
        self._updating_assembly_list = True
        try:
            for index, group in enumerate(plan.groups):
                item = self.assembly_group_list.item(index)
                if item is not None:
                    item.setText(
                        self._assembly_item_text(
                            group,
                            group.number in self.assembly_completed,
                        )
                    )
        finally:
            self._updating_assembly_list = False
        if 0 <= row < self.assembly_group_list.count():
            self.assembly_group_list.setCurrentRow(row)

    def complete_assembly_group(self) -> None:
        plan = self.assembly_plan
        if plan is None:
            self.statusBar().showMessage("Gere o plano primeiro.", 5000)
            return
        row = self.assembly_group_list.currentRow()
        if row < 0 or row >= len(plan.groups):
            return
        group = plan.groups[row]
        self.assembly_completed.add(group.number)
        self._refresh_assembly_list()

        next_row = next(
            (
                index
                for index, candidate in enumerate(plan.groups)
                if candidate.number not in self.assembly_completed
            ),
            None,
        )
        if next_row is not None:
            self.assembly_group_list.setCurrentRow(next_row)
            self._show_assembly_group(next_row)
        else:
            self._show_assembly_group(row)
        self._update_assembly_progress()
        self.statusBar().showMessage(
            f"Conjunto {group.number} concluído.", 5000
        )

    def clear_assembly_progress(self) -> None:
        if self.assembly_plan is None:
            return
        self.assembly_completed.clear()
        self._refresh_assembly_list()
        self.assembly_group_list.setCurrentRow(0)
        self._show_assembly_group(0)
        self._update_assembly_progress()
        self.statusBar().showMessage(
            "Progresso do assistente limpo.", 5000
        )

    def _clear_assembly_plan(self) -> None:
        self._set_assembly_plan(None)

    def generate_assembly_plan(self) -> None:
        self.calculate_spokes()
        if self.last_sheet is None:
            return
        if self.assembly_plan is None:
            self.statusBar().showMessage(
                "Plano indisponível para esta montagem.", 5000
            )
        else:
            self.statusBar().showMessage(
                "Plano dos 4 conjuntos gerado.", 5000
            )

    def _selected_sim_index(self) -> int | None:
        try:
            index = int(self.sim_spoke_idx.text().strip())
            spoke_count = int(self.spokes_count_combo.currentText())
        except (ValueError, TypeError):
            return None
        return index if 0 <= index < spoke_count else None

    def _on_sim_index_changed(self, *args) -> None:
        if hasattr(self, "visualizer"):
            self.visualizer.set_selected_index(self._selected_sim_index())
        if hasattr(self, "sim_selected_info"):
            self._update_selected_spoke_info()

    def _current_truing_inputs(self) -> tuple[WheelSpec, float, float]:
        spec = self._read_spec()
        target = self._parse_float(
            self.target_tension_input, "Tensão alvo"
        )
        diameter = self._parse_float(
            self.spoke_diameter_input, "Diâmetro do raio"
        )
        return spec, target, diameter

    def _ensure_truing_state(self, force: bool = False) -> TruingState:
        """Cria ou reutiliza o estado físico compatível com os campos atuais."""

        spec, target, diameter = self._current_truing_inputs()
        count = spec.spoke_count
        if len(self.lat_offsets) != count:
            self.lat_offsets = [0.0] * count
        if len(self.rad_offsets) != count:
            self.rad_offsets = [0.0] * count

        state = self.truing_state
        needs_new = (
            force
            or state is None
            or state.spec != spec
            or abs(state.target_tension_n - target) > 1e-9
            or abs(state.spoke_diameter_mm - diameter) > 1e-9
            or len(state.lateral_mm) != count
        )
        if needs_new:
            state = TruingState(
                spec,
                target,
                diameter,
                initial_lateral_mm=self.lat_offsets,
                initial_radial_mm=self.rad_offsets,
            )
            self.truing_state = state
            self.last_suggestion = None
            if hasattr(self, "apply_suggestions_btn"):
                self.apply_suggestions_btn.setEnabled(False)
        return state

    def _refresh_truing_view(self, state: TruingState) -> None:
        self.lat_offsets = list(state.lateral_mm)
        self.rad_offsets = list(state.radial_mm)
        self.visualizer.set_wheel(
            state.spec.spoke_count,
            state.spec.crossings,
            state.spec.erd_mm,
            self.lat_offsets,
            self.rad_offsets,
        )
        self._on_sim_index_changed()

    @staticmethod
    def _truing_metrics_text(state: TruingState) -> str:
        slack = (
            "nenhum"
            if not state.slack_indices
            else ", ".join(str(index) for index in state.slack_indices)
        )
        return (
            f"Runout lateral: {_fmt(state.lateral_runout_mm, 2)} mm\n"
            f"Runout radial: {_fmt(state.radial_runout_mm, 2)} mm\n"
            f"Tensões: {_fmt(state.min_tension_n, 0)} a "
            f"{_fmt(state.max_tension_n, 0)} N\n"
            f"Raios frouxos: {slack}"
        )

    def _update_selected_spoke_info(self) -> None:
        index = self._selected_sim_index()
        if index is None:
            self.sim_selected_info.setText(
                "Índice inválido. Use um valor entre 0 e N-1."
            )
            return
        try:
            spoke_count = int(self.spokes_count_combo.currentText())
            crossings = int(self.cross_combo.currentData())
            spokes = build_spoke_table(spoke_count, crossings)
        except (ValueError, TypeError) as exc:
            self.sim_selected_info.setText(f"Erro: {exc}")
            return
        spoke = spokes[index]
        text = (
            f"Raio {index}: {spoke.side.label_pt}, "
            f"{spoke.direction.label_pt}"
        )
        state = self.truing_state
        if state is not None and len(state.geometries) == len(spokes):
            tension = state.tensions_n[index]
            status = "" if state.active[index] else " (frouxo)"
            text += f" — tensão {_fmt(tension, 0)} N{status}"
        self.sim_selected_info.setText(text)

    def _format_suggestion(self, suggestion: TruingSuggestion) -> str:
        lines = [
            "=== SUGESTÕES DE AJUSTE (modelo físico) ===",
            f"Runout atual: lateral "
            f"{_fmt(suggestion.current_lateral_runout_mm, 2)} mm; radial "
            f"{_fmt(suggestion.current_radial_runout_mm, 2)} mm",
            "",
        ]
        if suggestion.adjustments:
            lines.append("Ajustes sugeridos (positivo = apertar):")
            for position, adjustment in enumerate(
                suggestion.adjustments[:12], start=1
            ):
                turns = f"{adjustment.turns:+.2f}".replace(".", ",")
                lines.append(
                    f"  {position:2d}. raio {adjustment.index:2d} "
                    f"({adjustment.side.label_pt}, "
                    f"{adjustment.direction.label_pt}): {turns} volta(s) "
                    f"→ tensão prevista "
                    f"{_fmt(adjustment.predicted_tension_n, 0)} N"
                )
            remaining = len(suggestion.adjustments) - 12
            if remaining > 0:
                lines.append(f"  ... e mais {remaining} raio(s).")
        else:
            lines.append(
                "Nenhum ajuste acima do mínimo; a roda já está próxima do alvo."
            )

        lines.extend(
            [
                "",
                f"Runout previsto: lateral "
                f"{_fmt(suggestion.predicted_lateral_runout_mm, 2)} mm; radial "
                f"{_fmt(suggestion.predicted_radial_runout_mm, 2)} mm",
                f"Tensões previstas: "
                f"{_fmt(min(suggestion.predicted_tensions_n), 0)} a "
                f"{_fmt(max(suggestion.predicted_tensions_n), 0)} N",
            ]
        )
        if suggestion.warnings:
            lines.append("")
            lines.append("Avisos:")
            lines.extend(f"• {warning}" for warning in suggestion.warnings)
        if suggestion.adjustments:
            lines.extend(
                [
                    "",
                    "Aplique as sugestões e recalcule; o modelo é linearizado.",
                ]
            )
        return "\n".join(lines)

    def _update_view_flags(self, *args) -> None:
        if hasattr(self, "visualizer"):
            self.visualizer.set_visibility(
                self.show_left_cb.isChecked(),
                self.show_right_cb.isChecked(),
                self.show_leading_cb.isChecked(),
                self.show_trailing_cb.isChecked(),
            )

    def _ensure_sheet(self) -> BuildSheet | None:
        if self.last_sheet is None:
            self.calculate_spokes()
        return self.last_sheet

    @staticmethod
    def _with_suffix(path: str, suffix: str) -> str:
        return path if path.lower().endswith(suffix) else path + suffix

    def save_sheet_json(self) -> None:
        sheet = self._ensure_sheet()
        if sheet is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar ficha em JSON",
            "ficha_roda.json",
            "JSON (*.json)",
        )
        if not path:
            return
        path = self._with_suffix(path, ".json")
        try:
            sheet.save_json(path)
        except OSError as exc:
            QMessageBox.warning(self, "Ficha de montagem", str(exc))
            return
        self.statusBar().showMessage(f"Ficha salva em {path}", 5000)

    def save_sheet_markdown(self) -> None:
        sheet = self._ensure_sheet()
        if sheet is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar ficha em Markdown",
            "ficha_roda.md",
            "Markdown (*.md)",
        )
        if not path:
            return
        path = self._with_suffix(path, ".md")
        try:
            sheet.save_markdown(path)
        except OSError as exc:
            QMessageBox.warning(self, "Ficha de montagem", str(exc))
            return
        self.statusBar().showMessage(f"Ficha salva em {path}", 5000)

    def export_sheet_pdf(self) -> None:
        sheet = self._ensure_sheet()
        if sheet is None:
            return
        if QPrinter is None:
            QMessageBox.warning(
                self,
                "Exportar PDF",
                "QtPrintSupport não está disponível nesta instalação.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar ficha em PDF",
            "ficha_roda.pdf",
            "PDF (*.pdf)",
        )
        if not path:
            return
        path = self._with_suffix(path, ".pdf")
        try:
            self._write_pdf(sheet, path)
        except Exception as exc:  # noqa: BLE001 - erro de impressão do Qt
            QMessageBox.warning(self, "Exportar PDF", str(exc))
            return
        self.statusBar().showMessage(f"PDF gerado em {path}", 5000)

    def _write_pdf(self, sheet: BuildSheet, path: str) -> None:
        if QPrinter is None:
            raise RuntimeError("QtPrintSupport não está disponível.")
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setDocName("Ficha de montagem — Wheel Lab")
        printer.setCreator("Wheel Lab")
        document = QTextDocument()
        document.setHtml(sheet.to_html())
        document.print_(printer)

    def calculate_erd_dialog(self) -> None:
        outer, ok = QInputDialog.getDouble(
            self,
            "Calcular ERD",
            "Diâmetro externo do aro (mm):",
            622.0,
            100.0,
            1000.0,
            1,
        )
        if not ok:
            return
        drop, ok = QInputDialog.getDouble(
            self,
            "Calcular ERD",
            "Profundidade do niple abaixo da borda (mm):",
            9.0,
            0.0,
            50.0,
            1,
        )
        if not ok:
            return
        try:
            erd = erd_from_outer_diameter(outer, drop)
        except ValueError as exc:
            QMessageBox.warning(self, "ERD", str(exc))
            return
        self.erd_input.setText(f"{erd:.1f}")
        self.statusBar().showMessage(f"ERD calculado: {_fmt(erd, 1)} mm", 5000)

    @staticmethod
    def _parse_float(widget: QLineEdit, label: str) -> float:
        raw = widget.text().strip().replace(",", ".")
        if not raw:
            raise ValueError(f"{label}: preencha um valor.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{label}: informe um número válido.") from exc
        if not math.isfinite(value):
            raise ValueError(f"{label}: informe um número finito.")
        return value

    @staticmethod
    def _safe_float(widget: QLineEdit, default: float) -> float:
        try:
            value = float(widget.text().strip().replace(",", "."))
        except (ValueError, AttributeError):
            return default
        if not math.isfinite(value) or value <= 0:
            return default
        return value

    def _read_spec(self) -> WheelSpec:
        crossings = self.cross_combo.currentData()
        if crossings is None:
            raise ValueError("Selecione o número de cruzamentos.")

        locknut_text = self.locknut_input.text().strip().replace(",", ".")
        locknut_spacing = (
            self._parse_float(self.locknut_input, "Distância entre locknuts")
            if locknut_text
            else None
        )

        spec = WheelSpec(
            erd_mm=self._parse_float(self.erd_input, "ERD"),
            left_flange_diameter_mm=self._parse_float(
                self.pcd_left_input, "PCD esquerdo"
            ),
            right_flange_diameter_mm=self._parse_float(
                self.pcd_right_input, "PCD direito"
            ),
            left_flange_offset_mm=self._parse_float(
                self.flange_left_input, "Flange esquerdo"
            ),
            right_flange_offset_mm=self._parse_float(
                self.flange_right_input, "Flange direito"
            ),
            hole_diameter_mm=self._parse_float(
                self.hole_dia_input, "Diâmetro do furo"
            ),
            spoke_count=int(self.spokes_count_combo.currentText()),
            crossings=int(crossings),
            rim_offset_mm=self._parse_float(
                self.dish_input, "Dish / deslocamento do aro"
            ),
            locknut_spacing_mm=locknut_spacing,
        )
        spec.validate()
        return spec

    def calculate_spokes(self) -> None:
        try:
            spec = self._read_spec()
            target = self._parse_float(
                self.target_tension_input, "Tensão alvo"
            )
            diameter = self._parse_float(
                self.spoke_diameter_input, "Diâmetro do raio"
            )
            sheet = create_build_sheet(
                spec,
                target,
                diameter,
                components=self.current_components,
            )

            if len(self.lat_offsets) != spec.spoke_count:
                self.lat_offsets = [0.0] * spec.spoke_count
                self.rad_offsets = [0.0] * spec.spoke_count
            self.visualizer.set_wheel(
                spec.spoke_count,
                spec.crossings,
                spec.erd_mm,
                self.lat_offsets,
                self.rad_offsets,
            )
            self.visualizer.set_selected_index(self._selected_sim_index())
            self.centering_view.set_spec(spec)
            self.last_sheet = sheet
            reset_plan = (
                sheet.assembly_plan is None
                or self.assembly_plan != sheet.assembly_plan
            )
            self._set_assembly_plan(
                sheet.assembly_plan, reset=reset_plan
            )
            try:
                self.truing_state = self._ensure_truing_state(force=True)
                physical_summary = self._truing_metrics_text(
                    self.truing_state
                )
            except ValueError as exc:
                self.truing_state = None
                self.last_suggestion = None
                self.apply_suggestions_btn.setEnabled(False)
                physical_summary = f"Modelo físico indisponível: {exc}"
            self.info_text.setPlainText(
                sheet.to_summary_text()
                + "\n\n=== MODELO FÍSICO ===\n"
                + physical_summary
            )
            self.sheet_preview.setMarkdown(sheet.to_markdown())
            self._on_sim_index_changed()
            self.statusBar().showMessage("Cálculo concluído.", 5000)
        except ValueError as exc:
            self.last_sheet = None
            self.truing_state = None
            self.last_suggestion = None
            if hasattr(self, "apply_suggestions_btn"):
                self.apply_suggestions_btn.setEnabled(False)
            self._on_sim_index_changed()
            self.info_text.setPlainText(f"Erro: {exc}")
            self.sheet_preview.setPlainText(
                "Corrija os dados e calcule os raios para gerar a ficha."
            )
            self._clear_assembly_plan()
            self.statusBar().showMessage(
                "Corrija os dados e tente novamente.", 5000
            )

    def reset_sim(self) -> None:
        try:
            spec, target, diameter = self._current_truing_inputs()
            state = TruingState(
                spec,
                target,
                diameter,
                initial_lateral_mm=[0.0] * spec.spoke_count,
                initial_radial_mm=[0.0] * spec.spoke_count,
            )
            self.truing_state = state
            self.last_suggestion = None
            self.apply_suggestions_btn.setEnabled(False)
            self._refresh_truing_view(state)
            left_target = next(
                geometry.initial_tension_n
                for geometry in state.geometries
                if geometry.side is Side.LEFT
            )
            right_target = next(
                geometry.initial_tension_n
                for geometry in state.geometries
                if geometry.side is Side.RIGHT
            )
            self.info_text.setPlainText(
                f"Simulador físico resetado: {spec.spoke_count} raios, "
                f"{spec.crossings}x, sem desvios.\n"
                f"Tensões alvo: esquerda {_fmt(left_target, 0)} N; "
                f"direita {_fmt(right_target, 0)} N.\n"
                "Use 'Carregar exemplo de empeno' ou aplique um ajuste."
            )
        except (ValueError, TypeError) as exc:
            self.truing_state = None
            self.last_suggestion = None
            if hasattr(self, "apply_suggestions_btn"):
                self.apply_suggestions_btn.setEnabled(False)
            self.info_text.setPlainText(f"Erro: {exc}")

    def load_example(self) -> None:
        try:
            spec, target, diameter = self._current_truing_inputs()
            count = spec.spoke_count
            lateral = [
                0.6 * math.sin(2.0 * math.pi * index / count)
                for index in range(count)
            ]
            radial = [
                0.3 * math.cos(4.0 * math.pi * index / count)
                for index in range(count)
            ]
            state = TruingState(
                spec,
                target,
                diameter,
                initial_lateral_mm=lateral,
                initial_radial_mm=radial,
            )
            self.truing_state = state
            self.last_suggestion = None
            self.apply_suggestions_btn.setEnabled(False)
            self._refresh_truing_view(state)
            self.info_text.setPlainText(
                "Exemplo de runout carregado (entrada didática; o solver "
                "calcula a resposta física):\n"
                "• Desvio lateral de ±0,6 mm (seno de uma volta).\n"
                "• Desvio radial de ±0,3 mm (cosseno de duas voltas).\n"
                f"• Runout lateral: {_fmt(state.lateral_runout_mm, 2)} mm; "
                f"radial: {_fmt(state.radial_runout_mm, 2)} mm.\n"
                "• Deslocamentos exagerados 20× no desenho.\n\n"
                "Use 'Sugerir ajustes' para calcular um passo de truing."
            )
        except (ValueError, TypeError) as exc:
            self.info_text.setPlainText(f"Erro: {exc}")

    def apply_sim_adjustment(self) -> None:
        try:
            state = self._ensure_truing_state()
            index = int(self.sim_spoke_idx.text().strip())
            if not 0 <= index < len(state.geometries):
                raise ValueError(
                    f"O índice deve estar entre 0 e "
                    f"{len(state.geometries) - 1}."
                )

            turns = self.sim_turn_val.currentData()
            if turns is None:
                raise ValueError("Selecione um ajuste de niple.")
            turns_value = float(turns)
            delta_mm = turns_to_mm(turns_value)
            geometry = state.geometries[index]
            tension_before = state.tensions_n[index]
            result = state.apply_turns({index: turns_value})

            self.last_suggestion = None
            self.apply_suggestions_btn.setEnabled(False)
            self._refresh_truing_view(state)

            tension_after = result.tensions_n[index]
            slack_text = (
                "nenhum"
                if not result.slack_indices
                else ", ".join(str(value) for value in result.slack_indices)
            )
            turns_text = f"{turns_value:+.2f}".replace(".", ",")
            delta_text = f"{delta_mm:+.3f}".replace(".", ",")
            self.info_text.setPlainText(
                f"Ajuste físico aplicado no raio {index} "
                f"({geometry.side.label_pt}, "
                f"{geometry.direction.label_pt}):\n"
                f"• {turns_text} volta(s) = {delta_text} mm\n"
                f"• Runout lateral: "
                f"{_fmt(result.lateral_runout_before_mm, 2)} → "
                f"{_fmt(result.lateral_runout_mm, 2)} mm\n"
                f"• Runout radial: "
                f"{_fmt(result.radial_runout_before_mm, 2)} → "
                f"{_fmt(result.radial_runout_mm, 2)} mm\n"
                f"• Tensão no raio: {_fmt(tension_before, 0)} → "
                f"{_fmt(tension_after, 0)} N\n"
                f"• Tensões na roda: {_fmt(result.min_tension_n, 0)} a "
                f"{_fmt(result.max_tension_n, 0)} N\n"
                f"• Raios frouxos: {slack_text}\n"
                f"• Iterações do equilíbrio: {result.iterations}\n\n"
                "Use 'Sugerir ajustes' para o próximo passo."
            )
        except (ValueError, IndexError, TypeError) as exc:
            self.info_text.setPlainText(f"Erro: {exc}")

    def suggest_sim_adjustments(self) -> None:
        try:
            state = self._ensure_truing_state()
            suggestion = state.suggest_adjustments(
                max_turns=0.75,
                min_turns=0.05,
                lateral_weight=1.0,
                radial_weight=0.5,
                regularization=1e-4,
            )
            self.last_suggestion = suggestion
            self.apply_suggestions_btn.setEnabled(bool(suggestion.adjustments))
            self.info_text.setPlainText(self._format_suggestion(suggestion))
        except (ValueError, TypeError) as exc:
            self.last_suggestion = None
            self.apply_suggestions_btn.setEnabled(False)
            self.info_text.setPlainText(f"Erro: {exc}")

    def apply_sim_suggestions(self) -> None:
        try:
            state = self._ensure_truing_state()
            suggestion = self.last_suggestion
            if suggestion is None or not suggestion.adjustments:
                self.info_text.setPlainText(
                    "Nenhuma sugestão pendente. Use 'Sugerir ajustes' "
                    "primeiro."
                )
                return
            turns_map = {
                adjustment.index: adjustment.turns
                for adjustment in suggestion.adjustments
            }
            result = state.apply_turns(turns_map)
            self.last_suggestion = None
            self.apply_suggestions_btn.setEnabled(False)
            self._refresh_truing_view(state)
            slack_text = (
                "nenhum"
                if not result.slack_indices
                else ", ".join(str(value) for value in result.slack_indices)
            )
            self.info_text.setPlainText(
                f"Sugestões aplicadas: {len(turns_map)} raio(s).\n"
                f"• Runout lateral: "
                f"{_fmt(result.lateral_runout_before_mm, 2)} → "
                f"{_fmt(result.lateral_runout_mm, 2)} mm\n"
                f"• Runout radial: "
                f"{_fmt(result.radial_runout_before_mm, 2)} → "
                f"{_fmt(result.radial_runout_mm, 2)} mm\n"
                f"• Tensões na roda: {_fmt(result.min_tension_n, 0)} a "
                f"{_fmt(result.max_tension_n, 0)} N\n"
                f"• Raios frouxos: {slack_text}\n\n"
                "Use 'Sugerir ajustes' novamente para o próximo passo."
            )
        except (ValueError, IndexError, TypeError) as exc:
            self.info_text.setPlainText(f"Erro: {exc}")

    def _on_spoke_count_changed(self, text: str) -> None:
        try:
            spoke_count = int(text)
        except ValueError:
            return
        maximum = max_crossings(spoke_count)
        current = self.cross_combo.currentData()
        if current is not None and int(current) > maximum:
            target_index = self.cross_combo.findData(maximum)
            if target_index >= 0:
                self.cross_combo.setCurrentIndex(target_index)
                self.statusBar().showMessage(
                    f"{spoke_count} raios: máximo {maximum}x; padrão ajustado.",
                    5000,
                )
        self._clear_assembly_plan()
        self.reset_sim()

    def _on_cross_changed(self) -> None:
        try:
            spoke_count = int(self.spokes_count_combo.currentText())
            crossings = int(self.cross_combo.currentData())
        except (ValueError, TypeError):
            return
        if not is_valid_cross_pattern(spoke_count, crossings):
            self.statusBar().showMessage(
                f"{crossings}x inválido para {spoke_count} raios; "
                f"o máximo é {max_crossings(spoke_count)}x.",
                5000,
            )
        else:
            self.statusBar().clearMessage()
        self._clear_assembly_plan()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Wheel Lab")
    window = WheelCalculatorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
