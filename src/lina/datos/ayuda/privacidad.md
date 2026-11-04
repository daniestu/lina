# Privacidad: qué sale de tu equipo y qué no

Lina no tiene telemetría: no envía estadísticas ni datos de uso a nadie. Lo único que sale del equipo es lo que hace falta para contestarte.

## Qué se envía a la IA (Gemini, de Google, salvo que cambies de proveedor)

- **Lo que dices, en texto.** Tu voz se convierte en texto en tu propio equipo (Whisper); el audio no se envía a ningún sitio.
- **La conversación en curso** (tus últimas preguntas y mis respuestas), para que podamos seguir hablando de lo mismo.
- **El nombre de la ventana activa y su programa**, para saber de qué hablas.
- **Capturas de tu pantalla, solo si lo permites** (`lina privacidad si`) y solo cuando hacen falta: en un juego, si hablas de lo que ves, o si la IA lo pide.
  Nunca con el **modo privado** activado, ni con ventanas **sensibles** (bancos, facturación, gestores de contraseñas…), ni mientras no hayas decidido.
- **El resultado de las órdenes y herramientas** que la IA usa para ayudarte (por ejemplo, la lista de programas instalados o el texto de una página que le pides leer).
- Si has puesto una clave de **Tavily**, el texto de cada búsqueda web, que se envía a Tavily. Puede incluir lo que preguntas o el nombre de un programa o juego que tengas abierto; a Tavily no le llegan tu voz, capturas de pantalla ni archivos.

## Adónde va cada búsqueda en internet (`ia.busqueda`)

Con `auto`, lo de fábrica, Lina prueba en este orden y se queda con lo primero que dé resultados. En todos los casos solo sale **el texto de la búsqueda**: nunca tu voz, capturas ni archivos.

1. **Google, dentro de Gemini**, si tienes clave de pago con saldo en tu tope (o una clave de Gemini que sí pueda buscar: en las pruebas, la gratuita no ha podido). Es una consulta aparte a Google, que ya recibe tus preguntas. Con la de pago, pasadas las búsquedas gratuitas del mes, cuesta dinero y cuenta en tu tope.
2. **Tavily**, si tienes clave.
3. **DuckDuckGo**, solo si lo enciendes (`lina config poner ia.busqueda_reserva true`). Está apagado de fábrica porque es poco fiable: suele tomar a los programas por robots y entonces no da nada. DuckDuckGo ve el texto de la búsqueda y tu dirección IP. Lina no se hace pasar por un navegador para evitar su bloqueo. La primera vez que se usa, te lo dice.
4. **Wikipedia y algunas wikis de juegos** (Fandom, minecraft.wiki, wiki.gg, bg3.wiki, WikiDex), con su buscador, sin clave. Ven el texto de la búsqueda y tu dirección IP. Solo se usan para lo enciclopédico (no para precios, noticias, el tiempo ni resultados). Lina pide también, a su API, el extracto de la primera página encontrada, cuyo texto llega a la IA. La primera vez que se usan, te llega una notificación.

Con `tavily` solo se usa Tavily (y DuckDuckGo si lo enciendes); con `google`, solo la de Gemini (y DuckDuckGo si lo enciendes); con `ninguna`, nada, salvo que digas «búscalo igualmente», que busca como `auto` solo en esa petición.

- Si guardas **fuentes** (una web para un tema) y usas Gemini, lo siguiente:
  - **A Gemini:** la lista de tus temas en cada petición que pueda usarlas, y cuando la IA elige una, una consulta más con solo ese tema y tu pregunta. Esa consulta va por tu clave de pago si la tienes y queda saldo de tu tope; si no, por la gratuita. Lo que traiga la web también le llega a la IA.
  - **A Tavily o DuckDuckGo:** el texto de la búsqueda y el dominio de tu fuente, para buscar solo ahí. DuckDuckGo solo se usa si lo has encendido (`busqueda_reserva`) y Tavily no responde o no hay clave.
  - **Con `ia.busqueda` en `auto` o `tavily` sin clave de Tavily y `busqueda_reserva` encendida:** tu consulta va a DuckDuckGo, limitada a esa web. Si no encuentra nada, se descarga la página guardada, como en el caso siguiente.
  - **Con `ia.busqueda` en `ninguna` o `google`, o sin clave de Tavily y con `busqueda_reserva` apagada (lo de fábrica):** no se usa ningún buscador para tu fuente. Tu equipo descarga directamente la página guardada, así que **esa web ve tu dirección IP**, y su texto se envía a la IA.

## Qué NO se envía

- Tus grabaciones de voz.
- Tus claves y contraseñas (las guarda el llavero del sistema; la IA no puede leerlas ni se imprimen en el registro).
- Tus archivos, a no ser que me pidas algo que exija leer uno (entonces solo lo que se lee para esa tarea).
- Capturas de pantalla en modo privado, con ventanas sensibles o sin tu permiso.

## Qué hace el modo privado

Se activa con «activa el modo privado» y se quita solo con el atajo, diciendo «quita el modo privado». La IA puede activarlo, pero no quitarlo. Se recuerda aunque reinicies.

**Mientras está activo:**

- No se hace ni se envía ninguna captura de tu pantalla, y la IA no puede pedirla.
- No atiendo «Oye Lina»: solo te escucho con el atajo.
- No se conserva lo que acaba de pasar (ver más abajo), y al activarlo se borra lo que hubiera.
- No puedo probar ajustes de KDE que haya que comprobar mirando el panel.

