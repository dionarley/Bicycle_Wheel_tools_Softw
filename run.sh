#!/usr/bin/env bash
# Roda a interface. Em NixOS, usa o shell.nix para fornecer as bibliotecas
# gráficas que o wheel do PySide6 não empacota (libGL, libxkbcommon etc.).
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  ./install.sh
fi

if command -v nix-shell >/dev/null 2>&1 && [ -f shell.nix ]; then
  exec nix-shell --run ".venv/bin/python wheel_builder_qt.py"
fi

exec .venv/bin/python wheel_builder_qt.py
