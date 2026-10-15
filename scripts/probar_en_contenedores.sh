#!/usr/bin/env bash
# Pasa las pruebas dentro de contenedores de Arch, Debian, Fedora y openSUSE (necesita docker o podman).
#   scripts/probar_en_contenedores.sh            todas las familias
#   scripts/probar_en_contenedores.sh debian     solo una (arch | debian | fedora | suse)
set -u
cd "$(dirname "$0")/.."
MOTOR="$(command -v podman || command -v docker || true)"
[ -n "$MOTOR" ] || { echo "Hace falta docker o podman."; exit 2; }

declare -A IMAGEN=([arch]=archlinux:latest [debian]=debian:stable [fedora]=fedora:latest [suse]=opensuse/tumbleweed)
declare -A PREPARAR=(
  [arch]="pacman -Syu --noconfirm --needed python python-pip gcc portaudio sudo"
  [debian]="apt-get update && apt-get install -y python3 python3-venv python3-pip python3-dev build-essential libportaudio2 sudo"
  [fedora]="dnf install -y python3 python3-pip python3-devel gcc portaudio sudo"
  [suse]="zypper --non-interactive install python3 python3-pip python3-devel gcc libportaudio2 sudo"
)
FAMILIAS=("$@"); [ ${#FAMILIAS[@]} -gt 0 ] || FAMILIAS=(arch debian fedora suse)
fallos=0
for f in "${FAMILIAS[@]}"; do
  echo; echo "=== $f (${IMAGEN[$f]}) ==="
  "$MOTOR" run --rm -v "$PWD":/lina:ro -e LINA_FAMILIA_ESPERADA="$f" "${IMAGEN[$f]}" bash -c "
    set -e
    ${PREPARAR[$f]}
    cp -r /lina /tmp/lina && cd /tmp/lina
    python3 -m venv /tmp/v && /tmp/v/bin/pip install -q -e '.[dev]'
    /tmp/v/bin/pytest -q" || { echo "FALLÓ en $f"; fallos=$((fallos + 1)); }
done
[ "$fallos" -eq 0 ] && echo && echo "Todas las familias en verde." || { echo; echo "$fallos familia(s) con fallos."; exit 1; }
