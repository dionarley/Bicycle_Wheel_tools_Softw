#!/usr/bin/env bash
# Instala o ambiente do Wheel Lab em .venv e as dependências.
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Pronto. Rode a interface com:"
echo "  ./run.sh"
echo
echo "Em sistemas com as bibliotecas gráficas no caminho padrão, também vale:"
echo "  .venv/bin/python wheel_builder_qt.py"
echo
echo "Para rodar os testes:"
echo "  .venv/bin/pip install -r requirements-dev.txt"
echo "  .venv/bin/python -m pytest"