**Lo que NO cambia. No es un modo de incógnito:**

- Lo que dices se sigue enviando a la IA en texto, con la conversación en curso, el nombre de la ventana activa y el resultado de las herramientas.
- Las búsquedas se siguen enviando adonde toque (Google dentro de Gemini, Tavily, DuckDuckGo si lo encendiste, Wikipedia y las wikis de juegos).
- Lo que ya estaba en la conversación sigue ahí: activarlo no la borra.
- Sigue guardándose lo demás: el registro (también tus preguntas, si `privacidad.registrar_preguntas` está activo), el registro de acciones, el diario de cambios, las recetas que aprendo, los tiempos y lo que me pidas recordar, y sigo usando esos recuerdos.

## Qué dice Google de lo que recibe

Con la clave **gratuita**, según las condiciones de Google vigentes, lo que se envía puede usarse para mejorar sus productos y puede ser revisado por personas; con una clave **de pago** no. Compruébalo en las condiciones de la API de Gemini antes de enviar nada que no quieras compartir. Si trabajas con información confidencial, usa la clave de pago, un proveedor que cumpla lo que tu empresa exige o el modo privado.

## Qué guarda Lina en tu equipo

| Qué | Dónde | Cómo borrarlo |
|---|---|---|
| Diario de cambios y copias para deshacer | `~/.local/share/lina/diario` | `lina olvidar diario` |
| Registro de acciones (órdenes ejecutadas) | `~/.local/state/lina/acciones.log` (rota solo al llegar a ~1 MB) | `lina olvidar acciones` |
| Lo que me pides recordar («recuerda que…»; solo lo escribes tú, con el atajo, nunca la IA ni Lina por su cuenta, y nunca contraseñas ni claves; a la IA solo le llega lo que viene al caso de cada petición) | `~/.local/share/lina/memoria.json` | `lina memoria` (verlo y borrar uno), `lina olvidar memoria` |
| Las webs que eliges para cada tema (`lina fuentes`; solo las escribes tú, nunca la IA; se usan al responder, como se explica arriba) | `~/.local/share/lina/fuentes.json` (solo lo puedes leer tú) | `lina fuentes quitar`, `lina olvidar fuentes` |
| Recetas aprendidas (lo que ya me pediste y salió bien: la frase, los pasos y cómo se comprobó; nunca contraseñas) | `~/.local/share/lina/recetas.json` | `lina olvidar recetas` o `lina recetas borrar todas` |
| Tiempos de cada petición (solo números, nunca lo que dices; `lina tiempos` los resume) | `~/.local/state/lina/tiempos.jsonl` (se recorta solo al llegar a ~200 KB) | `lina olvidar tiempos` |
| Cómo termina cada escucha del atajo (por silencio, por tu pulsación…), con el día sin hora y tiempos; nunca audio ni texto (`lina tiempos escucha`) | `~/.local/state/lina/escuchas.jsonl` (últimas 5000) | `lina olvidar tiempos` |
| Tokens y duración de cada llamada a la IA, con el modelo, su motivo (normal, reintento…), el día sin hora y una huella del principio fijo (para saber si la caché se aprovecha); nunca lo que preguntas ni lo que contesta (`lina tiempos ia`) | `~/.local/state/lina/llamadas_ia.jsonl` (últimas 5000) | `lina olvidar tiempos` |
| Cómo acabó cada comprobación de que una pregunta es del tema de una fuente: si es uso real o `lina fuentes probar`, encaja o no, intentos, segundos, el día sin hora y si usó la clave de pago; nunca el tema ni la pregunta (`lina tiempos ia`) | `~/.local/state/lina/comprobaciones_fuente.jsonl` | `lina olvidar tiempos` |
| Registro del sistema (lo que dices y contesto, si no lo desactivas) | `journalctl --user -u lina` | `lina olvidar registro` |

Para que lo que dices y contesto no quede en el registro: `lina config poner privacidad.registrar_preguntas false`.
Las grabaciones y capturas temporales viven en la carpeta de ejecución de tu sesión (memoria) y desaparecen al cerrar la sesión; cada captura, además, se borra en cuanto termina la petición. Solo se hace una captura si se podrá usar: nunca en modo privado, sin tu permiso o con una ventana sensible; en un juego, al pulsar el atajo; fuera de un juego, después de hablar y solo si lo que dices lo pide, y solo si sigue delante la misma ventana (en los escritorios que no dicen qué ventana está activa, como GNOME en Wayland sin xdotool, se hace al pulsar, como antes).

## Cómo decidirlo

```
lina privacidad          lo explica y te pregunta
lina privacidad si       permito las capturas cuando hagan falta
lina privacidad no       nunca capturas
```

La IA no puede cambiar esta decisión sola: la tomas tú. Si dejaste «preguntar» y para lo que le pides Lina necesita ver tu pantalla, te lo pedirá ella
(explicando que la captura va a Google) y solo se activa si lo confirmas pulsando el atajo; con la voz de manos libres no vale. Si dijiste «no», no
insiste: solo lo cambias tú en una terminal.

Lo que acaba de pasar (tu frase, las herramientas usadas con su resultado y la respuesta de las últimas 4 peticiones) se guarda solo en memoria durante 15 minutos, para contestarte si preguntas qué ha ocurrido, y entonces se envía a la IA. En **modo privado** no se guarda nada de esto, y al activarlo se borra lo que hubiera.
