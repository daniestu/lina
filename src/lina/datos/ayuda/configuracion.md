# Configuración

Todos los ajustes de Lina están en un único archivo, `~/.config/lina/config.toml`. Se puede editar a mano o con `lina config`. Se relee solo al guardar,
así que casi todo se aplica sin reiniciar (el nombre y la voz piden `systemctl --user restart lina`). Si un valor está mal escrito, Lina usa el de fábrica y lo
dice en el registro (`journalctl --user -u lina`); `lina config comprobar` te lo cuenta también.

```
lina config                              # ver todo
lina config ver voz.velocidad            # un ajuste, con su explicación
lina config poner voz.velocidad 1.2      # cambiarlo
lina config perfil prudente              # cambiar el perfil de autonomía
lina config comprobar                    # revisar el archivo
```

Las listas que se editan a mano siguen aparte: `politica.txt` (reglas de lo crítico), `comandos.txt`, `vocabulario.txt`, `paquetes_confiables.txt` y los precios en `presupuesto.txt`.

## Pedirle a Lina que se configure

Lina conoce su propia documentación, sus comandos y todos sus ajustes con su valor actual (la herramienta `mis_ajustes`), así que no hace falta saber el comando:
se lo pides con tus palabras y ella consulta y lo hace («¿qué voces tienes?», «ponme un ejemplo de cada una», «quédate con la segunda», «habla más rápido»,
«quita el resplandor», «pasa al perfil prudente»). Puede consultar todo, probar voces, elegir voz y cambiar casi cualquier ajuste; se nota al momento.

Las protecciones están en el código, no en lo que ella entienda:

- Lo que da **más permisos** (un perfil más permisivo, categorías en «libre») solo lo cambia si pulsas el atajo y lo pides tú; con «Oye Lina» se niega, por si lo dijera otra voz.
  Tampoco lo hace si en esa petición ha leído algo de internet o de un archivo.
- **Claves y gasto** (el tope, los avisos, el cambio de moneda) no los toca ella: el tope lo subes tú por voz con el atajo («sube el tope de gasto a 20 euros») o en la terminal.
- Lo que aprieta (perfil más prudente) se lo puedes pedir de cualquier forma.

## Perfiles de autonomía

| Perfil | Qué hace |
|---|---|
| `autonomo` (por defecto) | Actúa solo salvo lo crítico, que se confirma con el atajo. |
| `equilibrado` | Igual, pero tras leer contenido de internet frena los cambios libres hasta que confirmes. |
| `prudente` | Pide confirmación para casi todo lo que cambie algo. |

Los interruptores por categoría (`borrado`, `software_de_fuera`, `red_expuesta`, `sesion`, `persistencia`, `archivos_de_paquetes`) valen `perfil` (lo que diga el perfil),
`confirmar` o `libre`. **Tocar discos, el arranque, las cuentas, el dinero y el gasto de Lina se confirma siempre, en todos los perfiles**, y hay bloqueos duros en el código
que no se pueden desactivar. Los perfiles se aplican encima de `politica.txt`: pueden apretar el modo o aflojar categorías, no vaciar lo crítico.

## Todos los ajustes

### [asistente] Identidad

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `nombre` | `"Lina"` | Cómo se llama el asistente. Es también la palabra de activación («Oye Lina»). |
| `idioma` | `"es"` | Idioma de Lina: en el que te habla y te entiende (es = español, en = inglés, experimental). |

### [voz] Voz

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `voz` | `"es_MX-claude-high"` | Voz de Piper. Mira las que hay con:  lina voz |
| `velocidad` | `1.0` | Velocidad al hablar: 1 normal, 1.2 más rápida, 0.8 más lenta. |

### [activacion] Manos libres

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `activo` | `true` | false: apaga el manos libres (el atajo sigue funcionando siempre). |
| `alias` | `""` | Otros nombres que también valen, separados por comas. |
| `prefijos` | `"oye, escucha, hey, ey, eh, hola, oiga, atiende, despierta, ok, vale, oie"` | Palabras que van delante del nombre. |
| `sin_prefijo` | `true` | true: basta con «Lina, …» al principio de la frase. |
| `seguimiento` | `8` | Segundos tras contestarte en los que puedes seguir hablando sin repetir el nombre (0 = nunca). |
| `espera_orden` | `6` | Segundos que espera tu orden si solo dices «Oye Lina» y callas. |
| `en_juegos` | `false` | true: escucha también con un juego en primer plano. |
| `sensibilidad` | `0.012` | Volumen mínimo para considerar que hablas. Mídelo con:  lina manos-libres nivel |
| `eco` | `"auto"` | auto: cancela el eco si está instalado. no: apagado. |
| `parecido` | `0.78` | Lo parecido que tiene que sonar el nombre (0-1). Más bajo = acepta más variantes (y más falsos avisos). |

### [autonomia] Autonomía: qué hace solo y qué te pregunta

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `perfil` | `"autonomo"` | autonomo: actúa solo salvo lo crítico · equilibrado: además frena los cambios tras leer contenido de internet · prudente: pide confirmación para casi todo lo que cambie algo. |
| `borrado` | `"perfil"` | Borrar de verdad o muchos archivos de golpe. |
| `software_de_fuera` | `"perfil"` | Instalar o ejecutar software de fuera de las fuentes de confianza (AUR, pip, npm…). |
| `red_expuesta` | `"perfil"` | Cortafuegos, SSH y todo lo que expone tu PC a la red. |
| `sesion` | `"perfil"` | Apagar, reiniciar o cerrar sesión. |
| `persistencia` | `"perfil"` | Crear servicios o tareas automáticas. |
| `archivos_de_paquetes` | `"perfil"` | Modificar archivos de programas instalados (/usr…). |

