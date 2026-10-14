#!/usr/bin/env bash
# Instalador de Lina (versión inicial: Arch Linux y derivados; el resto de distribuciones llegan en la Fase 3).
#   ./install.sh             instala o actualiza
#   ./install.sh --simular   dice qué haría, sin tocar nada
#   ./install.sh --quitar    desinstala el servicio y el comando (no borra tus ajustes ni tus datos)
set -euo pipefail

SIMULAR=0; QUITAR=0
for a in "$@"; do
  case "$a" in
    --simular) SIMULAR=1 ;;
    --quitar) QUITAR=1 ;;
    -h|--help) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $a" >&2; exit 2 ;;
  esac
done

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}/lina"
CONFIG_SYSTEMD="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV="$DATOS/venv"
BIN="$HOME/.local/bin"

paso() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
aviso(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
fallo(){ printf '  \033[31m✘\033[0m %s\n' "$*" >&2; exit 1; }
hacer(){ if [ "$SIMULAR" = 1 ]; then printf '  [simulación] %s\n' "$*"; else "$@"; fi; }

[ "$(id -u)" -ne 0 ] || [ "${LINA_PERMITIR_ROOT:-0}" = 1 ] || fallo "No lo ejecutes como administrador: Lina se instala para tu usuario (pedirá sudo solo si hace falta)."

if [ "$QUITAR" = 1 ]; then
  paso "Quitando Lina"
  hacer systemctl --user disable --now lina.service 2>/dev/null || true
  hacer rm -f "$CONFIG_SYSTEMD/lina.service" "$BIN/lina"
  hacer systemctl --user daemon-reload
  ok "Servicio y comando quitados. Tus ajustes (~/.config/lina) y datos ($DATOS) siguen ahí."
  exit 0
fi

paso "1/5 Comprobando el sistema"
command -v python3 >/dev/null || fallo "Falta Python 3."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fallo "Hace falta Python 3.11 o superior (tienes $(python3 -V 2>&1))."
ok "$(python3 -V)"
ID_LIKE=""; ID=""
[ -r /etc/os-release ] && . /etc/os-release
FAMILIA="otra"
case " ${ID:-} ${ID_LIKE:-} " in *" arch "*) FAMILIA="arch" ;; esac
if [ "$FAMILIA" = "arch" ]; then ok "Arch Linux o derivado (${PRETTY_NAME:-$ID})"
else aviso "Distribución no probada todavía (${PRETTY_NAME:-desconocida}). Seguiré, pero instala a mano portaudio y libnotify si algo falla."; fi
[ -n "${XDG_SESSION_TYPE:-}" ] && ok "Sesión: ${XDG_SESSION_TYPE}, escritorio: ${XDG_CURRENT_DESKTOP:-?}"

paso "2/5 Paquetes del sistema"
if [ "$FAMILIA" = "arch" ]; then
  FALTAN=()
  for p in python portaudio libnotify; do pacman -Qq "$p" >/dev/null 2>&1 || FALTAN+=("$p"); done
  if [ "${#FALTAN[@]}" -gt 0 ]; then
    echo "  Instalo: ${FALTAN[*]} (pedirá tu contraseña de administrador)"
    hacer sudo pacman -S --needed --noconfirm "${FALTAN[@]}"
  else ok "ya estaban"; fi
else
  aviso "Salto este paso en esta distribución."
fi

paso "3/5 Entorno de Python y Lina"
hacer mkdir -p "$DATOS"
[ -d "$VENV" ] || hacer python3 -m venv "$VENV"
hacer "$VENV/bin/pip" install --quiet --upgrade pip
hacer "$VENV/bin/pip" install --quiet -e "$AQUI"
ok "Lina instalada en $VENV (modo editable: un «git pull» la actualiza)"

paso "4/5 Comando y servicio"
hacer mkdir -p "$BIN" "$CONFIG_SYSTEMD"
hacer ln -sf "$VENV/bin/lina" "$BIN/lina"
case ":$PATH:" in *":$BIN:"*) ok "lina está en el PATH" ;; *) aviso "$BIN no está en tu PATH: añádelo para poder usar «lina pulsar»." ;; esac
if [ "$SIMULAR" = 1 ]; then
  printf '  [simulación] escribiría %s/lina.service\n' "$CONFIG_SYSTEMD"
else
  cat > "$CONFIG_SYSTEMD/lina.service" <<UNIDAD
[Unit]
Description=Lina, asistente de voz
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
ExecStart=$VENV/bin/lina
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
UNIDAD
  systemctl --user daemon-reload
  systemctl --user enable lina.service >/dev/null 2>&1
fi
ok "Servicio de usuario lina.service"

paso "5/5 Arrancando"
hacer systemctl --user restart lina.service
ok "Lina arrancada"

cat <<TEXTO

Listo. Quedan dos cosas, una sola vez:
  1. Crea un atajo de teclado global (por ejemplo Meta+Espacio) que ejecute:   lina pulsar
  2. Guarda tu clave de Gemini (gratis en https://aistudio.google.com/apikey) en  ~/.config/lina/gemini.key

Registro:  journalctl --user -u lina -f
TEXTO
