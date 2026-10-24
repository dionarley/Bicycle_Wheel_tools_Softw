# Wheel Lab

Ferramentas de cálculo, montagem e alinhamento de rodas de bicicleta, baseadas
em *The Bicycle Wheel* (Jobst Brandt, 3ª ed.).

O projeto começou como um protótipo de calculadora em PySide6. A Fase 0 separa
a engenharia da interface, corrige os crashes do protótipo e cria uma base
testável. A Fase 1 completa a calculadora, adiciona dish/centralização e gera
uma ficha de montagem. A Fase 2 substitui o simulador didático por um solver
elástico de alinhamento, com tensões, runout e sugestões de ajuste.

## Estado atual (Fase 2)

- **Núcleo de cálculo puro em Python** (`wheel_lab/core/`), sem Qt e sem NumPy.
- **Comprimento de raio** pela equação 1 de Brandt, por lado, com arredondamento
  sempre para baixo.
- **Validação de padrão**: `T = 720·X/N ≤ 90°`; máximo de cruzamentos `N/8`.
- **ERD** a partir do diâmetro externo e da profundidade do niple.
- **Tensão**: razão esquerda/direita pelo equilíbrio lateral, tensões alvo,
  compressão do aro, alongamento do raio e tom aproximado.
- **Constantes de montagem**: passo de rosca de 56 TPI (≈ 0,4536 mm/volta;
  1/4 de volta ≈ 0,1134 mm).
- **Dish/centralização**: offsets medidos do centro do cubo, deslocamento do
  plano do aro, distância entre locknuts e correção sugerida.
- **Visualizador** com vista superior, corte axial, filtros por lado/sentido e
  destaque do raio selecionado.
- **Ficha de montagem** com resumo, JSON, Markdown e PDF.
- **Solver físico de truing** (`wheel_lab/core/truing.py`): aro como anel
  elástico discretizado nos furos, com flexão lateral, flexão no plano e
  membrana (hoop); raios como molas axiais só-tração, com rigidez geométrica.
  Raios que ficam frouxos são desativados, a folga é rastreada e o equilíbrio é
  resolvido novamente.
- **Sugestões de ajuste** por mínimo quadrado regularizado, com passo global
  limitado, arredondamento para 1/4 de volta e avisos de tensão/frouxidão.
- **Instalação assistida** para NixOS, Arch, Debian/Ubuntu e RHEL/Fedora, com
  detecção de distribuição e instalação das bibliotecas gráficas do Qt.
- **Testes** de engenharia, solver e smoke tests da UI em modo offscreen.

O modelo de truing é **incremental e linearizado**: parte da forma atual
(runout medido ou exemplo) e calcula a mudança causada pelos ajustes. As
sugestões são um passo; aplique, recalcule e repita, como no alinhamento real.
As propriedades padrão do aro são rigidezes equivalentes de um aro de alumínio
de perfil médio, não a geometria literal da seção. O solver exige número de
raios múltiplo de 4, pois usa a tabela de montagem.

## Instalação

