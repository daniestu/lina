# Cómo se usa Lina

## Hablarle

- **Con el atajo** (`Meta+Espacio` en KDE, `Ctrl+Alt+Espacio` en GNOME): lo pulsas, hablas y lo vuelves a pulsar. Pulsarlo mientras habla la calla.
  Si prefieres pulsar **una sola vez**, `lina config poner activacion.fin_por_silencio true`: deja de escucharte cuando te quedas callado un segundo
  (`activacion.silencio_atajo`), con el mismo pitido de siempre, y la segunda pulsación sigue valiendo para terminar antes. Viene apagado: tarda casi un
  segundo más que pulsar, y con música alta puede no oír que has callado (entonces pulsas, o para sola a los 60 s).
  `lina tiempos escucha` te dice, con tu uso real, cuántas veces cortó solo, cuántas acabaste pulsando y si te cortó a destiempo (guarda solo el modo de
  terminar, el día y tiempos; nunca audio ni texto).
- **Sin manos**: «Oye Lina, …» (el nombre lo eliges tú). No escucha mientras juegas, salvo que se lo pidas. Se prueba con `lina manos-libres probar "oye lina abre firefox"`.
- Si le dices algo mientras trabaja, te escucha igualmente: «para» o «cancela eso» lo dejan; otra cosa distinta, la atiende en lugar de lo anterior.

Lina entiende la intención, no frases fijas. Estos ejemplos son solo orientativos.

## Qué puedes pedirle

| Para | Ejemplos |
|---|---|
| Programas y ventanas | «abre Firefox», «pon Dolphin a pantalla completa», «cierra esta ventana» |
| Sistema | «sube el volumen», «¿qué proceso gasta más CPU?», «conéctate al Wi-Fi de casa», «cambia la resolución del monitor» |
| Ajustes de KDE | «activa la luz nocturna», «pon el tema oscuro», «cambia el tamaño de la letra» |
| Juegos | «pon MangoHud en este juego», «qué opciones de lanzamiento tiene este juego en Steam» |
| Documentos | «hazme un currículum en PDF», «una factura para…», «prepárame un Excel con estos gastos», «copia esto al portapapeles» |
| Web | «resume esta página» (la que tienes copiada o la que le digas) |
| Notas y recordatorios | «apunta que el wifi es…», «¿qué tenía apuntado de la compra?», «avísame en 20 minutos» |
| Mirar la pantalla | «¿qué significa este error?», «¿dónde pulso para…?» (solo si permites las capturas: `lina privacidad`) |
| Manejar programas por su interfaz | «pulsa Siguiente», «marca la casilla…» (requiere `lina interfaz preparar`) |
| Sobre ella misma | «¿qué puedes hacer?», «cámbiate la voz», «llámate Jarvis», «¿cuánto he gastado de Gemini?» |
| Corregirla | «cuando oigas cait quiero decir Kate» (para lo que oye mal; solo con el atajo), «olvida el alias cait» |

## Tus fuentes: una web para cada tema

Puedes decirle a Lina qué web usar para un tema concreto, por ejemplo las recetas de refinería de un juego. Para lo demás, aunque sea del mismo juego, seguirá buscando como siempre.

**Añadir una fuente**, solo con el atajo, con `lina di` o en la terminal. Por «Oye Lina» se niega, por si lo dijera otra voz:

- «para las recetas de refinería usa esta web: nomanssky punto fandom punto com»
- Copia la dirección y di «para las recetas de refinería usa la página que tengo copiada», o «añade la fuente que tengo en el portapapeles a recetas de refinería». El portapapeles solo se mira si lo pides, con el atajo, y lo copiado no se repite.
- `lina fuentes añadir "recetas de refinería" https://…`

Guardar una fuente **no pide confirmación previa**. Lina te avisa después, con el dominio deletreado («nomanssky punto fandom punto com»), y si no es lo que querías se deshace con «quita la última fuente». Escucha ese dominio: es la forma de notar que lo copiado no era lo que creías. Solo se deletrea el dominio: una página distinta de esa misma web no se notaría, y se comprueba con `lina fuentes`. Si falta la web o el tema, te lo pide. Puedes guardar hasta 20.

