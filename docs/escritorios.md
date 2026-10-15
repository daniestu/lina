# Escritorios compatibles

Lina necesita tres cosas del escritorio: saber **qué ventana tienes delante** (para entender si estás en un juego, en una terminal o en el navegador),
**capturar la pantalla** (solo con tu permiso) y usar el **portapapeles**. Cada escritorio las ofrece de forma distinta, así que Lina detecta el tuyo
(`lina escritorio` te lo cuenta) y usa el primer método que funciona. Si ninguno funciona, **lo dice** y no finge: la IA recibe esa misma información
y sabe qué no puede hacer en tu equipo.

## Qué funciona en cada escritorio

| Escritorio | Ventana activa | Captura | Portapapeles | Atajo global (`lina atajo`) |
|---|---|---|---|---|
| **KDE Plasma** (Wayland) | `kdotool` | `spectacle` | `wl-clipboard` | automático |
| **KDE Plasma** (X11) | `kdotool` / `xdotool` | `spectacle`, `scrot` | `xclip` | automático |
| **GNOME** (Wayland) | solo programas X11/XWayland (`xdotool`)* | `gnome-screenshot` | `wl-clipboard` | automático |
| **GNOME** (X11) | `xdotool` | `gnome-screenshot`, `scrot` | `xclip` | automático |
| **Cinnamon** | `xdotool` | `gnome-screenshot`, `scrot` | `xclip` | automático |
| **XFCE** (X11) | `xdotool` | `xfce4-screenshooter`, `scrot` | `xclip` | automático |
| **sway** / **Hyprland** | `swaymsg` / `hyprctl` | `grim` (recorta a la ventana activa) | `wl-clipboard` | te da la línea para tu configuración |
| MATE, LXQt, COSMIC y otros | `xdotool` (X11) | según sesión | según sesión | te explica cómo crearlo a mano |

\* GNOME no deja leer las ventanas de programas Wayland nativos. Lina ve juegos de Steam, Electron y demás programas X11, y lo dice con un aviso; en el resto
puede no saber qué ventana tienes delante (entonces trata la petición como «general», sin más).

Las herramientas de captura que solo ven X11 (`scrot`, `maim`, `import`) **no se usan en Wayland**: darían una imagen negra y se enviaría a la IA como si fuera tu
pantalla. En Wayland, o hay un programa de captura de Wayland o Lina dice que no puede ver la pantalla.

## Qué se instala

`install.sh` añade a los paquetes del sistema solo lo que falta **para tu escritorio** (`xdotool`, `xclip`, `grim`, `wl-clipboard`, `gnome-screenshot`…, con el
nombre que tenga en tu distribución). `lina doctor` te dice qué falta y la orden exacta. Esta lista no obliga a nada: sin esos programas Lina funciona, pero sin
esa función.

## Gestión de ventanas por voz

«Cierra Firefox», «minimiza el terminal», «mueve la ventana»: en **KDE** hay todo (maximizar, mosaicos, escritorios virtuales, monitores). En **X11** con `xdotool`:
listar, enfocar, cerrar, minimizar, mover y cambiar el tamaño. Maximizar, mosaicos, escritorios y monitores usan atajos de KWin y por ahora son solo de KDE; en otros
escritorios Lina contesta eso en vez de intentarlo. En **sway** y **Hyprland** y en **GNOME con Wayland** todavía no gestiona ventanas.

## El resplandor de escucha

Se dibuja en una capa por encima de todo (`gtk-layer-shell`) en KDE, sway, Hyprland y la mayoría de compositores Wayland. **GNOME no admite capas**: allí el
resplandor puede no verse y es el pitido de inicio y fin el que te avisa. En X11 es una ventana transparente que necesita un compositor con transparencia.

## Qué es solo de KDE

Los ajustes de Plasma (`kwriteconfig`), el D-Bus de KWin y las acciones de menú de los programas de KDE. En otros escritorios la IA recibe el aviso de que no valen
y usa lo que sí hay (comandos normales, el servidor MCP, `interfaz` por accesibilidad).

## Qué no se ha podido probar todavía

Todo lo de esta página está cubierto con pruebas que simulan las órdenes de cada escritorio (qué se ejecuta y qué se hace con la respuesta), pero **solo KDE Plasma con
Wayland está comprobado en un equipo real**. Si usas otro y algo no responde como dice la tabla, `lina doctor --informe` genera un texto sin datos personales para
abrir una incidencia; es la mejor ayuda para cerrar esta lista.
