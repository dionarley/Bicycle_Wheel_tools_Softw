#!/usr/bin/env python3
import sys
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QComboBox, QPushButton, QLabel,
    QGroupBox, QTabWidget, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen


class WheelVisualizer(QWidget):
    """Widget customizado para renderizar a geometria da roda e os desvios."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.num_spokes = 32
        self.lateral_offsets = np.zeros(32)
        self.radial_offsets = np.zeros(32)
        self.setMinimumSize(350, 350)

    def update_offsets(self, num_spokes, lateral, radial):
        self.num_spokes = num_spokes
        self.lateral_offsets = lateral
        self.radial_offsets = radial
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2
        base_radius = min(width, height) * 0.38

        # Desenhar Aro Base (Preto)
        painter.setPen(QPen(QColor(100, 100, 100), 2, Qt.DashLine))
        painter.drawEllipse(center_x - base_radius, center_y - base_radius, base_radius * 2, base_radius * 2)

        # Desenhar Cubo Central
        hub_radius = base_radius * 0.15
        painter.setPen(QPen(QColor(60, 60, 60), 2))
        painter.setBrush(QColor(200, 200, 200))
        painter.drawEllipse(center_x - hub_radius, center_y - hub_radius, hub_radius * 2, hub_radius * 2)

        # Desenhar Raios e Perfil Deformado
        angles = np.linspace(0, 2 * np.pi, self.num_spokes, endpoint=False)
        
        rim_points = []
        for i, angle in enumerate(angles):
            # Aplica os desvios radiais no raio visual
            r = base_radius + self.radial_offsets[i] * 5.0  # Escala visual
            rx = center_x + r * np.cos(angle)
            ry = center_y + r * np.sin(angle)
            rim_points.append((rx, ry))

            # Cor do raio baseada no desvio lateral (Vermelho = Esquerda, Azul = Direita)
            lat = self.lateral_offsets[i]
            if abs(lat) < 0.1:
                spoke_color = QColor(150, 150, 150)
            elif lat > 0:
                spoke_color = QColor(220, 50, 50)
            else:
                spoke_color = QColor(50, 100, 220)

            painter.setPen(QPen(spoke_color, 1.5))
            
            # Ponto de saída do cubo com compensação
            hx = center_x + hub_radius * np.cos(angle + 0.1)
            hy = center_y + hub_radius * np.sin(angle + 0.1)
            painter.drawLine(hx, hy, rx, ry)

        # Desenhar Perfil do Aro Atual
        painter.setPen(QPen(QColor(20, 160, 80), 2.5))
        for i in range(self.num_spokes):
            p1 = rim_points[i]
            p2 = rim_points[(i + 1) % self.num_spokes]
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])


class WheelCalculatorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calculador & Alinhador de Rodas de Bicicleta")
        self.resize(900, 650)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Painel Esquerdo: Tabs de Entrada/Controle
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # Painel Direito: Visualizador Gráfico Qt
        visualizer_group = QGroupBox("Visualizador de Deformação e Tensão")
        viz_layout = QVBoxLayout(visualizer_group)
        self.visualizer = WheelVisualizer()
        viz_layout.addWidget(self.visualizer)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        viz_layout.addWidget(self.info_text)

        main_layout.addWidget(visualizer_group, stretch=1)

        # Construção das Tabs
        self.init_calculator_tab()
        self.init_truing_sim_tab()

    def init_calculator_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        
        self.erd_input = QLineEdit("600.0")
        self.pcd_left_input = QLineEdit("45.0")
        self.pcd_right_input = QLineEdit("45.0")
        self.flange_left_input = QLineEdit("35.0")
        self.flange_right_input = QLineEdit("19.0")
        self.hole_dia_input = QLineEdit("2.6")

        self.spokes_count_combo = QComboBox()
        self.spokes_count_combo.addItems(["28", "32", "36"])
        self.spokes_count_combo.setCurrentText("32")

        self.cross_combo = QComboBox()
        self.cross_combo.addItems(["0 (Radial)", "2", "3", "4"])
        self.cross_combo.setCurrentText("3")

        form.addRow("ERD do Aro (mm):", self.erd_input)
        form.addRow("Diâmetro Flange Esquerda (PCD mm):", self.pcd_left_input)
        form.addRow("Diâmetro Flange Direita (PCD mm):", self.pcd_right_input)
        form.addRow("Dist. Flange Esq. ao Centro (mm):", self.flange_left_input)
        form.addRow("Dist. Flange Dir. ao Centro (mm):", self.flange_right_input)
        form.addRow("Diâmetro Furo Flange (mm):", self.hole_dia_input)
        form.addRow("Número de Raios:", self.spokes_count_combo)
        form.addRow("Cruzamentos:", self.cross_combo)

        layout.addLayout(form)

        calc_btn = QPushButton("Calcular Comprimento dos Raios")
        calc_btn.clicked.connect(self.calculate_spokes)
        layout.addWidget(calc_btn)
        layout.addStretch()

        self.tabs.addTab(tab, "Cálculo de Raios")

    def init_truing_sim_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        self.sim_spoke_idx = QLineEdit("0")
        self.sim_turn_val = QComboBox()
        self.sim_turn_val.addItems(["+1/4 volta (Apertar)", "-1/4 volta (Soltar)", "+1/2 volta", "-1/2 volta"])

        form.addRow("Índice do Raio (0 a N-1):", self.sim_spoke_idx)
        form.addRow("Ajuste no Niple:", self.sim_turn_val)

        layout.addLayout(form)

        apply_btn = QPushButton("Aplicar Ajuste")
        apply_btn.clicked.connect(self.apply_sim_adjustment)
        layout.addWidget(apply_btn)

        reset_btn = QPushButton("Resetar Desvios da Roda")
        reset_btn.clicked.connect(self.reset_sim)
        layout.addWidget(reset_btn)

        layout.addStretch()
        self.tabs.addTab(tab, "Simulador de Alinhamento")

        # Inicializa estado de erro simulado
        self.reset_sim()

    def calculate_spoke_side(self, erd, d_flange, w_flange, d_hole, num_spokes, crossings):
        if crossings == 0:
            angle = 0.0
        else:
            angle = (360.0 * crossings) / (num_spokes / 2.0)
        
        rad_angle = np.radians(angle)
        
        a = (d_flange / 2.0) * np.sin(rad_angle)
        b = (erd / 2.0) - ((d_flange / 2.0) * np.cos(rad_angle))
        c = w_flange

        length = np.sqrt(a**2 + b**2 + c**2) - (d_hole / 2.0)
        return length

    def calculate_spokes(self):
        try:
            erd = float(self.erd_input.text())
            pcd_l = float(self.pcd_left_input.text())
            pcd_r = float(self.pcd_right_input.text())
            wl = float(self.flange_left_input.text())
            wr = float(self.flange_right_input.text())
            d_hole = float(self.hole_dia_input.text())
            n_spokes = int(self.spokes_count_combo.currentText())
            cross = int(self.cross_combo.currentText().split()[0])

            len_left = self.calculate_spoke_side(erd, pcd_l, wl, d_hole, n_spokes, cross)
            len_right = self.calculate_spoke_side(erd, pcd_r, wr, d_hole, n_spokes, cross)

            res = (
                f"=== RESULTADOS DO CÁLCULO ===\n\n"
                f"• Raio Lado Esquerdo: {len_left:.2f} mm (Comprar: {np.floor(len_left):.0f} ou {np.round(len_left):.0f} mm)\n"
                f"• Raio Lado Direito:  {len_right:.2f} mm (Comprar: {np.floor(len_right):.0f} ou {np.round(len_right):.0f} mm)\n\n"
                f"Nota: Considerado encurtamento do aro e deformação sob tensão (~0.5 a 1.0mm)."
            )
            self.info_text.setText(res)
        except ValueError:
            self.info_text.setText("Erro: Certifique-se de preencher todos os campos numéricos corretamente.")

    def reset_sim(self):
        n = int(self.spokes_count_combo.currentText())
        # Cria um empenamento lateral e radial simulado inicial
        angles = np.linspace(0, 2*np.pi, n, endpoint=False)
        self.lat_offsets = 1.5 * np.sin(angles)
        self.rad_offsets = 0.8 * np.cos(2 * angles)
        self.visualizer.update_offsets(n, self.lat_offsets, self.rad_offsets)
        self.info_text.setText("Simulador resetado com deformação inicial de teste.")

    def apply_sim_adjustment(self):
        try:
            idx = int(self.sim_spoke_idx.text())
            n = int(self.spokes_count_combo.currentText())
            if idx < 0 or idx >= n:
                self.info_text.setText(f"Erro: O índice deve ser entre 0 e {n-1}.")
                return

            turn = self.sim_turn_val.currentText()
            factor = 0.25 if "1/4" in turn else 0.5
            if "-" in turn:
                factor = -factor

            # Lado do raio: Pares = Esquerda, Ímpares = Direita
            side = 1 if (idx % 2 == 0) else -1

            # Ajuste afeta o ponto do raio e suavemente os vizinhos
            self.lat_offsets[idx] += factor * side
            self.rad_offsets[idx] -= abs(factor) * 0.5

            self.visualizer.update_offsets(n, self.lat_offsets, self.rad_offsets)
            self.info_text.setText(
                f"Ajuste aplicado no raio {idx}:\n"
                f"• Desvio Lateral Atual: {self.lat_offsets[idx]:.2f} mm\n"
                f"• Desvio Radial Atual:  {self.rad_offsets[idx]:.2f} mm"
            )
        except ValueError:
            self.info_text.setText("Erro: Índice do raio inválido.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WheelCalculatorApp()
    window.show()
    sys.exit(app.exec())
