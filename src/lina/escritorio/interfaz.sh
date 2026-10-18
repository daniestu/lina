#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
# Fase 0 del control de programas con la pantalla (pulsar botones, escribir, mover ventanas…) en KDE Plasma 6 + Wayland.
#   lina interfaz diagnostico   → solo mira qué piezas funcionan (no cambia nada, salvo una prueba de ratón de 0 píxeles)
#   lina interfaz preparar      → instala/arregla lo que falte (pide tu contraseña con sudo) y vuelve a diagnosticar
#   lina interfaz estado        → muestra el último diagnóstico guardado
# El resultado queda en ~/.local/share/lina/interfaz_capacidades.txt: el asistente lo leerá para saber qué capas puede usar.
set -u
DATOS="${DATOS_DIR:-$HOME/.local/share/lina}"
SALIDA="$DATOS/interfaz_capacidades.txt"
SUDO="${SUDO_PRUEBA-sudo}"
UID_ACTUAL="$(id -u)"
RUN="${XDG_RUNTIME_DIR:-/run/user/$UID_ACTUAL}"

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
mal()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
aviso(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
paso() { printf '\n\033[1m%s\033[0m\n' "$*"; }
declare -A CAP        # capacidades detectadas: clave → si/no
ARREGLOS=()            # cosas que 'preparar' puede arreglar

marca() { CAP["$1"]="$2"; }
tiene() { command -v "$1" >/dev/null 2>&1; }

# Familia de la distribución (como lina.nucleo.plataforma) y paquetes con el nombre de cada una
FAMILIA="${LINA_DISTRO:-$( . /etc/os-release 2>/dev/null
  for i in ${ID:-} ${ID_LIKE:-}; do case "$i" in
    arch|cachyos|endeavouros|manjaro|garuda|artix) echo arch; break;;
    debian|ubuntu|linuxmint|pop|elementary|zorin|kali|neon) echo debian; break;;
    fedora|rhel|centos|rocky|almalinux|nobara) echo fedora; break;;
    opensuse*|suse|sles) echo suse; break;;
  esac; done )}"
real() {
  case "$FAMILIA:$1" in
    debian:python-gobject) echo python3-gi;;
    fedora:python-gobject|suse:python-gobject) echo python3-gobject;;
    *) echo "$1";;
  esac
}
paquete() {
  local p; p="$(real "$1")"
  case "$FAMILIA" in
    arch) pacman -Qq "$p";;
    debian) dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii';;
    fedora|suse) rpm -q "$p";;
    *) return 1;;
  esac >/dev/null 2>&1
}
instalar_paquetes() {
  local r=() p; for p in "$@"; do r+=("$(real "$p")"); done
  case "$FAMILIA" in
    arch) $SUDO pacman -S --needed --noconfirm "${r[@]}";;
    debian) $SUDO apt-get install -y --no-install-recommends "${r[@]}";;
    fedora) $SUDO dnf install -y "${r[@]}";;
    suse) $SUDO zypper --non-interactive install --no-recommends "${r[@]}";;
    *) echo "  No conozco el gestor de paquetes de esta distribución: instala a mano ${r[*]}"; return 1;;
  esac
}

socket_ydotool() {
  local s
  for s in "${YDOTOOL_SOCKET:-}" "$RUN/.ydotool_socket" /tmp/.ydotool_socket; do
    [ -n "$s" ] && [ -S "$s" ] && { echo "$s"; return; }
  done
}

