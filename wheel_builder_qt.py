#!/usr/bin/env python3
"""Wheel Lab — calculador e alinhador de rodas de bicicleta.

Fase 0: núcleo de cálculo testável + UI PySide6 sem os crashes do protótipo.
O simulador de alinhamento ainda é didático; o solver físico (aro + raios)
entra na Fase 2.
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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

from wheel_lab.core import (
    Side,
    SpokeDirection,
    WheelSpec,
    build_spoke_table,
    calculate_spoke_lengths,
    erd_from_outer_diameter,
    is_valid_cross_pattern,
    lateral_tension_ratio,
    linear_density_kg_per_m,
    max_crossings,
    rim_compression_from_sides,
    spoke_elongation_mm,
    target_tensions,
    tone_frequency_hz,
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

        self.update()

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

            # Raios.
            hub_radius = base_radius * 0.18
            for index, spoke in enumerate(self.spokes):
                hub_angle = math.radians(spoke.hub_angle_deg)
                hub_point = QPointF(
                    center.x() + hub_radius * math.cos(hub_angle),
                    center.y() + hub_radius * math.sin(hub_angle),
                )
                color = (
                    QColor(55, 105, 220)
                    if spoke.side is Side.LEFT
                    else QColor(220, 65, 60)
                )
                if spoke.direction is SpokeDirection.TRAILING:
                    color = color.darker(130)
                width = 2.2 if spoke.is_leading else 1.3
                painter.setPen(
                    QPen(
                        color,
                        width,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.drawLine(hub_point, rim_points[index])

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

    def _draw_legend(self, painter: QPainter) -> None:
        legend = (
            "Raios: azul = esquerda, vermelho = direita\n"
            "Claro = leading, escuro = trailing\n"
            "Aro: azul = desvio p/ esquerda, vermelho = p/ direita\n"
            f"Deslocamentos exagerados {EXAGGERATION:.0f}×"
        )
        painter.setPen(QColor(70, 70, 70))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(
            QRectF(8, self.height() - 78, self.width() - 16, 70),
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


class WheelCalculatorApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wheel Lab — Calculador e Alinhador de Rodas")
        self.resize(1050, 720)

        self.lat_offsets: list[float] = []
        self.rad_offsets: list[float] = []

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
        splitter.addWidget(self.tabs)

        visualizer_group = QGroupBox("Visualizador de montagem e desvios")
        viz_layout = QVBoxLayout(visualizer_group)

        viz_splitter = QSplitter(Qt.Orientation.Vertical)
        self.visualizer = WheelVisualizer()
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumHeight(170)
        self.info_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        viz_splitter.addWidget(self.visualizer)
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
            "Distância do plano do aro ao flange esquerdo. Em uma roda "
            "centralizada, equivale à distância do centro do cubo ao flange."
        )
        self.flange_right_input.setToolTip(
            "Distância do plano do aro ao flange direito. Em uma roda "
            "centralizada, equivale à distância do centro do cubo ao flange."
        )
        self.hole_dia_input.setToolTip(
            "Diâmetro do furo do flange (comum 2,6 mm). O comprimento do "
            "raio é reduzido em metade desse valor."
        )

        hub_form.addRow("PCD esquerdo (mm):", self.pcd_left_input)
        hub_form.addRow("PCD direito (mm):", self.pcd_right_input)
        hub_form.addRow("Offset flange esq. (mm):", self.flange_left_input)
        hub_form.addRow("Offset flange dir. (mm):", self.flange_right_input)
        hub_form.addRow("Diâmetro do furo (mm):", self.hole_dia_input)
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
            "plano do aro ao flange."
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
            "Fase 0: modelo didático. O ajuste de niple move o raio e os "
            "vizinhos com um fator fixo; ainda não há equilíbrio elástico do "
            "aro nem tensão. O solver físico entra na Fase 2."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)
        layout.addStretch()

        self.tabs.addTab(tab, "Simulador de alinhamento")

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
        spec = WheelSpec(
            erd_mm=self._parse_float(self.erd_input, "ERD"),
            left_flange_diameter_mm=self._parse_float(
                self.pcd_left_input, "PCD esquerdo"
            ),
            right_flange_diameter_mm=self._parse_float(
                self.pcd_right_input, "PCD direito"
            ),
            left_flange_offset_mm=self._parse_float(
                self.flange_left_input, "Offset esquerdo"
            ),
            right_flange_offset_mm=self._parse_float(
                self.flange_right_input, "Offset direito"
            ),
            hole_diameter_mm=self._parse_float(
                self.hole_dia_input, "Diâmetro do furo"
            ),
            spoke_count=int(self.spokes_count_combo.currentText()),
            crossings=int(crossings),
        )
        spec.validate()
        return spec

    def calculate_spokes(self) -> None:
        try:
            spec = self._read_spec()
            result = calculate_spoke_lengths(spec)

            target = self._parse_float(
                self.target_tension_input, "Tensão alvo"
            )
            diameter = self._parse_float(
                self.spoke_diameter_input, "Diâmetro do raio"
            )
            if target <= 0:
                raise ValueError("A tensão alvo deve ser positiva.")
            if diameter <= 0:
                raise ValueError("O diâmetro do raio deve ser positivo.")

            ratio = lateral_tension_ratio(
                spec.left_flange_offset_mm,
                spec.right_flange_offset_mm,
                result.left_mm,
                result.right_mm,
            )
            if ratio < 1.0:
                tighter = Side.RIGHT
            elif ratio > 1.0:
                tighter = Side.LEFT
            else:
                tighter = Side.RIGHT

            tensions = target_tensions(target, ratio, tighter)
            compression = rim_compression_from_sides(
                tensions[Side.LEFT],
                tensions[Side.RIGHT],
                spec.spoke_count,
            )
            mu = linear_density_kg_per_m(diameter)
            elongation_left = spoke_elongation_mm(
                tensions[Side.LEFT], result.left_mm, diameter
            )
            elongation_right = spoke_elongation_mm(
                tensions[Side.RIGHT], result.right_mm, diameter
            )
            tone_left = tone_frequency_hz(
                tensions[Side.LEFT], result.left_mm, mu
            )
            tone_right = tone_frequency_hz(
                tensions[Side.RIGHT], result.right_mm, mu
            )

            tighter_label = "direito" if tighter is Side.RIGHT else "esquerdo"
            lines = [
                "=== COMPRIMENTO DOS RAIOS ===",
                f"Ângulo de cruzamento (T): {_fmt(result.angle_deg, 1)}°",
                (
                    f"Esquerdo: {_fmt(result.left_mm, 2)} mm "
                    f"→ comprar {result.left_purchase_mm} mm"
                ),
                (
                    f"Direito:  {_fmt(result.right_mm, 2)} mm "
                    f"→ comprar {result.right_purchase_mm} mm"
                ),
                (
                    "Diferença L-R: "
                    f"{_fmt(abs(result.left_mm - result.right_mm), 2)} mm"
                ),
                "",
                "=== TENSÃO (estimativa) ===",
                (
                    f"Razão T_esq / T_dir: {_fmt(ratio, 3)} "
                    f"(lado {tighter_label} mais tenso)"
                ),
                (
                    f"Alvo esquerdo: {_fmt(tensions[Side.LEFT], 0)} N | "
                    f"direito: {_fmt(tensions[Side.RIGHT], 0)} N "
                    f"(lado mais tenso: {tighter_label})"
                ),
                f"Compressão no aro: {_fmt(compression, 0)} N",
                (
                    f"Alongamento a essa tensão: esq. "
                    f"{_fmt(elongation_left, 2)} mm | dir. "
                    f"{_fmt(elongation_right, 2)} mm"
                ),
                (
                    f"Tom aproximado: esq. {_fmt(tone_left, 0)} Hz | "
                    f"dir. {_fmt(tone_right, 0)} Hz"
                ),
                "",
                "Notas:",
                "• Comprimento arredondado para baixo (raio estica, aro encolhe).",
                "• Tom é aproximado; use tensiômetro para tensão absoluta.",
                "• Offsets medidos do plano do aro ao flange.",
            ]
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
            self.info_text.setPlainText("\n".join(lines))
            self.statusBar().showMessage("Cálculo concluído.", 5000)
        except ValueError as exc:
            self.info_text.setPlainText(f"Erro: {exc}")
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

            lateral_max = max(abs(value) for value in self.lat_offsets)
            radial_range = max(self.rad_offsets) - min(self.rad_offsets)
            self.info_text.setPlainText(
                f"Ajuste aplicado no raio {index} "
                f"({spoke.side.label_pt}, {spoke.direction.label_pt}):\n"
                f"• {float(turns):+.2f} volta(s) = {delta_mm:+.3f} mm\n"
                f"• Desvio lateral máximo: {_fmt(lateral_max, 2)} mm\n"
                f"• Faixa radial (máx - mín): {_fmt(radial_range, 2)} mm\n\n"
                "Modelo didático da Fase 0: o aro ainda não é resolvido por "
                "equilíbrio elástico e a tensão não é calculada."
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
