#!/usr/bin/env bash
# Cria/atualiza o ambiente gerenciado pelo uv e instala as dependências.
set -euo pipefail

cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  uv sync
elif command -v nix-shell >/dev/null 2>&1 && [ -f shell.nix ]; then
  nix-shell --run "uv sync"
else
  echo "uv não encontrado." >&2
  echo "Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo
echo "Pronto. Rode a interface com:"
echo "  ./run.sh"
echo
echo "Ou diretamente:"
echo "  uv run wheel_builder_qt.py"
echo
echo "Para rodar os testes:"
echo "  uv run pytest"
