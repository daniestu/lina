# Arquitectura

```
src/lina/
  __main__.py         comando `lina` (arrancar, pulsar, clave, manos-libres, …)
  nucleo/             el cerebro
    asistente.py        bucle principal: oír → pensar (Gemini) → actuar → hablar
    grupos.py           qué herramientas se le enseñan a la IA según lo que se pide
    herramientas.py     las herramientas y las capas de seguridad (qué es crítico, qué se bloquea)
    ajustes.py          config.toml: ajustes con validación, perfiles de autonomía y `lina config`
    politica.py         reglas de lo crítico (politica.txt) con el perfil de autonomía por encima
    turnos.py           pequeñas reglas sobre qué cuenta como petición nueva y qué como seguimiento
    claves.py           guardar claves sin que se vean ni se dicten
    recetas.py          lo que ya se comprobó que funciona
    diario.py           registro de cambios y «deshacer»
    presupuesto.py      control del gasto de la clave de pago
    comandos.py         palabras y frases con significado fijo (sí/no, cancelar…)
    plataforma.py       distribución, gestor de paquetes e instalación de dependencias
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
