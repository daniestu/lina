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
    proveedores.py      formato común para hablar con una IA y registro de proveedores
    proveedor_gemini.py Gemini (Google) como proveedor
    resolver.py         ajustes de KDE, paquetes del AUR de confianza, fechas relativas y programas que faltan
    ejecucion.py        ejecutar una orden sencilla (sin shell), con o sin permisos de administrador
    registro.py         registro de acciones (con las claves tapadas) y notificaciones
    procesos.py         lanzar programas fuera del servicio de Lina
    ajustes.py          config.toml: ajustes con validación, perfiles de autonomía y `lina config`
    politica.py         reglas de lo crítico (politica.txt) con el perfil de autonomía por encima
    turnos.py           pequeñas reglas sobre qué cuenta como petición nueva y qué como seguimiento
    fuentes.py          lina fuentes: una web para cada tema, solo las escribe el usuario; usar_fuente y el prompt de R3
    medir_fuentes.py    lina fuentes medir y probar: lo que decidió cómo elegir la fuente, sin ejecutar nada
    claves.py           guardar claves sin que se vean ni se dicten
    recetas.py          lo que ya se comprobó que funciona
    diario.py           registro de cambios y «deshacer»
    presupuesto.py      control del gasto de la clave de pago
    canal.py            lina di: socket Unix con la Lina en marcha (origen «texto»: no confirma ni sube el tope)
    aviso_busqueda.py   avisos de la búsqueda en internet: que falta (una vez), el límite de Tavily (432/433, una vez al mes) y la primera vez con DuckDuckGo o las wikis
    busqueda.py         la escalera de ia.busqueda = auto: Google dentro de Gemini (consulta aparte), Tavily, DuckDuckGo si lo enciendes, Wikipedia y wikis de juegos
    probar_busqueda.py  lina probar-busqueda: 20 preguntas con la Lina de un usuario nuevo, en tres niveles (gratis, tavily, pago)
    comandos.py         palabras y frases con significado fijo (sí/no, cancelar…)
    contenido.py        «ponme el partido…»: busca y elige la ficha en las plataformas oficiales, sin IA
    plataforma.py       distribución (Arch, Debian, Fedora, openSUSE), gestor de paquetes y capacidades del equipo
    rutas.py            carpetas XDG y archivos de fábrica
  voz/                manos libres («Oye Lina»), voces de Piper (`lina voz`), indicador visual de escucha y fin de frase por silencio del atajo (`fin_de_frase.py`, V3)
  escritorio/         control de programas: accesibilidad (AT-SPI), D-Bus de KDE, visión
  modulos/            sistema, web, notas, oficina, organización, recordatorios, juegos
  mcp/                cliente y servidor MCP (herramientas externas)
  datos/              archivos de fábrica que se copian a ~/.config/lina la primera vez
```

## Fuentes: cómo se usa una al responder

1. `asistente._herramienta_de_fuente` ofrece `usar_fuente` si hay fuentes, `fuentes.activas()` (con Gemini, sea cual sea `ia.busqueda`) y la frase no es una orden.
2. La IA elige por significado. `asistente_organizacion.usar_fuente` revisa el id y llama a `ia.comprobar_tema` (R3) con el tema y `pregunta_pura`, por la clave de `presupuesto.claves_para("fuente")`.
3. Si encaja, se busca en el dominio o, sin búsqueda, se lee la dirección guardada; desde ahí `fuente_cerrada` solo deja la web y `_insistir_si_hace_falta` no reintenta. Si no encaja o no contesta, sigue sin decir nada.
4. `turnos.correccion_de_fuente` añade al final lo que la respuesta no reconozca. Cada comprobación queda en `comprobaciones_fuente.jsonl`, y `lina tiempos ia` enseña la regla del 8 %.

## Carpetas del usuario

| Qué | Dónde |
|---|---|
| Ajustes (`config.toml`), listas editables y claves | `~/.config/lina/` |
| Recetas, diario, gasto, voces | `~/.local/share/lina/` |
| Registro de acciones | `~/.local/state/lina/` |
| Temporales (pid, capturas, audio) | `$XDG_RUNTIME_DIR/lina/` |

Los archivos de fábrica de `datos/` se copian a `~/.config/lina/` la primera vez; a partir de ahí manda la copia del usuario.
