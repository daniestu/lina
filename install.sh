#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
# Instalador de Lina: un solo comando, en Arch, Debian/Ubuntu, Fedora u openSUSE (y derivadas).
#
#   curl -fsSL https://raw.githubusercontent.com/daniestu/lina/main/install.sh | bash      desde cero
#   ./install.sh                  desde una copia del repositorio
#
#   --simular, --dry-run   dice lo que haría, sin tocar nada
#   -y, --si               responde «sí» a todo (menos a los permisos de administrador de Lina, que se dan a mano con «lina privilegios»)
#   --quitar [--todo]      desinstala (--todo borra también tus ajustes, claves y datos)
#   --sin-sistema          no instala paquetes del sistema (los pones tú)
#   --sin-bienvenida       no abre la configuración guiada al terminar
#   --entrada              prepara también el control de programas con la pantalla (pide administrador)
#   --atajo TECLA          tecla del atajo global (por defecto Meta+Espacio en KDE, Ctrl+Alt+Espacio en GNOME)
#
# Lo que hace: instala lo que falte del sistema (te enseña la orden y pide tu contraseña), crea un entorno de Python aislado, instala Lina,
# baja los modelos de voz, registra el servicio de usuario y el atajo, y abre la configuración guiada. Todo queda anotado en
# ~/.local/state/lina/instalacion.log y `lina uninstall` lo deshace.
set -euo pipefail

SIMULAR=0; QUITAR=0; SI=0; TODO=0; SIN_SISTEMA=0; SIN_BIENVENIDA=0; ENTRADA=0; ATAJO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --simular|--dry-run) SIMULAR=1 ;;
    --quitar|--desinstalar) QUITAR=1 ;;
    -y|--si) SI=1 ;;
    --todo) TODO=1 ;;
    --sin-sistema) SIN_SISTEMA=1 ;;
    --sin-bienvenida) SIN_BIENVENIDA=1 ;;
    --entrada) ENTRADA=1 ;;
    --atajo) shift; ATAJO="${1:-}" ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1 (mira ./install.sh --help)" >&2; exit 2 ;;
  esac
  shift
done

DATOS="${XDG_DATA_HOME:-$HOME/.local/share}/lina"
ESTADO="${XDG_STATE_HOME:-$HOME/.local/state}/lina"
VENV="$DATOS/venv"
REPO="${LINA_REPO:-https://github.com/daniestu/lina.git}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"

paso()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✔\033[0m %s\n' "$*"; }
aviso() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fallo() { printf '  \033[31m✘\033[0m %s\n' "$*" >&2; exit 1; }
hacer() { if [ "$SIMULAR" = 1 ]; then printf '  [simulación] %s\n' "$*"; else "$@"; fi; }
# Con «curl | bash» la entrada estándar es el propio script: las preguntas se hacen por la terminal
CON_TTY=0; [ -r /dev/tty ] && [ -w /dev/tty ] && { : < /dev/tty; } 2>/dev/null && CON_TTY=1
pregunta() {    # pregunta "texto" → 0 si sí. Con -y siempre sí; sin terminal, no.
  [ "$SI" = 1 ] && return 0
  [ "$CON_TTY" = 1 ] || return 1
  local r; printf '  %s [S/n] ' "$1" > /dev/tty; read -r r < /dev/tty || return 1
  case "${r,,}" in ""|s|si|sí|y|yes) return 0 ;; *) return 1 ;; esac
}

[ "$(id -u)" -ne 0 ] || [ "${LINA_PERMITIR_ROOT:-0}" = 1 ] || fallo "No lo ejecutes como administrador: Lina se instala para tu usuario (pedirá la contraseña solo para los paquetes del sistema)."

# ---------------------------------------------------------------- desinstalar
if [ "$QUITAR" = 1 ]; then
  paso "Desinstalando Lina"
  if [ -x "$VENV/bin/lina" ]; then
    ARGS=(); [ "$SIMULAR" = 1 ] && ARGS+=(--simular); [ "$SI" = 1 ] && ARGS+=(--si); [ "$TODO" = 1 ] && ARGS+=(--todo)
    if [ "$CON_TTY" = 1 ] && [ "$SI" = 0 ]; then "$VENV/bin/lina" uninstall "${ARGS[@]}" < /dev/tty; else "$VENV/bin/lina" uninstall "${ARGS[@]}"; fi
  else
    aviso "No encuentro la instalación en $VENV: quito solo lo básico."
    hacer systemctl --user disable --now lina.service 2>/dev/null || true
    hacer rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/lina.service" "$HOME/.local/bin/lina"
  fi
  exit 0
fi

# ---------------------------------------------------------------- registro
if [ "$SIMULAR" = 0 ]; then
  mkdir -p "$ESTADO"; LOG="$ESTADO/instalacion.log"
  exec > >(tee -a "$LOG") 2>&1
  echo "=== $(date '+%F %T') install.sh ($*) ==="
fi

