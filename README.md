# Wheel Lab

Ferramentas de cálculo, montagem e alinhamento de rodas de bicicleta, baseadas
em *The Bicycle Wheel* (Jobst Brandt, 3ª ed.).

O projeto começou como um protótipo de calculadora em PySide6. A Fase 0 separa
a engenharia da interface, corrige os crashes do protótipo e cria uma base
testável para o simulador físico de truing.

## Estado atual (Fase 0)

- **Núcleo de cálculo puro em Python** (`wheel_lab/core/`), sem Qt e sem NumPy.
- **Comprimento de raio** pela equação 1 de Brandt, por lado, com arredondamento
  sempre para baixo.
- **Validação de padrão**: `T = 720·X/N ≤ 90°`; máximo de cruzamentos `N/8`.
- **ERD** a partir do diâmetro externo e da profundidade do niple.
- **Tensão**: razão esquerda/direita pelo equilíbrio lateral, tensões alvo,
  compressão do aro, alongamento do raio e tom aproximado.
- **Constantes de montagem**: passo de rosca de 56 TPI (≈ 0,4536 mm/volta;
  1/4 de volta ≈ 0,1134 mm).
- **Visualizador** esquemático com lados, leading/trailing, válvula, perfil
  deformado e cores para desvio lateral.
- **Simulador didático** de ajuste de niple, sem crashes ao trocar 32 → 36
  raios. O solver físico do aro entra na Fase 2.
- **Testes** de engenharia e smoke tests da UI em modo offscreen.

O simulador atual **não** calcula equilíbrio elástico nem tensão. Ele move o
raio selecionado e os vizinhos com fatores fixos; é apenas uma demonstração
visual até a Fase 2.

## Instalação

Requisitos: Python 3.10+ e Linux/Windows/macOS com Qt.

```bash
./install.sh
./run.sh
```

Ou manualmente:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python wheel_builder_qt.py
```

Em NixOS, o wheel do PySide6 não traz `libGL`, `libxkbcommon` e outras
bibliotecas do sistema. O `run.sh` detecta o Nix e usa o `shell.nix`, que
aponta o `LD_LIBRARY_PATH` para elas. Se preferir rodar direto:

```bash
nix-shell --run ".venv/bin/python wheel_builder_qt.py"
```

O script antigo `install_numpy.sh` foi mantido como atalho para `install.sh`.

## Testes

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Os testes da UI usam `QT_QPA_PLATFORM=offscreen` (definido em
`tests/conftest.py`), então rodam sem display.

## Estrutura

```text
wheel_builder_qt.py       # janela PySide6 (entry point)
run.sh                    # executa a UI (com Nix quando disponível)
shell.nix                 # bibliotecas gráficas para NixOS
wheel_lab/
  __init__.py
  core/
    models.py             # dataclasses e validações
    geometry.py           # T, ERD, máximo de cruzamentos
    spoke_length.py       # equação 1 e arredondamento
    lacing.py             # tabela de raios para desenho
    tension.py            # razão L/R, alvo, alongamento, tom, pneu
    units.py              # TPI, voltas ↔ mm
tests/
  test_spoke_length.py
  test_geometry.py
  test_tension.py
  test_lacing.py
  test_units.py
  test_ui_smoke.py
```

## Fórmulas principais

Comprimento de raio (Brandt, eq. 1):

```text
L = sqrt(A² + B² + C²) - S/2
A = (d/2)·sin(T)
B = D/2 - (d/2)·cos(T)
C = offset do flange ao plano do aro
T = 360·X/(N/2)
```

- `D` = ERD, `d` = diâmetro da circunferência dos furos do flange,
  `S` = diâmetro do furo do flange, `X` = cruzamentos, `N` = total de raios.
- O livro manda arredondar **para baixo**: o raio estica ~1 mm e o aro pode
  encolher ~2 mm sob tensão.

Tensão lateral (aproximação de equilíbrio):

```text
T_esq / T_dir = (offset_dir / L_dir) / (offset_esq / L_esq)
```

Compressão do aro (eq. 7), alongamento (eq. 3), tom de corda fixa e constrição
do pneu (eq. 8) estão em `wheel_lab/core/tension.py`.

## Roadmap

- **Fase 0 (atual)**: núcleo, validação, testes, correções de UI.
- **Fase 1**: calculadora completa, visualizador de montagem, dish/centralização
  e build sheet.
- **Fase 2**: solver físico de truing (aro como viga/anel + raios como molas
  só-tração), tensão, runout e sugestões de ajuste.
- **Fase 3**: assistente dos 4 conjuntos de montagem, biblioteca de componentes
  e exportação em PDF.
- **Fase 4**: rigidez/FEM, leitura de tom por microfone e diagnóstico avançado.

## Referência e direitos autorais

O PDF `Bicycle_Wheel_-_Jobst_Brandt.pdf` é usado apenas como referência local e
**não é versionado** (obra protegida). O código implementa as equações e ideias
de engenharia, com citação da fonte; nenhum texto ou figura do livro é
redistribuído.
