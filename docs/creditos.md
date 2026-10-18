# Créditos y licencias de terceros

## Voces

Lina usa el motor de voz [Piper](https://github.com/rhasspy/piper) y las voces del repositorio
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices). Las voces no se distribuyen con este repositorio: Lina descarga
la que se elige a `~/.local/share/lina/voces/` la primera vez que la necesita.

| Voz | Datos de entrenamiento | Licencia de los datos |
|---|---|---|
| `es_MX-claude-high` (por defecto) | [HirCoir/Piper-TTS-Spanish](https://huggingface.co/spaces/HirCoir/Piper-TTS-Spanish) | Apache-2.0 |
| `es_ES-sharvard-medium-1`, `-2` | Corpus Sharvard, Universidad de Edimburgo ([DataShare](https://datashare.ed.ac.uk/handle/10283/574)) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |

- **Sharvard** exige atribución: *Corpus Sharvard, Universidad de Edimburgo; artículo de referencia:
  [doi:10.3109/14992027.2014.907507](https://www.tandfonline.com/doi/abs/10.3109/14992027.2014.907507)*. Es un modelo de dos hablantes.
- **Claude**: se mantiene el aviso de Apache-2.0 y se reconoce a HirCoir como origen de los datos.
- `sharvard` se afinó a partir de la voz inglesa *lessac* (calidad media), cuyos datos son solo para investigación. No sabemos si esa restricción pasa a la voz derivada ni es asesoramiento legal: se mantiene como excepción consciente de la beta (es de las pocas voces de España con calidad media) y se sustituirá por una entrenada desde cero cuando exista. `davefx` se retiró por la misma razón y porque no gustó.
- Cada voz tiene su ficha (`MODEL_CARD`) en su carpeta del repositorio de voces.

### Voces inglesas (experimental)

| Voz | Datos de entrenamiento | Licencia de los datos | Entrenamiento |
|---|---|---|---|
| `en_US-ljspeech-high` (por defecto en inglés) | [LJ Speech](https://keithito.com/LJ-Speech-Dataset/), Keith Ito | Dominio público | Desde cero |
| `en_US-bryce-medium` | Voz grabada por su autor, Bryce Beattie ([detalles](https://brycebeattie.com/files/tts/)) | Dominio público | Afinada a partir de una voz suya no publicada |

Comprobado el 2026-10-18 en las fichas (`MODEL_CARD`) de cada voz y en la página del dataset. El modelo de `bryce` parte de una voz del propio autor que no se ha
publicado, así que su origen exacto no se puede verificar; la ficha no la relaciona con ningún corpus con restricciones.

**Voces descartadas, y por qué.** La licencia de los datos de *Lessac* (Blizzard 2013, CSTR) es solo para investigación, sin uso comercial ni redistribución. Muchas voces
de Piper se afinaron a partir de ella: `amy`, `hfc_female`, `hfc_male` (además CC BY-NC-SA), `arctic`, `libritts_r` y `joe`. No sabemos si la restricción pasa a las voces
derivadas y no es asesoramiento legal, así que no se incluyen. `ryan` se descarta por ser CC BY-NC-SA. Regla para añadir una voz de cualquier idioma: **calidad media como
mínimo (alta si existe), entrenada desde cero o a partir de una base de licencia abierta, con la licencia de los datos comprobada en su ficha**.

La ficha de cada modelo declara MIT para el modelo, pero eso no dice nada de los datos con los que se entrenó. Las voces no viajan en el repositorio: se descargan al elegirlas.

Cómo elegir voz: `lina voz` lista las que hay y `lina voz NOMBRE` cambia de voz.
Si publicas una versión que incluya alguna voz, mantén estas atribuciones.
