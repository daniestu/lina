# Privacidad: qué sale de tu equipo y qué no

Lina no tiene telemetría: no envía estadísticas ni datos de uso a nadie. Lo único que sale del equipo es lo que hace falta para contestarte.

## Qué se envía a la IA (Gemini, de Google, salvo que cambies de proveedor)

- **Lo que dices, en texto.** Tu voz se convierte en texto en tu propio equipo (Whisper); el audio no se envía a ningún sitio.
- **La conversación en curso** (tus últimas preguntas y mis respuestas), para que podamos seguir hablando de lo mismo.
- **El nombre de la ventana activa y su programa**, para saber de qué hablas.
- **Capturas de tu pantalla, solo si lo permites** (`lina privacidad si`) y solo cuando hacen falta: en un juego, si hablas de lo que ves, o si la IA lo pide.
  Nunca con el **modo privado** activado, ni con ventanas **sensibles** (bancos, facturación, gestores de contraseñas…), ni mientras no hayas decidido.
- **El resultado de las órdenes y herramientas** que la IA usa para ayudarte (por ejemplo, la lista de programas instalados o el texto de una página que le pides leer).
- Si has puesto una clave de **Tavily**, el texto de las búsquedas web que haces.

## Qué NO se envía

- Tus grabaciones de voz.
- Tus claves y contraseñas (las guarda el llavero del sistema; la IA no puede leerlas ni se imprimen en el registro).
- Tus archivos, a no ser que me pidas algo que exija leer uno (entonces solo lo que se lee para esa tarea).
- Capturas de pantalla en modo privado, con ventanas sensibles o sin tu permiso.

## Qué dice Google de lo que recibe

Con la clave **gratuita**, según las condiciones de Google vigentes, lo que se envía puede usarse para mejorar sus productos y puede ser revisado por personas; con una clave **de pago** no. Compruébalo en las condiciones de la API de Gemini antes de enviar nada que no quieras compartir. Si trabajas con información confidencial, usa la clave de pago, un proveedor que cumpla lo que tu empresa exige o el modo privado.

## Qué guarda Lina en tu equipo

| Qué | Dónde | Cómo borrarlo |
|---|---|---|
| Diario de cambios y copias para deshacer | `~/.local/share/lina/diario` | `lina olvidar diario` |
| Registro de acciones (órdenes ejecutadas) | `~/.local/state/lina/acciones.log` (rota solo al llegar a ~1 MB) | `lina olvidar acciones` |
| Recetas aprendidas | `~/.local/share/lina/recetas.json` | `lina olvidar recetas` |
| Tiempos de cada petición (solo números, nunca lo que dices; `lina tiempos` los resume) | `~/.local/state/lina/tiempos.jsonl` (se recorta solo al llegar a ~200 KB) | `lina olvidar tiempos` |
| Registro del sistema (lo que dices y contesto, si no lo desactivas) | `journalctl --user -u lina` | `lina olvidar registro` |

Para que lo que dices y contesto no quede en el registro: `lina config poner privacidad.registrar_preguntas false`.
Las grabaciones y capturas temporales viven en la carpeta de ejecución de tu sesión (memoria) y desaparecen al cerrar la sesión.

## Cómo decidirlo

```
lina privacidad          lo explica y te pregunta
lina privacidad si       permito las capturas cuando hagan falta
lina privacidad no       nunca capturas
```

La IA no puede cambiar esta decisión sola: la tomas tú. Si dejaste «preguntar» y para lo que le pides Lina necesita ver tu pantalla, te lo pedirá ella
(explicando que la captura va a Google) y solo se activa si lo confirmas pulsando el atajo; con la voz de manos libres no vale. Si dijiste «no», no
insiste: solo lo cambias tú en una terminal.
