# Arquitectura

```
src/lina/
  __main__.py         comando `lina` (arrancar, pulsar, clave, manos-libres, …)
  nucleo/             el cerebro
    asistente.py        bucle principal: oír → pensar → actuar → hablar (la clase Asistente)
    asistente_mcp.py        └ herramientas externas (servidores MCP)
    asistente_interfaz.py   └ control de programas por interfaz (accesibilidad y visión) y sus recetas
    asistente_ajustes.py    └ probar y aprender ajustes de configuración
    asistente_pantalla.py   └ cuándo se puede mirar la pantalla
    asistente_organizacion.py └ notas, recordatorios, ofimática y lectura de la web
    ia.py               hablar con la IA: Gemini (reintentos, pausas por cuota, topes de gasto), modelo local, búsqueda web
    constantes.py       modelos, tiempos, topes y texto base para la IA
    texto.py            fecha para la IA, números a palabras, limpieza del texto antes de decirlo
    opcionales.py       módulos que, si faltan, no impiden arrancar (presupuesto)
    grupos.py           qué herramientas se le enseñan a la IA según lo que se pide
    declaraciones.py    las herramientas tal como se le describen a la IA (solo datos)
    herramientas.py     el ejecutor de comandos con sus capas de seguridad (confirmaciones, snapshots, deshacer, verificación)
    clasificador.py     qué es de solo lectura, qué lanza un programa, qué es hostil y qué se bloquea siempre (funciones puras)
    papelera.py         los borrados pasan a la papelera; ver, restaurar y vaciar
    documentos.py       documentos de Word, hojas de cálculo, presentaciones y PDF con diseño
    diseno.py           HTML de la IA → PDF (limpieza, navegador o WeasyPrint, cuenta de páginas)
    resolver.py         ajustes de KDE, paquetes del AUR de confianza, fechas relativas y programas que faltan
    ejecucion.py        ejecutar una orden sencilla (sin shell), con o sin permisos de administrador
    registro.py         registro de acciones (con las claves tapadas) y notificaciones
    procesos.py         lanzar programas fuera del servicio de Lina
    ajustes.py          config.toml: ajustes con validación, perfiles de autonomía y `lina config`
    politica.py         reglas de lo crítico (politica.txt) con el perfil de autonomía por encima
    turnos.py           pequeñas reglas sobre qué cuenta como petición nueva y qué como seguimiento
    claves.py           guardar claves sin que se vean ni se dicten
    recetas.py          lo que ya se comprobó que funciona
    diario.py           registro de cambios y «deshacer»
    presupuesto.py      control del gasto de la clave de pago
    comandos.py         palabras y frases con significado fijo (sí/no, cancelar…)
    plataforma.py       distribución (Arch, Debian, Fedora, openSUSE), gestor de paquetes y capacidades del equipo
    rutas.py            carpetas XDG y archivos de fábrica
  voz/                manos libres («Oye Lina»), voces de Piper (`lina voz`) e indicador visual de escucha
  escritorio/         control de programas: accesibilidad (AT-SPI), D-Bus de KDE, visión
  modulos/            sistema, web, notas, oficina, organización, recordatorios, juegos
  mcp/                cliente y servidor MCP (herramientas externas)
  datos/              archivos de fábrica que se copian a ~/.config/lina la primera vez
```

## Carpetas del usuario

| Qué | Dónde |
|---|---|
| Ajustes (`config.toml`), listas editables y claves | `~/.config/lina/` |
| Recetas, diario, gasto, voces | `~/.local/share/lina/` |
| Registro de acciones | `~/.local/state/lina/` |
| Temporales (pid, capturas, audio) | `$XDG_RUNTIME_DIR/lina/` |

Los archivos de fábrica de `datos/` se copian a `~/.config/lina/` la primera vez; a partir de ahí manda la copia del usuario.
