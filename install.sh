#!/usr/bin/env bash
# Cria/atualiza o ambiente gerenciado pelo uv e instala as dependências.
#
# NixOS: usa o shell.nix (uv + bibliotecas gráficas).
# Arch/Debian/RHEL: instala as bibliotecas do Qt/PySide6 pelo gerenciador de
# pacotes da distribuição e depois roda o uv sync.
set -euo pipefail

cd "$(dirname "$0")"

# O instalador oficial do uv usa ~/.local/bin (ou ~/.cargo/bin em versões
# antigas). Inclui esses diretórios para o uv recém-instalado ser encontrado
# tanto neste script quanto no run.sh.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

DRY_RUN=0
USE_SYSTEM=1
INSTALL_UV=1
FORCE_NIX=0
NO_NIX=0
DISTRO=""

usage() {
  cat <<'EOF'
Uso: ./install.sh [opções]

Prepara o ambiente do Wheel Lab. Detecta NixOS (shell.nix) ou a distribuição
(Arch, Debian/Ubuntu, RHEL/Fedora) e instala o que falta.

Opções:
  --dry-run          Mostra os comandos sem executar.
  --no-system        Não instala dependências do sistema.
  --no-uv            Não instala o uv automaticamente.
  --nix              Força o uso do shell.nix (se nix-shell existir).
  --no-nix           Ignora o Nix e usa o gerenciador da distribuição.
  --distro NOME      Força arch, debian ou rhel no instalador do sistema.
  -h, --help         Mostra esta ajuda.

Variável de ambiente:
  WHEEL_LAB_USE_NIX=1  Força o Nix em qualquer distribuição.
  WHEEL_LAB_USE_NIX=0  Ignora o Nix, inclusive no NixOS.

Exemplos:
  ./install.sh
  ./install.sh --dry-run
  WHEEL_LAB_USE_NIX=1 ./install.sh
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-system) USE_SYSTEM=0 ;;
    --no-uv) INSTALL_UV=0 ;;
    --nix) FORCE_NIX=1 ;;
    --no-nix) NO_NIX=1 ;;
    --distro)
      if [ $# -lt 2 ]; then
        echo "Faltou o valor de --distro." >&2
        exit 2
      fi
      DISTRO="$2"
      shift
      ;;
    --distro=*) DISTRO="${1#*=}" ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

use_nix=0
if [ "$NO_NIX" -eq 0 ] \
  && command -v nix-shell >/dev/null 2>&1 \
  && [ -f shell.nix ]; then
  if [ "$FORCE_NIX" -eq 1 ]; then
    use_nix=1
  elif [ "${WHEEL_LAB_USE_NIX:-}" = "1" ]; then
    use_nix=1
  elif [ -e /etc/NIXOS ] && [ "${WHEEL_LAB_USE_NIX:-1}" != "0" ]; then
    use_nix=1
  fi
fi

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if [ "$INSTALL_UV" -eq 0 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "uv não encontrado; --no-uv impediria a instalação." >&2
      return 0
    fi
    echo "uv não encontrado e --no-uv foi usado." >&2
    echo "Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl não encontrado; não é possível instalar o uv." >&2
    echo "Instale curl e tente novamente." >&2
    exit 1
  fi

  echo "uv não encontrado; instalando no diretório padrão do usuário..."
  if [ "$DRY_RUN" -eq 1 ]; then
    echo '+ curl -LsSf https://astral.sh/uv/install.sh | sh'
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  hash -r 2>/dev/null || true
  if [ "$DRY_RUN" -eq 0 ] && ! command -v uv >/dev/null 2>&1; then
    echo "uv foi instalado, mas não está no PATH." >&2
    echo "Adicione ~/.local/bin ao PATH e rode ./install.sh novamente." >&2
    exit 1
  fi
}

if [ "$use_nix" -eq 1 ]; then
  echo "Nix detectado: usando o shell.nix para uv e bibliotecas gráficas."
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ nix-shell --run 'uv sync'"
  else
    nix-shell --run "uv sync"
  fi
else
  if [ "$USE_SYSTEM" -eq 1 ]; then
    deps_args=()
    if [ "$DRY_RUN" -eq 1 ]; then
      deps_args+=(--dry-run)
    fi
    if [ -n "$DISTRO" ]; then
      deps_args+=(--distro "$DISTRO")
    fi
    bash ./install_system_deps.sh "${deps_args[@]}"
  else
    echo "Pulando dependências do sistema (--no-system)."
  fi

  ensure_uv
  if [ "$DRY_RUN" -eq 1 ]; then
    echo '+ uv sync'
  else
    uv sync
  fi
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
if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "Dry-run: nenhum comando foi executado."
fi
