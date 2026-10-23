#!/usr/bin/env bash
# Script legado do protótipo. Mantido para compatibilidade; use ./install.sh.
set -euo pipefail
exec "$(dirname "$0")/install.sh" "$@"
