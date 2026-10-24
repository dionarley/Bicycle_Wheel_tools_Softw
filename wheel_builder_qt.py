#!/usr/bin/env python3
"""Wheel Lab — calculador e alinhador de rodas de bicicleta.

Fase 1: calculadora completa, visualizador de montagem, dish/centralização e
ficha de montagem (JSON, Markdown e PDF). O simulador de alinhamento ainda é
didático; o solver físico (aro + raios) entra na Fase 2.
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
    BuildSheet,
    Side,
    SpokeDirection,
    WheelSpec,
    build_spoke_table,
    create_build_sheet,
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

            # Raios. O selecionado é desenhado por último, para ficar no topo.
            hub_radius = base_radius * 0.18
            selected = self.selected_index
            for index, spoke in enumerate(self.spokes):
                if not self._spoke_visible(spoke) or index == selected:
                    continue
                self._draw_spoke(
                    painter, index, spoke, rim_points, center, hub_radius
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
    ) -> None:
        hub_angle = math.radians(spoke.hub_angle_deg)
        hub_point = QPointF(
            center.x() + hub_radius * math.cos(hub_angle),
            center.y() + hub_radius * math.sin(hub_angle),
        )
        rim_point = rim_points[index]

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
            "Aro: azul = desvio p/ esquerda, vermelho = p/ direita\n"
            f"Deslocamentos exagerados {EXAGGERATION:.0f}×"
        )
        painter.setPen(QColor(70, 70, 70))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(
            QRectF(8, self.height() - 94, self.width() - 16, 86),
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
        self.sim_spoke_idx.textChanged.connect(self._on_sim_index_changed)

        apply_btn = QPushButton("Aplicar ajuste")
        apply_btn.clicked.connect(self.apply_sim_adjustment)
        layout.addWidget(apply_btn)

        reset_btn = QPushButton("Resetar desvios da roda")
        reset_btn.clicked.connect(self.reset_sim)
        layout.addWidget(reset_btn)

        example_btn = QPushButton("Carregar exemplo de empeno")
        example_btn.clicked.connect(self.load_example)
        layout.addWidget(example_btn)

        note = QLabel(
            "Modelo didático. O ajuste de niple move o raio e os vizinhos com "
            "um fator fixo; ainda não há equilíbrio elástico do aro nem tensão. "
            "O solver físico entra na Fase 2."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)
        layout.addStretch()

        self.tabs.addTab(tab, "Simulador de alinhamento")

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
            sheet = create_build_sheet(spec, target, diameter)

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
            self.info_text.setPlainText(sheet.to_summary_text())
            self.sheet_preview.setMarkdown(sheet.to_markdown())
            self.statusBar().showMessage("Cálculo concluído.", 5000)
        except ValueError as exc:
            self.last_sheet = None
            self.info_text.setPlainText(f"Erro: {exc}")
            self.sheet_preview.setPlainText(
                "Corrija os dados e calcule os raios para gerar a ficha."
            )
            self.statusBar().showMessage(
                "Corrija os dados e tente novamente.", 5000
            )

    def reset_sim(self) -> None:
        try:
            spoke_count = int(self.spokes_count_combo.currentText())
            crossings = int(self.cross_combo.currentData())
            build_spoke_table(spoke_count, crossings)
            erd = self._safe_float(self.erd_input, 600.0)

            self.lat_offsets = [0.0] * spoke_count
            self.rad_offsets = [0.0] * spoke_count
            self.visualizer.set_wheel(
                spoke_count,
                crossings,
                erd,
                self.lat_offsets,
                self.rad_offsets,
            )
            self._on_sim_index_changed()
            self.info_text.setPlainText(
                f"Simulador resetado: {spoke_count} raios, {crossings}x, "
                "sem desvios.\n"
                "Use 'Carregar exemplo de empeno' para ver um caso didático "
                "ou aplique um ajuste de niple."
            )
        except (ValueError, TypeError) as exc:
            self.info_text.setPlainText(f"Erro: {exc}")

    def load_example(self) -> None:
        try:
            spoke_count = int(self.spokes_count_combo.currentText())
            crossings = int(self.cross_combo.currentData())
            build_spoke_table(spoke_count, crossings)
            erd = self._safe_float(self.erd_input, 600.0)

            self.lat_offsets = [
                1.5 * math.sin(2.0 * math.pi * index / spoke_count)
                for index in range(spoke_count)
            ]
            self.rad_offsets = [
                0.8 * math.cos(4.0 * math.pi * index / spoke_count)
                for index in range(spoke_count)
            ]
            self.visualizer.set_wheel(
                spoke_count,
                crossings,
                erd,
                self.lat_offsets,
                self.rad_offsets,
            )
            self._on_sim_index_changed()
            self.info_text.setPlainText(
                "Exemplo didático carregado:\n"
                "• Desvio lateral de ±1,5 mm (seno de uma volta).\n"
                "• Desvio radial de ±0,8 mm (cosseno de duas voltas).\n"
                "• Deslocamentos exagerados 20× no desenho.\n\n"
                "Isto não é um resultado físico; serve para testar o visualizador."
            )
        except (ValueError, TypeError) as exc:
            self.info_text.setPlainText(f"Erro: {exc}")

    def apply_sim_adjustment(self) -> None:
        try:
            spoke_count = int(self.spokes_count_combo.currentText())
            crossings = int(self.cross_combo.currentData())
            spokes = build_spoke_table(spoke_count, crossings)

            index = int(self.sim_spoke_idx.text().strip())
            if not 0 <= index < spoke_count:
                raise ValueError(
                    f"O índice deve estar entre 0 e {spoke_count - 1}."
                )

            turns = self.sim_turn_val.currentData()
            if turns is None:
                raise ValueError("Selecione um ajuste de niple.")
            delta_mm = turns_to_mm(float(turns))

            if len(self.lat_offsets) != spoke_count:
                self.lat_offsets = [0.0] * spoke_count
            if len(self.rad_offsets) != spoke_count:
                self.rad_offsets = [0.0] * spoke_count

            spoke = spokes[index]
            side_sign = spoke.side.sign

            # Modelo didático: apertar puxa o aro para dentro e para o lado
            # do flange; os vizinhos recebem uma fração do movimento.
            self.rad_offsets[index] -= delta_mm
            self.lat_offsets[index] += side_sign * delta_mm * 0.35
            for neighbor in ((index - 1) % spoke_count, (index + 1) % spoke_count):
                self.rad_offsets[neighbor] -= 0.15 * delta_mm
                self.lat_offsets[neighbor] += side_sign * 0.10 * delta_mm

            erd = self._safe_float(self.erd_input, 600.0)
            self.visualizer.set_wheel(
                spoke_count,
                crossings,
                erd,
                self.lat_offsets,
                self.rad_offsets,
            )
            self._on_sim_index_changed()

            lateral_max = max(abs(value) for value in self.lat_offsets)
            radial_range = max(self.rad_offsets) - min(self.rad_offsets)
            self.info_text.setPlainText(
                f"Ajuste aplicado no raio {index} "
                f"({spoke.side.label_pt}, {spoke.direction.label_pt}):\n"
                f"• {float(turns):+.2f} volta(s) = {delta_mm:+.3f} mm\n"
                f"• Desvio lateral máximo: {_fmt(lateral_max, 2)} mm\n"
                f"• Faixa radial (máx - mín): {_fmt(radial_range, 2)} mm\n\n"
                "Modelo didático: o aro ainda não é resolvido por equilíbrio "
                "elástico e a tensão não é calculada."
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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Wheel Lab")
    window = WheelCalculatorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