# ---------------------------------------------------------------- 1. sistema
paso "1/6 Comprobando el sistema"
# El Python de Lina: el de uv si está (no cambia cuando la distribución sube de versión el suyo); si no, el primero del sistema entre 3.11 y 3.14,
# que es para lo que están fijadas y comprobadas las dependencias. Fuera de ese rango no se sigue: pip fallaría a medias.
version_de() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null; }
en_rango() { case "$(version_de "$1")" in 3.11|3.12|3.13|3.14) return 0 ;; *) return 1 ;; esac; }
PY=""; ORIGEN_PY=""
if command -v uv >/dev/null; then
  PY="$(uv --no-cache python find --managed-python 3.14 2>/dev/null || true)"
  if [ -z "$PY" ]; then
    if [ "$SIMULAR" = 1 ]; then printf '  [simulación] uv python install 3.14\n'
    else uv python install 3.14 >/dev/null 2>&1 || aviso "uv no ha podido instalar Python 3.14: busco uno del sistema."; PY="$(uv --no-cache python find --managed-python 3.14 2>/dev/null || true)"; fi
  fi
  { [ -n "$PY" ] && en_rango "$PY"; } && ORIGEN_PY="de uv" || PY=""
fi
if [ -z "$PY" ]; then
  for p in python3 python3.14 python3.13 python3.12 python3.11; do
    if command -v "$p" >/dev/null && en_rango "$p"; then PY="$(command -v "$p")"; ORIGEN_PY="del sistema"; break; fi
  done
fi
[ -n "$PY" ] || fallo "No encuentro un Python entre 3.11 y 3.14$(command -v python3 >/dev/null && echo " (python3 es $(version_de python3))"), que es para lo que están comprobadas las dependencias de Lina. Instala uv (Arch: sudo pacman -S uv · Fedora: sudo dnf install uv) y repite: Lina usará su propio Python. O instala uno de esos (Fedora 45: sudo dnf install python3.14)."
ok "Python para Lina: $("$PY" -V 2>&1) $ORIGEN_PY ($PY)"
[ "$ORIGEN_PY" = "de uv" ] || command -v uv >/dev/null || aviso "Con el Python del sistema, Lina deja de arrancar cuando tu distribución lo cambie de versión; con uv instalado usaría el suyo. Si pasa, repite este instalador."
[ -r /etc/os-release ] && . /etc/os-release
ok "${PRETTY_NAME:-Linux}${XDG_SESSION_TYPE:+ · sesión $XDG_SESSION_TYPE}${XDG_CURRENT_DESKTOP:+ · $XDG_CURRENT_DESKTOP}"
[ "$(uname -m)" = "x86_64" ] || aviso "Arquitectura $(uname -m): lo probado es x86_64; algún paquete de Python podría tardar en compilarse."

# ---------------------------------------------------------------- 2. código
paso "2/6 Código de Lina"
if [ -n "$AQUI" ] && [ -f "$AQUI/pyproject.toml" ] && [ -d "$AQUI/src/lina" ]; then
  FUENTE="$AQUI"; CLONADO=0; ok "Usando esta copia: $FUENTE"
else
  FUENTE="$DATOS/fuente"; CLONADO=1
  command -v git >/dev/null || fallo "Falta git para bajar Lina. Instálalo (por ejemplo «sudo apt install git», «sudo dnf install git», «sudo pacman -S git») y repite."
  if [ -d "$FUENTE/.git" ]; then ok "Ya estaba en $FUENTE"; hacer git -C "$FUENTE" pull --ff-only --quiet
  else hacer mkdir -p "$DATOS"; hacer git clone --quiet --depth 1 "$REPO" "$FUENTE"; ok "Bajado de $REPO"; fi
fi
[ "$SIMULAR" = 1 ] && [ ! -d "$FUENTE/src" ] && { aviso "Simulación sin el código a mano: no puedo seguir comprobando."; exit 0; }

# ---------------------------------------------------------------- 3. paquetes del sistema
paso "3/6 Paquetes del sistema"
if [ "$SIN_SISTEMA" = 1 ]; then aviso "Saltado (--sin-sistema)."
else
  set +e; ORDEN="$(PYTHONPATH="$FUENTE/src" "$PY" -m lina.nucleo.plataforma base)"; RC=$?; set -e
  if [ "$RC" -ne 0 ]; then
    aviso "No reconozco el gestor de paquetes de esta distribución. Instala a mano: Python con venv y pip, un compilador de C, git, PortAudio y libnotify."
    aviso "Si es una derivada, prueba con LINA_DISTRO=debian (o arch, fedora, suse) delante del comando."
  elif [ -z "$ORDEN" ]; then ok "No falta nada"
  else
    echo "  Faltan paquetes del sistema. La orden sería:"; echo "      $ORDEN"
    if [ "$SIMULAR" = 1 ]; then printf '  [simulación] la ejecutaría (pide tu contraseña)\n'
    elif pregunta "¿La ejecuto? (pide tu contraseña de administrador)"; then bash -c "$ORDEN" || fallo "No se han podido instalar. Hazlo a mano con la orden de arriba y repite."
    else fallo "Sin esos paquetes no puedo seguir. Ejecuta la orden de arriba y repite, o usa --sin-sistema si ya lo tienes todo."; fi
  fi
