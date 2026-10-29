#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
# Fija las dependencias de Lina en packaging/requisitos.txt (S8a): versiones exactas y hashes, para Python 3.11 a 3.14 a la vez.
# Lo ejecuta el mantenedor antes de etiquetar una versión (ver docs/publicacion.md). Necesita uv y red.
#
#   scripts/fijar_dependencias.sh            genera el archivo y comprueba que hay ruedas para cada Python
#   scripts/fijar_dependencias.sh --comprobar solo comprueba el archivo que hay
#
# Comprueba que cada paquete fijado tiene rueda binaria para Linux x86_64 en 3.11, 3.12, 3.13 y 3.14. La única excepción es evdev, que solo se
# publica como código fuente y se compila al instalar (por eso install.sh instala un compilador de C). Si falta una rueda, falla: mejor saberlo
# aquí que en el equipo de quien actualiza.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVO="packaging/requisitos.txt"
PYTHONS=(3.11 3.12 3.13 3.14)
SOLO_FUENTE=(evdev)

command -v uv >/dev/null || { echo "Hace falta uv: https://docs.astral.sh/uv/" >&2; exit 1; }
cd "$RAIZ"

if [ "${1:-}" != "--comprobar" ]; then
  uv pip compile pyproject.toml --universal --generate-hashes --python-version "${PYTHONS[0]}" \
     --custom-compile-command "scripts/fijar_dependencias.sh" -q -o "$ARCHIVO"
  echo "✔ $ARCHIVO generado"
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
EXCEPCIONES=(); for p in "${SOLO_FUENTE[@]}"; do EXCEPCIONES+=(--no-binary "$p"); done
for v in "${PYTHONS[@]}"; do
  if uv pip compile "$ARCHIVO" --python-version "$v" --python-platform x86_64-manylinux_2_28 --only-binary :all: "${EXCEPCIONES[@]}" \
       --no-header -q -o "$TMP/r$v.txt" 2> "$TMP/error$v.txt"; then
    echo "✔ Python $v: hay ruedas para todo"
  else
    echo "✘ Python $v: falta alguna rueda:" >&2; tail -4 "$TMP/error$v.txt" >&2; exit 1
  fi
done