Requisitos: Linux com Qt; Python 3.10+ é baixado/gerenciado pelo
[uv](https://docs.astral.sh/uv/). O projeto usa `uv` para criar o ambiente e
travar as versões (`uv.lock`); não é preciso criar `.venv` nem usar `pip`
manualmente.

### Instalação assistida

```bash
./install.sh   # dependências do sistema + uv sync
./run.sh       # uv run wheel_builder_qt.py
```

O `install.sh` detecta o ambiente e instala as bibliotecas gráficas que o wheel
do PySide6 não empacota:

- **NixOS**: usa o `shell.nix` (uv, Qt, xcb e Wayland).
- **Arch/Manjaro**: `pacman`.
- **Debian/Ubuntu**: `apt-get`.
- **RHEL/Fedora/Rocky/Alma**: `dnf` ou `yum`.

Se o `uv` não estiver instalado, ele é instalado no diretório padrão do usuário
(`~/.local/bin`). Depois o script executa `uv sync`.

Opções úteis:

```bash
./install.sh --dry-run          # mostra os comandos sem executar
./install.sh --no-system        # não instala dependências do sistema
./install.sh --no-uv            # não instala o uv automaticamente
./install.sh --distro arch      # força arch, debian ou rhel
WHEEL_LAB_USE_NIX=1 ./install.sh  # força o Nix em qualquer distribuição
WHEEL_LAB_USE_NIX=0 ./install.sh  # ignora o Nix, inclusive no NixOS
```

Para instalar apenas as bibliotecas do sistema:

```bash
./install_system_deps.sh
./install_system_deps.sh --dry-run --distro debian
```

Em RHEL 9, o pacote `xcb-util-cursor` pode estar no EPEL. Se o script avisar que
ele não foi encontrado:

```bash
sudo dnf install epel-release
sudo dnf install xcb-util-cursor
```

### NixOS

O wheel do PySide6 não traz `libGL`, `libxkbcommon`, `libxcb-cursor` e outras
bibliotecas do sistema. O `shell.nix` fornece essas bibliotecas (incluindo os
plugins xcb e Wayland) **e o próprio uv**. O `run.sh` usa o Nix automaticamente
no NixOS; nas demais distribuições, usa o `uv` do ambiente criado por
`./install.sh`. Para rodar direto:

```bash
nix-shell --run "uv run wheel_builder_qt.py"
```

O script antigo `install_numpy.sh` foi mantido como atalho para `install.sh`.

## Testes

```bash
uv run pytest
```

Em NixOS:

```bash
nix-shell --run "uv run pytest"
```

Os testes da UI usam `QT_QPA_PLATFORM=offscreen` (definido em
`tests/conftest.py`), então rodam sem display.

## Estrutura

```text
wheel_builder_qt.py       # janela PySide6 (entry point)
pyproject.toml            # dependências e configuração do projeto
uv.lock                   # versões travadas pelo uv
install.sh                # detecta NixOS/distribuição e prepara o uv
install_system_deps.sh    # libs Qt via pacman/apt/dnf
run.sh                    # executa a UI (Nix no NixOS, uv nas demais)
shell.nix                 # uv + bibliotecas gráficas para NixOS
wheel_lab/
  __init__.py
  core/
    models.py             # dataclasses e validações
    geometry.py           # T, ERD, máximo de cruzamentos
    spoke_length.py       # equação 1 e arredondamento
    lacing.py             # tabela de raios para desenho
    tension.py            # razão L/R, alvo, alongamento, tom, pneu
    build_sheet.py        # ficha, JSON, Markdown e HTML/PDF
    truing.py             # solver elástico, runout, tensões e sugestões
    units.py              # TPI, voltas ↔ mm
tests/
  test_spoke_length.py
  test_centering.py
  test_build_sheet.py
  test_geometry.py
  test_tension.py
  test_lacing.py
  test_truing.py
  test_units.py
  test_ui_smoke.py
```

## Fórmulas principais

Comprimento de raio (Brandt, eq. 1):

```text
L = sqrt(A² + B² + C²) - S/2
A = (d/2)·sin(T)
B = D/2 - (d/2)·cos(T)
C_esq = offset_esq + dish
C_dir = offset_dir - dish
T = 360·X/(N/2)
```

- `D` = ERD, `d` = diâmetro da circunferência dos furos do flange,
  `S` = diâmetro do furo do flange, `X` = cruzamentos, `N` = total de raios.
- `dish` positivo desloca o plano do aro para a direita do centro do cubo;
  a correção de centralização é `-dish`.
- O livro manda arredondar **para baixo**: o raio estica ~1 mm e o aro pode
  encolher ~2 mm sob tensão.

Tensão lateral (aproximação de equilíbrio):

```text
T_esq / T_dir = (offset_dir / L_dir) / (offset_esq / L_esq)
```

Compressão do aro (eq. 7), alongamento (eq. 3), tom de corda fixa e constrição
do pneu (eq. 8) estão em `wheel_lab/core/tension.py`.

## Modelo de alinhamento (Fase 2)

O aro é discretizado nos furos dos raios, com dois graus de liberdade por nó:
deslocamento radial e lateral. A energia inclui:

- flexão lateral do aro;
- flexão no plano (radial);
- membrana/hoop, que resiste à variação local do perímetro;
- molas axiais dos raios, com rigidez geométrica dependente da tensão.

O ajuste do niple encurta o comprimento livre do raio em `s` (positivo ao
apertar). O alongamento elástico é `n·δ + s`, onde `n` é a direção do raio e
`δ` o deslocamento do aro. A tensão é limitada a zero: o solver usa um conjunto
ativo, desativa raios frouxos, guarda a folga e resolve o equilíbrio de novo.
A matriz de influência dá a resposta do aro a 1 mm de aperto em cada raio.

As sugestões resolvem um mínimo quadrado regularizado com pesos para runout
lateral e radial. O passo inteiro é reduzido para respeitar no máximo 3/4 de
volta por raio e arredondado para 1/4 de volta. Como o modelo é linearizado,
aplique um passo, recalcule e repita. Os padrões do aro são rigidezes
equivalentes (`E = 69 GPa`, `I_lat = 7000 mm⁴`, `I_no_plano = 1500 mm⁴`,
`A = 40 mm²`) e podem ser ajustados em `RimElasticProperties`.

Limitações: o modelo usa apenas deslocamentos radial e lateral (sem grau de
liberdade tangencial); não simula avarias, flambagem local, fadiga, rotação,
pneu ou atrito do niple; a folga de um raio frouxo é tratada de forma
unidimensional. Use-o como assistente de truing, não como substituto da
inspeção e do tensiômetro.

## Roadmap

- **Fase 0 (concluída)**: núcleo, validação, testes, correções de UI.
- **Fase 1 (concluída)**: calculadora completa, visualizador de montagem,
  dish/centralização e build sheet em JSON/Markdown/PDF.
- **Fase 2 (atual)**: solver físico de truing (aro como anel + raios como
  molas só-tração), tensão, runout e sugestões de ajuste.
- **Fase 3**: assistente dos 4 conjuntos de montagem, biblioteca de componentes
  e integração com o build sheet.
- **Fase 4**: rigidez/FEM, leitura de tom por microfone e diagnóstico avançado.

## Referência e direitos autorais

O PDF `Bicycle_Wheel_-_Jobst_Brandt.pdf` é usado apenas como referência local e
**não é versionado** (obra protegida). O código implementa as equações e ideias
de engenharia, com citação da fonte; nenhum texto ou figura do livro é
redistribuído.