fi

# ---------------------------------------------------------------- 4. entorno de Python
paso "4/6 Entorno de Python aislado"
hacer mkdir -p "$DATOS"
venv_vale() {    # el entorno es del Python elegido y sigue siendo de su versión (una subida del Python del sistema lo deja roto)
  [ -f "$VENV/pyvenv.cfg" ] && [ -x "$VENV/bin/python" ] || return 1
  [ "$(sed -n 's/^home = //p' "$VENV/pyvenv.cfg")" = "$(dirname "$PY")" ] && [ "$(version_de "$VENV/bin/python")" = "$(version_de "$PY")" ]
}
RECREAR=0
if [ -d "$VENV" ] && ! venv_vale; then
  aviso "El entorno de $VENV es de otro Python o está roto: lo creo de nuevo con $("$PY" -V 2>&1)."
  hacer rm -rf "$VENV"; RECREAR=1
fi
{ [ -d "$VENV" ] && [ "$RECREAR" = 0 ]; } || hacer "$PY" -m venv "$VENV"
hacer "$VENV/bin/pip" install --quiet --upgrade pip
REQUISITOS="$FUENTE/packaging/requisitos.txt"
if [ -f "$REQUISITOS" ]; then
  # Versiones exactas y comprobadas con su hash (S8a): lo que se probó, no lo último que haya en PyPI ese día
  hacer "$VENV/bin/pip" install --quiet --require-hashes -r "$REQUISITOS" \
    || fallo "No he podido instalar las dependencias fijadas con $("$PY" -V 2>&1). Mira el error de pip de arriba y repite; si no se arregla, borra $VENV y repite."
  hacer "$VENV/bin/pip" install --quiet --no-deps -e "$FUENTE"
else
  hacer "$VENV/bin/pip" install --quiet -e "$FUENTE"
fi
ok "Lina instalada en $VENV (modo editable: «lina update» la actualiza)"

# ---------------------------------------------------------------- 5. modelos, servicio y atajo
paso "5/6 Modelos de voz, servicio y atajo"
ARGS=(); [ "$SIMULAR" = 1 ] && ARGS+=(--simular); [ "$SI" = 1 ] && ARGS+=(--si); [ "$ENTRADA" = 1 ] && ARGS+=(--entrada); [ -n "$ATAJO" ] && ARGS+=(--atajo "$ATAJO")
LINA="$VENV/bin/lina"
if [ "$SIMULAR" = 1 ] && [ ! -x "$LINA" ]; then LINA="$PY -m lina"; export PYTHONPATH="$FUENTE/src"; fi
export LINA_CLONADO="$CLONADO"
set +e
if [ "$CON_TTY" = 1 ] && [ "$SI" = 0 ] && [ "$SIMULAR" = 0 ]; then $LINA preparar "${ARGS[@]}" < /dev/tty; else $LINA preparar "${ARGS[@]}"; fi
RC_PREPARAR=$?
set -e
[ "$RC_PREPARAR" = 0 ] || aviso "Algún paso no ha podido completarse (mira arriba). Puedes repetirlo con:  lina preparar"

# ---------------------------------------------------------------- 6. primera configuración
paso "6/6 Primera configuración"
if [ "$SIMULAR" = 1 ]; then printf '  [simulación] abriría la configuración guiada:  lina bienvenida\n'
elif [ "$SIN_BIENVENIDA" = 1 ] || [ "$CON_TTY" = 0 ] || [ "$SI" = 1 ]; then
  aviso "Cuando quieras, termina de configurarla con:  lina bienvenida"
else PYTHONUNBUFFERED=1 "$LINA" bienvenida < /dev/tty || aviso "La configuración guiada no ha terminado: repítela con  lina bienvenida"; fi

# si KDE aún no carga el atajo recién creado, se dice lo último y bien visible (lo importante no se pierde entre los textos largos)
AVISO_FINAL=""
if [ "$SIMULAR" != 1 ]; then
  AVISO="$("$VENV/bin/python" -c "from lina.nucleo import bienvenida as B; a = B.atajo_pendiente(); print(B.texto_atajo_pendiente(a) if a else '')" 2>/dev/null || true)"
  [ -n "$AVISO" ] && AVISO_FINAL="
  ┌─────────────────────────────────────────────────────────────────────
  │  ¡IMPORTANTE!  $AVISO
  └─────────────────────────────────────────────────────────────────────

"
fi

cat <<TEXTO

Listo.
${AVISO_FINAL}  · Configuración guiada (clave, micrófono, voz, permisos):   lina bienvenida
  · Si algo falla:                                            lina doctor
  · Actualizar / desinstalar:                                 lina update   ·   lina uninstall
  · Registro de la instalación:                               ${LOG:-$ESTADO/instalacion.log}
TEXTO
