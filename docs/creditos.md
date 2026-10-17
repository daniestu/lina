# Créditos y licencias de terceros

## Voces

Lina usa el motor de voz [Piper](https://github.com/rhasspy/piper) y las voces del repositorio
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices). Las voces no se distribuyen con este repositorio: Lina descarga
la que se elige a `~/.local/share/lina/voces/` la primera vez que la necesita.

| Voz | Datos de entrenamiento | Licencia de los datos |
|---|---|---|
| `es_MX-claude-high` (por defecto) | [HirCoir/Piper-TTS-Spanish](https://huggingface.co/spaces/HirCoir/Piper-TTS-Spanish) | Apache-2.0 |
| `es_ES-davefx-medium` | [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets) | CC0 |
| `es_ES-sharvard-medium-1`, `-2` | Corpus Sharvard, Universidad de Edimburgo ([DataShare](https://datashare.ed.ac.uk/handle/10283/574)) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |

- **Sharvard** exige atribución: *Corpus Sharvard, Universidad de Edimburgo; artículo de referencia:
  [doi:10.3109/14992027.2014.907507](https://www.tandfonline.com/doi/abs/10.3109/14992027.2014.907507)*. Es un modelo de dos hablantes.
- **Claude**: se mantiene el aviso de Apache-2.0 y se reconoce a HirCoir como origen de los datos.
- **Davefx** no exige atribución (CC0); se cita igualmente por cortesía.
- Las voces `davefx` y `sharvard` se entrenaron a partir de la voz inglesa *lessac* (calidad media).
- Cada voz tiene su ficha (`MODEL_CARD`) en su carpeta del repositorio de voces.

### Voces inglesas (experimental)

| Voz | Datos de entrenamiento | Licencia de los datos |
|---|---|---|
| `en_US-lessac-medium` (por defecto en inglés) | Blizzard 2013 Lessac, Universidad de Edimburgo (CSTR) | **Sin comprobar**: la ficha remite a la página de licencia del conjunto de datos |
| `en_US-amy-medium` | [mycroft-ai/mimic3-voices](https://github.com/MycroftAI/mimic3-voices) | **Sin comprobar**: la ficha no la indica |

La ficha de cada modelo declara MIT para el modelo, pero eso no dice nada de los datos con los que se entrenó. **Antes de publicar `v0.1.0-beta` hay que leer
esas licencias y, si no permiten el uso, quitar la voz del catálogo** (`src/lina/voz/voces.py`). Las voces no viajan en el repositorio: se descargan al elegirlas.

Cómo elegir voz: `lina voz` lista las que hay y `lina voz NOMBRE` cambia de voz.
Si publicas una versión que incluya alguna voz, mantén estas atribuciones.
