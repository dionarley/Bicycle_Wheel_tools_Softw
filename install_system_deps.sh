#!/usr/bin/env bash
# Instala as bibliotecas de sistema exigidas pelo PySide6/Qt no Linux.
# Suporta Arch, Debian/Ubuntu e RHEL/Fedora. No NixOS, use o shell.nix.
set -euo pipefail

DRY_RUN=0
FORCE=0
DISTRO=""

usage() {
  cat <<'EOF'
Uso: ./install_system_deps.sh [opções]

Instala as bibliotecas gráficas do Qt/PySide6 usando o gerenciador de pacotes
da distribuição. O NixOS é atendido pelo shell.nix e não precisa deste script.

Opções:
  --dry-run          Mostra os comandos sem executar.
  --force            Instala mesmo que as bibliotecas já pareçam presentes.
  --distro NOME      Força a distribuição: arch, debian ou rhel.
  -h, --help         Mostra esta ajuda.

Exemplos:
  ./install_system_deps.sh
  ./install_system_deps.sh --dry-run --distro arch
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
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

if [ -z "$DISTRO" ]; then
  if command -v pacman >/dev/null 2>&1; then
    DISTRO=arch
  elif command -v apt-get >/dev/null 2>&1; then
    DISTRO=debian
  elif command -v dnf >/dev/null 2>&1; then
    DISTRO=rhel
  elif command -v yum >/dev/null 2>&1; then
    DISTRO=rhel
  else
    cat >&2 <<'EOF'
Não reconheci o gerenciador de pacotes desta distribuição.

Distribuições suportadas:
  Arch/Manjaro       pacman
  Debian/Ubuntu      apt-get
  RHEL/Fedora/Rocky  dnf ou yum

Use --distro arch|debian|rhel para forçar, ou instale manualmente as
bibliotecas do Qt/PySide6. No NixOS, use ./install.sh (shell.nix).
EOF
    exit 1
  fi
fi

case "$DISTRO" in
  arch|archlinux|manjaro)
    DISTRO=arch
    PACKAGES=(
      python
      uv
      curl
      ca-certificates
      libxcb
      xcb-util
      xcb-util-cursor
      xcb-util-image
      xcb-util-keysyms
      xcb-util-renderutil
      xcb-util-wm
      libxkbcommon
      libxkbcommon-x11
      fontconfig
      freetype2
      libglvnd
      mesa
      dbus
      libx11
      libxext
      libxrender
      libxi
      libxfixes
      libxrandr
      libice
      libsm
      glib2
      wayland
      libxcursor
    )
    ;;
  debian|ubuntu|apt)
    DISTRO=debian
    PACKAGES=(
      curl
      ca-certificates
      libxcb1
      libxcb-cursor0
      libxcb-image0
      libxcb-keysyms1
      libxcb-render-util0
      libxcb-util1
      libxcb-icccm4
      libxcb-xinerama0
      libxcb-randr0
      libxcb-shape0
      libxcb-sync1
      libxcb-xfixes0
      libxcb-shm0
      libxcb-render0
      libxcb-glx0
      libxcb-xkb1
      libx11-6
      libx11-xcb1
      libxext6
      libxrender1
      libxi6
      libxfixes3
      libxrandr2
      libice6
      libsm6
      libxkbcommon0
      libxkbcommon-x11-0
      libfontconfig1
      libfreetype6
      libgl1
      libglx0
      libegl1
      libdbus-1-3
      libglib2.0-0
      libwayland-client0
      libwayland-cursor0
      libwayland-egl1
      libxcursor1
    )
    ;;
  rhel|fedora|centos|rocky|almalinux|dnf|yum)
    DISTRO=rhel
    PACKAGES=(
      curl
      ca-certificates
      libxcb
      xcb-util
      xcb-util-cursor
      xcb-util-image
      xcb-util-keysyms
      xcb-util-renderutil
      xcb-util-wm
      libxkbcommon
      libxkbcommon-x11
      fontconfig
      freetype
      mesa-libGL
      mesa-libEGL
      dbus-libs
      libX11
      libXext
      libXrender
      libXi
      libXfixes
      libXrandr
      libICE
      libSM
      glib2
      libwayland-client
      libwayland-cursor
      libwayland-egl
      libXcursor
    )
    ;;
  *)
    echo "Distribuição desconhecida: $DISTRO" >&2
    echo "Use arch, debian ou rhel." >&2
    exit 2
    ;;
