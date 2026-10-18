# Idiomas

Lina está pensada primero para el español. El ajuste `idioma` de `[asistente]` admite `es` (por defecto) y `en` (inglés, experimental); el español funciona exactamente igual que siempre.

## Qué depende del idioma

| Qué | Dónde | Cómo se elige |
|---|---|---|
| Textos que el usuario ve u oye | `T("texto en español")` en el código; traducciones en `datos/idiomas/<código>.toml` | El texto en español es la clave; sin traducción, sale el español |
| Reconocimiento de voz | Whisper | `language` = idioma activo |
| Voces | `voz/voces.py` (`CATALOGO`, `POR_DEFECTO`) | Catálogo y voz de fábrica por idioma; una voz elegida de otro idioma se sustituye por la de fábrica |
| Instrucciones a la IA | `constantes.INSTRUCCIONES_POR_IDIOMA` | Incluyen el idioma en el que debe contestar |
| Palabras de sí/no, cancelar, modo profundo… | `comandos.<código>.txt` (el español es `comandos.txt`) | Si el idioma no tiene archivo, el español |
| Frases de «aprende que…» y «olvida el alias» | `comandos._ALIAS_POR_IDIOMA` | Tabla por idioma |
| Palabras que activan cada grupo de herramientas | `grupos._PALABRAS` (texto o `{idioma: texto}`) y `_VERBOS_POR_IDIOMA` | Tabla por idioma |
| Fecha y hora que se le da a la IA | `texto._FECHA_POR_IDIOMA` | Función por idioma |
| Cifras en palabras para la voz | `texto.numeros_a_palabras` | Solo en español; los demás idiomas dejan las cifras (la voz las lee sola) |
| Órdenes del manos libres y recordatorios | `manos_libres.entender_orden`, `recordatorios.parse_cuando` | Una función por idioma |
| Palabras vacías al buscar en notas | `notas._PARAR_POR_IDIOMA` | Tabla por idioma |
| Cómo empieza el «motivo» de abrir un programa o cambiar un ajuste | `resolver._LANZAMIENTO_POR_IDIOMA`, `asistente._VERBO_INICIAL_POR_IDIOMA` | Tabla por idioma |

Las tablas se consultan con `idioma.segun(tabla)`: el valor del idioma activo o, si no lo tiene, el del español. Por eso un idioma a medias nunca deja a Lina sin reglas.

## Alcance del inglés (experimental)

`idioma = "en"` lo activa (`lina config poner asistente.idioma en`, o por voz). Está en inglés:

- Todo lo que Lina dice y muestra: frases, notificaciones, mensajes de las órdenes de voz y la salida de la terminal (`lina doctor`, `lina ia`, `lina config`,
  `lina preparar`, `lina update`, `lina bienvenida`, `lina clave`, `lina privilegios`, `lina olvidar`, `lina voz`, `lina modelos`…), con sus ayudas y avisos.
  Los nombres de las órdenes y de los ajustes (`lina config poner asistente.nombre …`) no se traducen.
- `datos/idiomas/en.toml` (todos los textos envueltos en `T()`/`N_()`), el manual `datos/ayuda/privacidad.en.md` y `README.en.md`.
- Instrucciones inglesas para la IA, `comandos.en.txt` (sí/no, cancelar, modo a fondo…), frases de «aprende que…», palabras que activan cada grupo de herramientas,
  fecha para la IA, palabras vacías de las notas, verbos de abrir programas, las órdenes del manos libres (nombre, activar/desactivar, juegos, eco) y los
  recordatorios («in ten minutes», «tomorrow at 9 pm», «every Monday»…).
- Dos voces de Piper.
- Las **redes de seguridad**: las que detectan una respuesta que da algo por hecho (`afirma_hecho`), que reconoce una duda (`admite_duda`) o que pide
  confirmación (`PIDE_CONFIRMACION`), las de promesa e incapacidad (`ia.py`), la de pantalla no visible y los avisos de destruir el sistema. La detección de
  destrucción total y los botones de confirmación de las ventanas miran siempre español e inglés a la vez.
- Las palabras «sí» y «yes» valen en las preguntas de la terminal; la frase que se teclea para el acceso total es `DAR ACCESO TOTAL` o `GRANT FULL ACCESS`, y la
  de `--todo` es `borrar todo` o `delete everything`.

Sigue en español **a propósito**, porque lo lee la IA y no el usuario (las instrucciones le dicen que conteste en el idioma del usuario):

- Las descripciones y los resultados de las herramientas, las reglas de cada grupo, las notas `[SISTEMA: …]`, los textos del clasificador, el revisor y los resúmenes.
- Las pruebas de `lina ia probar` y la nota del escritorio que se le da a la IA.
- Los mensajes del registro (`journalctl`).
- Los archivos de `ayuda/` que usa la IA para conocer los ajustes (`configuracion.md`).

Pendiente o limitado:

- Las cifras solo se leen en palabras en español; en inglés se dejan como cifras y la voz las lee sola.
- Las pistas de pantalla/relleno de `pendiente_dicho` solo conocen palabras españolas e inglesas básicas, y el reconocimiento de nombres de ajustes de KDE es español.
- La documentación de `docs/` está solo en español.
- **Sin probar por mí:** Whisper en inglés, las voces inglesas, la calidad de las traducciones (necesitan una revisión nativa) y la licencia de los datos
  de las voces (ver `docs/creditos.md`). Las pruebas automáticas comprueban que cada regla elige su tabla inglesa y que no falta ninguna traducción, no que Lina «suene» bien.
- El primer argumento de `T()` es solo posicional, así que un hueco puede llamarse `texto`.

## Cómo escribir textos nuevos

- Texto que ve u oye el usuario: `T("texto en español", dato=…)`. Si es una constante de módulo (o una tabla), `N_("texto")` en la constante y `T(CONSTANTE)` donde se muestra.
- Texto para la IA: sin `T()`, en español.
- `raiz.py` y `lina-instalar` (lo que se ejecuta como administrador) no importan nada de Lina: no llevan `T()`.
- Cada texto nuevo necesita su traducción en `en.toml`: `test_el_catalogo_ingles_cubre_todos_los_textos_envueltos` falla si falta alguna (o si sobra).

## Cómo añadir un idioma

1. Añadir su código a `ajustes.IDIOMAS`.
2. Escribir su `datos/idiomas/<código>.toml` y comprobarlo (`idioma.comprobar("<código>")`: los huecos `{…}` tienen que coincidir).
3. Añadir su entrada a cada tabla de arriba y su `comandos.<código>.txt`.
4. Añadir sus voces a `voz/voces.py`: calidad media como mínimo (alta si existe), entrenadas desde cero o desde una base de licencia abierta, y con la licencia de los datos
   comprobada en la ficha (ver la regla y las voces descartadas en `docs/creditos.md`).
5. Probar con voz real: ni el reconocimiento ni las voces se pueden probar sin oírlas.