### [directas] Órdenes directas (sin IA)

Las órdenes claras y de riesgo bajo («abre Firefox», «sube el volumen», «silencia el sonido») se hacen sin llamar a la IA: mucho más rápido y sin gasto. Usan las mismas herramientas y
reglas de seguridad de siempre. Si la frase no está clara (una pregunta, una negación, dos cosas encadenadas) o algo falla, se la dejo a la IA. Mira cuáles hay y pruébalas con `lina directas`.

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `activo` | `true` | true: las órdenes claras y de riesgo bajo («abre Firefox», «sube el volumen») se hacen sin llamar a la IA, mucho más rápido. Mira cuáles y pruébalas con:  lina directas |
| `recetas` | `true` | true: lo que ya me has pedido una vez y salió bien (p. ej. «desactiva la cámara») lo aprendo y, si lo repites con las mismas palabras, lo hago sin llamar a la IA. Mira lo aprendido con:  lina recetas |

### [ia] Inteligencia artificial

Con qué IA habla Lina. Por defecto es Gemini con tu clave gratuita y no hace falta tocar nada. Mira y cambia con `lina ia`. Cambiar de proveedor decide a qué empresa se envía lo que
dices, así que por voz exige el atajo (o se hace en la terminal).

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `proveedor` | `"gemini"` | `gemini`, `anthropic` u `openai` (OpenAI y todo lo compatible: OpenRouter, Groq, Mistral, Ollama, LM Studio, un servidor de tu empresa…). |
| `modelo_rapido` | `""` | Modelo para el día a día. Vacío: el recomendado (con `openai` hay que indicarlo; los ves con `lina ia modelos`). |
| `modelo_profundo` | `""` | Modelo para el modo «a fondo». Vacío: el recomendado, o el rápido si no hay recomendado. |
| `url_base` | `""` | Solo con `openai`: dirección del servicio si no es OpenAI, p. ej. `http://localhost:11434/v1` (Ollama). En local no hace falta clave. |
| `razonamiento` | `false` | Solo con `openai`: `true` si el modelo es de razonamiento y admite indicar cuánto pensar. |

### [gasto] Gasto con la clave de pago

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `tope_mensual_eur` | `10.0` | Lo máximo que gastas al mes con la clave de pago, en euros. |
| `eur_por_usd` | `0.92` | Cuántos euros vale un dólar (los precios de Google están en dólares). |
| `avisos_porcentaje` | `[50, 80, 100]` | Te aviso al llegar a estos porcentajes del tope. Al 100 % la clave de pago deja de usarse. |

### [privacidad] Privacidad

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `almacen_claves` | `"auto"` | auto: las claves van al llavero del sistema si lo hay (y si no, a un archivo solo tuyo). archivo: siempre archivo. |
| `capturas` | `"preguntar"` | Enviar capturas de tu pantalla a la IA. `preguntar`: aún no has decidido, no se envía ninguna (decídelo con `lina privacidad`) · `si`: cuando hacen falta, nunca en modo privado ni con ventanas sensibles · `no`: nunca. La IA no puede cambiarlo. |
| `registrar_preguntas` | `true` | true: lo que dices y lo que contesto queda en el registro del sistema (journalctl), útil para depurar. false: se omite. |
| `registro_ruido` | `false` | true: se apunta en el registro lo que oye y descarta (solo para depurar). |
| `registrar_tiempos` | `true` | true: se apuntan cuántos segundos tarda cada fase de una petición (solo números, nunca lo que dices). Se ven con:  lina tiempos |

### [interfaz] Interfaz

| Ajuste | De fábrica | Qué hace |
|---|---|---|
| `indicador` | `true` | Resplandor en los bordes: te escucha (azul), piensa (ámbar), habla (verde). |
| `indicador_color` | `"azul"` | Color al escucharte: azul, rojo, verde, morado, naranja, amarillo, rosa, cian, blanco o #rrggbb. |
| `indicador_grosor` | `40` | Píxeles que entra el resplandor desde el borde. |
| `indicador_intensidad` | `1.0` | Lo fuerte que brilla: 0.1 casi invisible … 1 normal … 2 muy fuerte. |
| `indicador_juegos` | `false` | true: también se dibuja con un juego en primer plano. |
| `indicador_instalar` | `true` | true: si faltan paquetes para dibujarlo, los instala solo (repositorios oficiales). |

## Claves

Las claves (Gemini gratuita, Gemini de pago, Tavily, las de servidores MCP) **no van en `config.toml`**. Se guardan en el llavero del sistema (GNOME Keyring, KWallet…
a través de `secret-tool`, del paquete `libsecret`) y, si no hay llavero, en un archivo con permisos 600 dentro de `~/.config/lina`. Nunca se escriben en pantalla,
no se dictan por voz y Lina las tapa en todo lo que imprime (el registro de `journalctl` no las contiene).

```
lina clave                 # qué claves hay y dónde (sin enseñarlas)
lina clave gemini          # la gratuita
lina clave pago            # la de pago: antes te pide un tope mensual, que es obligatorio
lina clave NOMBRE          # otra, por ejemplo GITHUB_TOKEN para un servidor MCP
lina clave borrar NOMBRE
lina clave migrar          # pasa al llavero las que estén en archivos
```

Para forzar siempre archivo: `lina config poner privacidad.almacen_claves archivo`.

## Venías de una versión anterior

La primera vez que arranca, Lina crea `config.toml` con lo que tenías en `activacion.txt`, `voz.txt`, `presupuesto.txt` (tope, cambio y avisos) y `politica.txt` (perfil).
Los dos primeros se renombran a `.antiguo` para que quede claro qué manda ahora; `presupuesto.txt` y `politica.txt` se quedan donde estaban (precios y reglas).