diagnostico() {
  mkdir -p "$DATOS"
  paso "1. Sesión"
  if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then ok "Wayland"; marca wayland si; else mal "La sesión no es Wayland (${XDG_SESSION_TYPE:-desconocida})"; marca wayland no; fi
  if tiene plasmashell; then ok "Plasma $(plasmashell --version 2>/dev/null | awk '{print $2}')"; marca plasma si; else aviso "No encuentro plasmashell"; marca plasma no; fi

  paso "2. Ventanas (kdotool)"
  if tiene kdotool; then
    local v g
    v="$(kdotool getactivewindow getwindowname 2>/dev/null)"
    g="$(kdotool getactivewindow getwindowgeometry 2>/dev/null | tr '\n' ' ')"
    if [ -n "$v" ]; then ok "kdotool funciona (ventana activa: «$v»${g:+, $g})"; marca ventanas si
    else aviso "kdotool está instalado pero no devuelve la ventana activa (¿lo ejecutas desde una terminal sin ventana enfocada?)"; marca ventanas si; fi
  else mal "Falta kdotool (el asistente ya lo usa para saber qué ventana tienes delante)"; marca ventanas no; fi

  paso "3. Captura de la ventana (spectacle)"
  if tiene spectacle; then
    local f="$DATOS/prueba_captura.png"; rm -f "$f"
    timeout 10 spectacle -b -n -a -o "$f" >/dev/null 2>&1
    if [ -s "$f" ]; then ok "Captura de la ventana activa: $(du -h "$f" | cut -f1)"; marca captura si; else mal "spectacle no ha generado la captura"; marca captura no; fi
    rm -f "$f"
  else mal "Falta spectacle"; marca captura no; fi

  paso "4. Accesibilidad (AT-SPI): leer botones por su nombre, sin coordenadas"
  if busctl --user status org.a11y.Bus >/dev/null 2>&1; then ok "Bus de accesibilidad presente"; marca a11y_bus si
  else mal "No hay bus de accesibilidad (at-spi2-core)"; marca a11y_bus no; paquete at-spi2-core || ARREGLOS+=("at-spi2-core"); fi
  local activo; activo="$(busctl --user get-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled 2>/dev/null | awk '{print $2}')"
  if [ "$activo" = "true" ]; then ok "Accesibilidad activada en la sesión"; marca a11y_activa si
  else aviso "Accesibilidad desactivada en la sesión (los programas no publican sus botones). 'preparar' la activa"; marca a11y_activa no; ARREGLOS+=("a11y_on"); fi
  if python3 -c "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi" >/dev/null 2>&1; then
    ok "Python puede usar AT-SPI"; marca a11y_python si
    local apps
    apps="$(python3 - <<'PY' 2>/dev/null
import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi
d = Atspi.get_desktop(0)
nombres = []
for i in range(d.get_child_count()):
    try:
        nombres.append(d.get_child_at_index(i).get_name() or "?")
    except Exception:
        pass
print(len(nombres), "|", ", ".join(nombres[:12]))
PY
)"
    if [ -n "$apps" ]; then
      local n="${apps%% |*}"
      if [ "${n:-0}" -gt 0 ]; then ok "Programas visibles por accesibilidad ($n): ${apps#*| }"; marca a11y_apps si
      else aviso "AT-SPI funciona, pero ningún programa se ha registrado todavía (abre uno y repite; algunos necesitan reiniciarse tras activar la accesibilidad)"; marca a11y_apps no; fi
    else aviso "No he podido leer la lista de programas por AT-SPI"; marca a11y_apps no; fi
  else
    mal "Python no puede usar AT-SPI (falta python-gobject o at-spi2-core)"; marca a11y_python no
    paquete python-gobject || ARREGLOS+=("python-gobject"); paquete at-spi2-core || ARREGLOS+=("at-spi2-core")
  fi

  paso "5. Pulsar, escribir y mover el ratón (ydotool, entrada virtual)"
  if tiene ydotool; then ok "ydotool instalado"; else mal "Falta ydotool"; ARREGLOS+=("ydotool"); fi
  if [ -e /dev/uinput ]; then
    if [ -w /dev/uinput ]; then ok "/dev/uinput: puedes escribir"; marca uinput si
    else mal "/dev/uinput existe pero tu usuario no puede escribir"; marca uinput no; ARREGLOS+=("uinput_permisos"); fi
  else mal "No existe /dev/uinput (módulo uinput sin cargar)"; marca uinput no; ARREGLOS+=("uinput_modulo"); fi
  local sock; sock="$(socket_ydotool)"
  if [ -n "$sock" ]; then
    ok "Servicio ydotoold en marcha ($sock)"; marca ydotoold si
    if tiene ydotool && YDOTOOL_SOCKET="$sock" timeout 5 ydotool mousemove -x 0 -y 0 >/dev/null 2>&1; then
      ok "Prueba de ratón (0 píxeles) correcta"; marca entrada si
    else mal "ydotoold responde mal a la prueba de ratón"; marca entrada no; fi
  else
    mal "ydotoold no está en marcha"; marca ydotoold no; marca entrada no; ARREGLOS+=("ydotoold_servicio")
  fi

  paso "6. Alternativa: portal de escritorio (pide permiso a ti, sin permisos especiales)"
  if busctl --user introspect org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop 2>/dev/null | grep -q 'org.freedesktop.portal.RemoteDesktop'; then
    ok "Portal RemoteDesktop disponible (plan B para pulsar si ydotool no va)"; marca portal si
  else aviso "Portal RemoteDesktop no disponible"; marca portal no; fi

  paso "7. Navegador y Electron (Discord, VS Code, Steam…)"
  aviso "Estas apps no publican sus botones por accesibilidad salvo que se lancen con --force-renderer-accessibility; el asistente usará visión con ellas."
  marca electron_vision si

  guardar
  resumen
}