**Quitar una fuente:** «quita la última fuente», «quita la fuente de recetas», «quita f3», «quita las fuentes f3 y f4» o «quita todas las fuentes» (esta te pide «sí» antes), por voz con el atajo o con `lina di`; por manos libres no. Si varias encajan, no quita ninguna y te las dice. Por terminal, `lina fuentes quitar f1`, y todas con `lina fuentes quitar todas`. `lina olvidar fuentes` también las borra. `lina fuentes` enseña la lista.

**Cómo elige Lina.** Cuando le preguntas algo, la IA decide por significado si va de uno de tus temas, aunque uses otras palabras. Después, una comprobación aparte mira solo el tema y tu pregunta, y si no es exactamente de ese tema no se usa la fuente. Si esa comprobación no contesta a tiempo, tampoco, y Lina sigue con la búsqueda general sin decírtelo. Para consultarla no hace falta nombrarla, aunque también puedes: «usa la fuente de recetas». `lina fuentes probar "tu pregunta"` enseña qué fuente elegiría y si la comprobación la aceptaría, sin responder ni buscar.

**Si la fuente no tiene la respuesta,** Lina no te pregunta: sigue con la búsqueda general y te dice que en tu web no estaba y de dónde sale lo demás. Si tu web no se puede leer y no hay búsqueda, te lo dice y termina, sin insistir ni probar otras vías, y no te contesta de memoria como si fuera un dato. Si te contesta algo como si fuera de tu web y no lo es, añade una corrección.

**Preguntas de seguimiento.** La comprobación solo ve la frase que acabas de decir. Algo como «¿y con carbono?» puede ir a la búsqueda general aunque siga siendo tu tema. Si quieres asegurarte de que use tu fuente, repite el tema en la pregunta.

**En qué configuraciones funciona.** Con Gemini y con `ia.busqueda` en `tavily` o `ninguna`:

| `ia.busqueda` | Qué hace con tu fuente |
|---|---|
| `tavily` con clave | Busca dentro de esa web (con DuckDuckGo si Tavily no responde) |
| `tavily` sin clave, con `busqueda_reserva` activa | Busca dentro de esa web con DuckDuckGo; si no encuentra nada, lee la dirección que guardaste |
| `tavily` sin clave y `busqueda_reserva` apagada, o `ninguna` | Lee solo la dirección que guardaste, sin buscar: guarda la página concreta. Si guardas la portada, Lina te avisa |
| `google` | No se usan |

Con otro proveedor de IA tampoco se usan, porque no está medido. `lina fuentes` te avisa si es tu caso. Lo que sale de tu equipo está en el [manual de privacidad](privacidad.md).

## Cómo te pide permiso

- Lo que cambia el sistema queda **pendiente** y Lina te lo dice en una pregunta («voy a instalar X, ¿lo hago?»). Según el perfil que elijas
  (`lina config perfil autonomo|equilibrado|prudente`) pide confirmación para más o menos cosas.
- Responder «sí» o «no» por voz vale para lo corriente. Lo **crítico** (borrar de verdad, discos, arranque, software de fuera, subir el tope de gasto,
  cambiar de proveedor de IA) solo se confirma con el atajo, nunca por voz.
- Borrar mueve a la papelera, salvo que digas «definitivamente». Todo lo que cambia queda en un diario y se puede deshacer.

## Ajustes que querrás tocar

```sh
lina config                          # todos los ajustes
lina config poner asistente.nombre Jarvis
lina config perfil prudente
lina voz                             # voces disponibles
lina ia                              # con qué IA habla
lina privacidad                      # qué se envía y si se envían capturas
lina doctor                          # si algo no va
lina di "¿qué tiempo hace?"           # decirle algo por escrito; la respuesta sale en la terminal (--voz: también en voz alta)
```

Con `lina di` lo que pide confirmación no se confirma: queda pendiente hasta que pulses el atajo y digas «sí» (ver [seguridad](seguridad.md)).

Más en [configuración](configuracion.md), [proveedores de IA](proveedores-ia.md), [idiomas](idiomas.md) y [seguridad](seguridad.md).
