#!/usr/bin/env bash
# Roda a interface com o ambiente gerenciado pelo uv. Em NixOS, usa o shell.nix
# para fornecer uv e as bibliotecas gráficas que o wheel do PySide6 não
# empacota (libGL, libxkbcommon etc.).
set -euo pipefail

cd "$(dirname "$0")"

if command -v nix-shell >/dev/null 2>&1 && [ -f shell.nix ]; then
  exec nix-shell --run "uv run wheel_builder_qt.py"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv não encontrado." >&2
  echo "Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

exec uv run wheel_builder_qt.py
