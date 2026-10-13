# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- Estructura de proyecto con paquete `lina` (`src/`), comando `lina` y datos del usuario en las carpetas estándar XDG
  (`~/.config/lina`, `~/.local/share/lina`, `~/.local/state/lina`).
- Pruebas automáticas (`tests/`) y comprobación de que no se cuelan secretos ni datos personales.

- Voz por defecto `es_ES-mls_10246-low`, descargada automáticamente la primera vez; se cambia con `~/.config/lina/voz.txt`.

### Cambiado
- El asistente pasa a llamarse **Lina** (palabra de activación por defecto: «Lina»; el nombre es configurable).