guardar() {
  : > "$SALIDA"
  local k
  for k in "${!CAP[@]}"; do echo "$k=${CAP[$k]}"; done | sort >> "$SALIDA"
  echo "fecha=$(date -Iseconds)" >> "$SALIDA"
}

resumen() {
  paso "Resumen"
  local capa_a11y="no" capa_entrada="no"
  [ "${CAP[a11y_python]:-no}" = si ] && [ "${CAP[a11y_activa]:-no}" = si ] && capa_a11y="si"
  [ "${CAP[entrada]:-no}" = si ] && capa_entrada="si"
  [ "$capa_a11y" = si ] && ok "Capa accesibilidad lista (leer y pulsar botones por nombre)" || mal "Capa accesibilidad NO lista"
  [ "$capa_entrada" = si ] && ok "Capa de entrada lista (teclado y ratón virtuales)" || mal "Capa de entrada NO lista"
  [ "${CAP[captura]:-no}" = si ] && [ "${CAP[ventanas]:-no}" = si ] && ok "Capa de visión lista (captura de ventana + dónde está)" || mal "Capa de visión NO lista"
  if [ "${#ARREGLOS[@]}" -gt 0 ]; then
    echo
    echo "Se puede arreglar con:  lina interfaz preparar"
    echo "Pendiente: $(printf '%s\n' "${ARREGLOS[@]}" | sort -u | tr '\n' ' ')"
  else
    echo; echo "Todo listo para la fase 1. Guardado en $SALIDA"
  fi
}

preparar() {
  paso "Preparando (se te pedirá la contraseña una vez)"
  local faltan=()
  for p in ydotool python-gobject at-spi2-core; do paquete "$p" || faltan+=("$p"); done
  if [ "${#faltan[@]}" -gt 0 ]; then
    echo "  Instalo: ${faltan[*]}"
    instalar_paquetes "${faltan[@]}" || { mal "No he podido instalar ${faltan[*]}"; }
  else ok "Paquetes ya instalados"; fi

  # permisos de /dev/uinput para el usuario de la sesión (sin tener que cerrar sesión)
  if [ ! -f /etc/udev/rules.d/80-asistente-uinput.rules ]; then
    echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | $SUDO tee /etc/udev/rules.d/80-asistente-uinput.rules >/dev/null
    ok "Regla de permisos para /dev/uinput creada"
  fi
  echo uinput | $SUDO tee /etc/modules-load.d/asistente-uinput.conf >/dev/null
  $SUDO modprobe uinput 2>/dev/null
  $SUDO udevadm control --reload-rules 2>/dev/null
  $SUDO udevadm trigger --name-match=uinput 2>/dev/null
  sleep 1

  # servicio ydotoold de usuario
  if ! systemctl --user cat ydotool.service >/dev/null 2>&1 && ! systemctl --user cat ydotoold.service >/dev/null 2>&1; then
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/ydotoold.service" <<EOF
[Unit]
Description=ydotoold (entrada virtual para el asistente)

[Service]
ExecStart=$(command -v ydotoold || echo /usr/bin/ydotoold) --socket-path=%t/.ydotool_socket --socket-perm=0600
Restart=on-failure

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    ok "Servicio de usuario ydotoold creado"
  fi
  local srv=ydotool.service
  systemctl --user cat ydotool.service >/dev/null 2>&1 || srv=ydotoold.service
  systemctl --user enable --now "$srv" 2>&1 | tail -1
  sleep 1

  # accesibilidad activada en la sesión (lo mismo que hace un lector de pantalla)
  busctl --user set-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled b true 2>/dev/null \
    && ok "Accesibilidad activada en esta sesión" || aviso "No he podido activar la accesibilidad (se hará desde el asistente)"

  CAP=(); ARREGLOS=()
  diagnostico
  echo
  aviso "Si algún programa que ya estaba abierto no aparece en la lista de accesibilidad, ciérralo y ábrelo otra vez."
}

case "${1:-diagnostico}" in
  diagnostico) diagnostico;;
  preparar)    preparar;;
  estado)      [ -f "$SALIDA" ] && cat "$SALIDA" || echo "Aún no hay diagnóstico: lina interfaz diagnostico";;
  *) sed -n '2,8p' "$0";;
esac
