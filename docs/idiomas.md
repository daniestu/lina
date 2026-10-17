# Idiomas

Lina está en español. La fase 8 prepara el terreno para otros idiomas; el inglés será el primero y llegará después de la beta. Hoy solo se puede elegir `es`
(ajuste `idioma` en `[asistente]`), y el español funciona exactamente igual que antes.

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
| Palabras vacías al buscar en notas | `notas._PARAR_POR_IDIOMA` | Tabla por idioma |
| Cómo empieza el «motivo» de abrir un programa o cambiar un ajuste | `resolver._LANZAMIENTO_POR_IDIOMA`, `asistente._VERBO_INICIAL_POR_IDIOMA` | Tabla por idioma |

Las tablas se consultan con `idioma.segun(tabla)`: el valor del idioma activo o, si no lo tiene, el del español. Por eso un idioma a medias nunca deja a Lina sin reglas.

## Lo que todavía no está por idioma

- Los textos que Lina devuelve a la IA como resultado de una herramienta y las descripciones de las herramientas siguen en español. Una IA multilingüe los entiende y
  contesta en el idioma de las instrucciones; con modelos pequeños puede no ser así (no comprobado).
- Las consultas auxiliares a la IA (revisor, confirmaciones, resúmenes) siguen con instrucciones en español.
- Los mensajes del registro (`journalctl`) siguen en español.
- `T()` ya envuelve los textos fijos que Lina dice o muestra: sus frases, las notificaciones, los mensajes de las órdenes de voz y la salida de `lina ia`.
  Todavía **no** están envueltos: `lina doctor`, los archivos de `ayuda/`, el README, las descripciones y resultados de las herramientas, los textos
  auxiliares que se envían a la IA y los registros (logs). En español todo sale igual que antes.
- El primer argumento de `T()` es solo posicional, así que un hueco puede llamarse `texto`.

## Cómo añadir un idioma

1. Añadir su código a `ajustes.IDIOMAS`.
2. Escribir su `datos/idiomas/<código>.toml` y comprobarlo (`idioma.comprobar("<código>")`: los huecos `{…}` tienen que coincidir).
3. Añadir su entrada a cada tabla de arriba y su `comandos.<código>.txt`.
4. Añadir sus voces a `voz/voces.py` con la licencia de cada una comprobada.
5. Probar con voz real: ni el reconocimiento ni las voces se pueden probar sin oírlas.
