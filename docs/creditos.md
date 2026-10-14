# Créditos y licencias de terceros

## Voces

Lina usa el motor de voz [Piper](https://github.com/rhasspy/piper) y las voces del repositorio
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices). Las voces no se distribuyen con este repositorio: Lina descarga
la que se elige a `~/.local/share/lina/voces/` la primera vez que la necesita.

| Voz | Origen |
|---|---|
| `es_MX-claude-high` (por defecto) | [es/es_MX/claude](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX/claude) |
| `es_ES-davefx-medium` | [es/es_ES/davefx](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx) |
| `es_ES-sharvard-medium-1`, `-2` | [es/es_ES/sharvard](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/sharvard) |

- **Sharvard**: entrenada con el corpus Sharvard (Universidad de Edimburgo, [DataShare](https://datashare.ed.ac.uk/handle/10283/574)),
  con licencia [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). Es un modelo de dos hablantes (los dos hablantes de Lina).
- Cada voz tiene su ficha (`MODEL_CARD`) en la carpeta indicada, con su conjunto de datos y licencia.

Cómo elegir voz: `lina voz` lista las que hay y `lina voz NOMBRE` cambia de voz.
Si publicas una versión que incluya alguna voz, mantén estas atribuciones.
