#!/usr/bin/env bash
# Roda a interface com o ambiente gerenciado pelo uv.
#
# No NixOS (ou com WHEEL_LAB_USE_NIX=1), usa o shell.nix para fornecer uv e as
# bibliotecas gráficas que o wheel do PySide6 não empacota. Nas demais
# distribuições, usa o uv do ambiente criado por ./install.sh.
set -euo pipefail

cd "$(dirname "$0")"

# uv instalado pelo install.sh pode estar em ~/.local/bin ou ~/.cargo/bin.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

use_nix=0
if command -v nix-shell >/dev/null 2>&1 && [ -f shell.nix ]; then
  if [ "${WHEEL_LAB_USE_NIX:-}" = "1" ]; then
    use_nix=1
  elif [ -e /etc/NIXOS ] && [ "${WHEEL_LAB_USE_NIX:-1}" != "0" ]; then
    use_nix=1
  fi
fi

if [ "$use_nix" -eq 1 ]; then
  exec nix-shell --run "uv run wheel_builder_qt.py"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv não encontrado." >&2
  echo "Rode ./install.sh para preparar o ambiente." >&2
  echo "Ou instale com: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

exec uv run wheel_builder_qt.py