esac

# Evita pedir sudo/instalar de novo quando as bibliotecas principais já estão
# disponíveis. Em --dry-run, sempre mostra o comando para fins de diagnóstico.
if [ "$DRY_RUN" -eq 0 ] && [ "$FORCE" -eq 0 ]; then
  LDCONFIG="$(command -v ldconfig || true)"
  if [ -z "$LDCONFIG" ] && [ -x /sbin/ldconfig ]; then
    LDCONFIG=/sbin/ldconfig
  fi
  if [ -n "$LDCONFIG" ]; then
    missing=0
    for lib in \
      libxcb-cursor.so.0 \
      libxcb-xkb.so.1 \
      libxcb-render.so.0 \
      libxcb-util.so.1 \
      libxkbcommon.so.0 \
      libxkbcommon-x11.so.0 \
      libGL.so.1 \
      libwayland-client.so.0 \
      libX11.so.6 \
      libX11-xcb.so.1; do
      if ! "$LDCONFIG" -p 2>/dev/null | grep -q "$lib"; then
        missing=1
        break
      fi
    done
    if [ "$missing" -eq 0 ]; then
      echo "Bibliotecas gráficas principais já encontradas; nada a instalar."
      exit 0
    fi
  fi
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
  else
    echo "Execute como root ou instale sudo para continuar." >&2
    exit 1
  fi
else
  SUDO=()
fi

run() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
  if [ "$DRY_RUN" -eq 0 ]; then
    "${SUDO[@]}" "$@"
  fi
}

package_available() {
  case "$DISTRO" in
    arch)
      pacman -Q "$1" >/dev/null 2>&1 || pacman -Si "$1" >/dev/null 2>&1
      ;;
    debian)
      dpkg -s "$1" >/dev/null 2>&1 || apt-cache show "$1" >/dev/null 2>&1
      ;;
    rhel)
      rpm -q "$1" >/dev/null 2>&1 && return 0
      if command -v dnf >/dev/null 2>&1; then
        dnf info -q "$1" >/dev/null 2>&1
      else
        yum info -q "$1" >/dev/null 2>&1
      fi
      ;;
  esac
}

filter_available_packages() {
  local pkg
  local -a available=()
  local -a missing=()

  for pkg in "${PACKAGES[@]}"; do
    if package_available "$pkg"; then
      available+=("$pkg")
    else
      missing+=("$pkg")
    fi
  done

  if [ ${#missing[@]} -gt 0 ]; then
    echo "Aviso: pacotes não encontrados e ignorados: ${missing[*]}" >&2
    if [ "$DISTRO" = "rhel" ]; then
      for pkg in "${missing[@]}"; do
        if [ "$pkg" = "xcb-util-cursor" ]; then
          echo "Dica (RHEL 9): habilite o EPEL para obter xcb-util-cursor:" >&2
          echo "  sudo dnf install epel-release" >&2
          echo "  sudo dnf install xcb-util-cursor" >&2
        fi
      done
    fi
  fi

  if [ ${#available[@]} -eq 0 ]; then
    echo "Nenhum pacote disponível; verifique os repositórios." >&2
    exit 1
  fi

  PACKAGES=("${available[@]}")
}

echo "Distribuição: $DISTRO"
echo "Instalando bibliotecas do Qt/PySide6..."

if [ "$DISTRO" = "debian" ]; then
  run apt-get update
fi

if [ "$DRY_RUN" -eq 0 ]; then
  filter_available_packages
fi

case "$DISTRO" in
  arch)
    run pacman -S --needed --noconfirm "${PACKAGES[@]}"
    ;;
  debian)
    run apt-get install -y --no-install-recommends "${PACKAGES[@]}"
    ;;
  rhel)
    if command -v dnf >/dev/null 2>&1 || ! command -v yum >/dev/null 2>&1; then
      run dnf install -y --skip-broken "${PACKAGES[@]}"
    else
      run yum install -y --skip-broken "${PACKAGES[@]}"
    fi
    ;;
esac

echo
echo "Concluído. Se a interface ainda não abrir, confira as mensagens do Qt"
echo "em ./run.sh e instale os pacotes que faltarem."
