# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- Estructura de proyecto con paquete `lina` (`src/`), comando `lina` y datos del usuario en las carpetas estándar XDG
  (`~/.config/lina`, `~/.local/share/lina`, `~/.local/state/lina`).
- Pruebas automáticas (`tests/`) y comprobación de que no se cuelan secretos ni datos personales.

- Cuatro voces en español (`es_MX-claude-high` por defecto, `es_ES-davefx-medium` y dos hablantes de `es_ES-sharvard-medium`),
  descargadas automáticamente la primera vez. Se elige con `lina voz NOMBRE`; el catálogo está organizado por idioma.

- Ajustes en un único archivo, `~/.config/lina/config.toml`, con validación, valores de fábrica y recarga en caliente; `lina config` para verlos y
  cambiarlos. Migra solo lo que había en `activacion.txt`, `voz.txt`, `presupuesto.txt` y `politica.txt` (ver `docs/configuracion.md`).
- Perfiles de autonomía (`autonomo`, `equilibrado`, `prudente`) e interruptores por categoría. Discos, arranque, cuentas, dinero y gasto se confirman siempre.
- Velocidad de la voz ajustable (`voz.velocidad`).

### Corregido

- El resplandor ya no es una ventana a pantalla completa: son cuatro franjas finas en los bordes de cada monitor (y una sola capa si hay pantallas duplicadas). Si el compositor no deja pasar el ratón, solo se bloquean los bordes y no el escritorio.
- El resplandor de escucha ya no debe bloquear el ratón: la zona de entrada se vacía al crear la ventana, al mostrarla y ya mostrada.
- Al abrir un programa, ya no se avisa de que «ha terminado» cuando el usuario cierra su ventana.
- Las recetas solo se guardan si al final se da por cumplido lo pedido, y describen la petición original (no una queja como «No lo has hecho»).
- Una respuesta que afirma algo habiendo cargado herramientas pero sin hacer ni leer nada del equipo se revisa a fondo.

### Cambiado
- El asistente pasa a llamarse **Lina** (palabra de activación por defecto: «Lina»; el nombre es configurable).
