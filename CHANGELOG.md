# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- **Música sin IA**: «pausa», «pon la música en pausa», «para la música», «sigue con la música», «dale al play», «siguiente canción» y «la anterior» controlan lo que ya suena (con `playerctl`, o con el socket del mpv de Lina) (no empiezan nada nuevo: «pon música de Queen» sigue siendo cosa de la IA). Si no hay reproductor, no está `playerctl` o Lina acaba de hacerte una pregunta (donde «la anterior» puede ser tu respuesta), se la dejo a la IA.
- **Piper residente**: la voz se carga una vez en un proceso aparte y las frases salen sin la espera de arrancar Piper cada vez (de uno a dos segundos). Se carga al arrancar Lina, se cierra solo tras 10 minutos sin hablar para soltar la memoria, y si falla de cualquier forma (otra versión de Piper, el proceso muere, tarda demasiado, audio vacío) esa frase sale con el método de siempre; tras dos fallos seguidos se deja por la sesión. Se apaga con `lina config poner voz.residente no`.
- `lina tiempos` cuenta ahora cada llamada a la IA (cuántas, media, mediana, la más lenta y cuántas no llegaron bien y por qué: red, 429, 503…), y la línea del registro las enumera. Solo números.
- **Recetas que se ejecutan solas** (fase 12b): cuando una petición termina bien (la dio por buena el código o el revisor, sin dudas, sin nada pendiente y sin contenido de internet de por medio), Lina apunta **los pasos que de verdad funcionaron** (sin los intentos fallidos ni las exploraciones) y la lectura que lo comprobó. La próxima vez que pidas lo mismo con las mismas palabras («desactiva la cámara»; da igual «oye», «por favor», el orden o «apaga»/«desactiva»), el código repite esos pasos **sin llamar a la IA**, con las mismas herramientas y reglas de seguridad de siempre, vuelve a comprobar el resultado y dice «Hecho.». Si algo no sale como la vez anterior (un paso falla, la comprobación da otra cosa, un comando ya no está permitido), la IA toma el relevo con una nota de lo que pasó, y una receta que falla dos veces seguidas se borra. Un paso crítico sigue pidiendo tu confirmación (la receta pregunta y espera tu «sí»). Una receta que comprobó el código se repite sola desde el primer acierto; una que solo confirmó el revisor, desde el segundo. «Activar» y «desactivar» son recetas distintas, y no se aprende de preguntas, de frases con dos órdenes ni de las que dependen del contexto («ciérralo», «abre el último»), ni nada con contraseñas, borrados, apagados o que alterne (`toggle`). `lina recetas` las lista (con * las que se repiten solas), `lina recetas probar "frase"` dice qué haría sin ejecutar nada y `lina recetas borrar ID` las quita; se apaga con `lina config poner directas.recetas no`.
- **Órdenes directas** (fase 12 del plan de mejoras): «abre Firefox», «sube el volumen», «baja el volumen un 20 %», «pon el volumen al 40», «silencia el sonido» y «quita el silencio» se entienden y se hacen sin llamar a la IA, con las mismas herramientas y reglas de seguridad de siempre. Si la frase no está clara (pregunta, negación, dos cosas encadenadas, un programa que no está instalado, un fallo) se la deja a la IA como antes. `lina directas` lista lo que sabe hacer y `lina directas probar "frase"` dice qué haría sin ejecutarlo; se apaga con `lina config poner directas.activo no`.
- Más órdenes directas, también sin IA: «maximiza esta ventana», «pantalla completa» (y quitarla), «minimiza esta ventana», «muestra el escritorio» (sobre la ventana activa; cerrar no entra: se podría perder trabajo), y «¿qué hora es?» / «¿qué día es hoy?», que dice el propio código con la hora del equipo. Las peticiones educadas que Whisper escribe con «¿…?» («¿puedes abrir Steam?») también valen.
- Las frases cortas de voz («Abierto.», «Volumen al 40 %.») se guardan ya sintetizadas en la caché y la segunda vez suenan al instante, sin arrancar Piper.

### Cambiado
- El revisor «¿se cumplió lo pedido?» ya no se llama cuando el propio código comprobó lo hecho (un programa abierto, un volumen leído después de tocarlo), espera 4 segundos en vez de 8 y prueba un solo modelo; con Google lento, una orden de 3 s dejaba de pasar a 14 s.
- Un fallo de conexión o un timeout deja en pausa a un modelo 30 segundos la primera vez, el doble la segunda y así hasta 3 minutos, y se olvida en cuanto responde bien (los fallos de cuota y de servidor siguen en 3 minutos); un timeout del revisor ya no pausa al modelo que contesta. Con la clave gratuita lenta o saturada, cada petición esperaba 20 s antes de pasar a la de pago.
- Con dos claves (gratuita y de pago), la primera solo espera 8 segundos antes de probar con la otra, en vez de 20 (a fondo y con una sola clave sigue como antes).
- `lina tiempos` separa las órdenes directas de las que pasan por la IA.

### Corregido
- «Para la música» decía «música parada» con la música sonando. Dos causas: `playerctl pause` contesta «hecho» (código 0, sin salida) aunque no haya ningún reproductor que controlar, y el mpv que Lina lanza no habla MPRIS, así que `playerctl` nunca lo veía. Ahora Lina lanza su música con un socket de control (`mpv --input-ipc-server`) y «pausa», «sigue», «siguiente», «anterior» y «para la música» (que ahora para de verdad, no solo pausa) lo usan cuando `playerctl` no ve ningún reproductor; con uno de MPRIS, `playerctl` se usa y se comprueba el estado después (pausado/sonando) en vez de fiarse del «hecho». Sin nada que controlar, el comando devuelve un error claro, no un falso éxito, y las instrucciones de la IA le dicen que nunca diga que ha parado algo que no se comprobó. Nueva orden `lina musica pausar|reanudar|siguiente|anterior|detener`. La música que ya estuviera sonando sin socket (puesta antes de esta versión) no se puede controlar así: ciérrala con `pkill mpv`.
- Una petición que necesita un paso previo largo ya no se olvida: si Lina tenía que instalar algo para abrirlo («abre Stremio») y la instalación pasaba a segundo plano, al terminar solo avisaba de que «ya ha terminado» y no abría nada. Ahora retoma sola la petición original cuando acaba la tarea (hasta 3 vueltas seguidas), le cuenta a la IA qué terminó y qué falta, y las instrucciones de la IA dicen expresamente que su trabajo es cumplir la petición completa, no el primer paso.
- La captura de pantalla se enviaba a la IA en todas las peticiones durante minutos después de pedir algo como «maximiza esta ventana» (incluso para «¿qué hora es?» o una receta), porque cada petición alargaba el plazo de «seguir con la ayuda de pantalla». Ahora seguir una ayuda no la alarga, y el plazo baja de 180 a 90 segundos.

### Añadido
- `lina tiempos [N]`: en qué fase se va el tiempo de tus últimas N peticiones (Whisper, decisiones previas del código, IA, herramientas, síntesis de la voz y reproducción), por separado con y sin herramientas, con media, mediana y la fase más lenta. Es la base para decidir qué acelerar (fase 11 del [plan de mejoras](docs/plan-mejoras.md)).
- Cada petición deja una línea `Tiempos […]` en el registro y una entrada en `~/.local/state/lina/tiempos.jsonl` con **solo números** (nunca lo que dijiste ni lo que contestó Lina); el archivo se recorta solo al llegar a ~200 KB. Se desactiva con `lina config poner privacidad.registrar_tiempos no` y se borra con `lina olvidar tiempos` (también incluido en `lina olvidar todo`).

## [0.1.0-beta] - 2026-10-20

### Corregido
- La prueba del micrófono de `lina bienvenida` detecta cuando el micrófono se satura (llega al máximo: suena alto, distorsionado y con ruido, y Whisper no entiende) y baja solo su ganancia hasta que se oye bien; si no basta, lo deja como estaba y aconseja unos auriculares o un micrófono USB.
- El micrófono sin eco que crea Lina ahora pide expresamente a PipeWire supresión de ruido, filtro de graves y control automático de volumen (se aplica al instalarlo de nuevo o con `lina manos-libres eco`), y `lina uninstall` quita esa configuración de audio, que antes se quedaba.
- En KDE el atajo recién creado no responde hasta cerrar sesión (los atajos van dentro de KWin y no hay forma fiable de recargarlos): ahora el instalador lo dice con un recuadro al final, el resumen lo recuerda y Lina lo avisa con una notificación y, una vez por sesión, por voz, hasta que se cierre sesión.
- `lina uninstall` dejaba tus ajustes, claves y datos sin avisar. Ahora dice que los conserva y, en una terminal, pregunta si quieres borrarlos también; con `--todo` también quita las claves del llavero del sistema.
- En Wayland (KDE, sway…) el instalador pedía los paquetes del sistema sin incluir `gtk-layer-shell`, GTK3 ni PyGObject: el resplandor salía como ventanas con barra de título y `lina doctor` decía «con capa». Ahora se comprueba de verdad, el instalador ofrece instalarlos (con tu contraseña) y Doctor avisa y da la orden si faltan.
- Tras guardar la clave de Gemini (en `lina bienvenida` o con `lina clave`) y al instalar encima de una instalación anterior, Lina se reinicia sola si ya estaba en marcha: leía la clave solo al arrancar y seguía diciendo «no tengo clave» y probando un modelo local que no existe.
- El instalador ya no se limita a avisar de que `~/.local/bin` no está en el PATH: lo añade él al shell del usuario (fish, zsh o bash), lo anota y `lina uninstall` lo quita.
- Al instalar, la configuración guiada pedía la clave sin haber mostrado antes la explicación (el texto quedaba retenido porque el instalador guarda su registro): ahora todo se muestra al momento.
- El asistente de bienvenida decía que la clave de Gemini «empieza por AIza», pero Google ya da claves que empiezan por `AQ.`: ahora no se afirma un prefijo, se quita el aviso falso y esas claves también se tapan en registros e informes.
- Al rechazar Google una clave se muestra su motivo (código y mensaje), y la clave pegada se limpia de comillas y de las marcas del «pegado entre corchetes» de la terminal, que podían invalidarla.
- Resplandor de escucha: dejaba de salir tras suspender el equipo (o apagar la pantalla o cambiar un monitor) hasta reiniciar a Lina. El proceso de dibujo creaba las
  capas una vez al arrancar y las escondía y mostraba después; KDE las cierra al suspender y las viejas no se recuperan («Compositor closed layer surface before sending
  initial .configure»). Ahora se crean al hacer falta, con los monitores de ese momento, y se destruyen al apagarse el resplandor.
- Apagar y reiniciar: la herramienta `energia` solo sabía hacerlo AHORA, y la IA podía decirte «dentro de una hora y media, ¿lo hago?» sobre un `systemctl poweroff`: tu «sí»
  confirmaba la frase y el equipo se apagaba al momento. Ahora `apagar` y `reiniciar` aceptan `valor` (minutos u hora del día) y programan con `shutdown`, hay
  `cancelar_apagado`, y la pregunta de confirmación de las órdenes de energía la escribe el código a partir del comando real («Voy a apagar el equipo dentro de 90 minutos,
  ¿lo hago?»), de modo que no puede contradecir lo que se va a ejecutar. `estado` avisa si hay un apagado programado.

### Cambiado
- Primera configuración (`lina bienvenida`) y `lina clave gemini`: ahora explican qué es la clave de Gemini («una contraseña que deja a Lina usar la IA de Google», gratuita,
  sin tarjeta), dónde y cómo se crea, qué aspecto tiene (empieza por «AIza») y cómo pegarla en la terminal (Ctrl+Mayús+V, sin que se vea nada). La línea que pide la clave
  dice qué se espera, se acusa recibo de lo pegado («Recibida (39 caracteres)») y se avisa si no parece una clave de Gemini.
- Licencia: de MIT a **GNU AGPL-3.0 o posterior** (aún no se había publicado ninguna versión). Cabecera `SPDX-License-Identifier` en todos los archivos, licencia de contribuciones
  en `CONTRIBUTING.md` (`Signed-off-by` y cesión al mantenedor, para poder ofrecer licencias comerciales) y política de la marca «Lina» en `TRADEMARKS.md`.
- Voces: en inglés `ljspeech-high` (de fábrica) y `bryce-medium`, con licencia comprobada; se quitan `lessac` y `amy` (datos de Lessac solo para investigación). En español se
  quita `davefx`; quedan `claude` (de fábrica) y los dos hablantes de `sharvard` (derivada de Lessac, mantenida como excepción de la beta). Si ya tenías instalada una voz
  retirada, sigue funcionando. Ver `docs/creditos.md`.

### Añadido
- Fase 8, inglés completo: la terminal entera (`lina doctor`, `preparar`, `update`, `bienvenida`, `clave`, `privilegios`, `olvidar`, `voz`, `modelos`, `config`, `ia`…)
  sale en inglés con `idioma = "en"`, con sus ayudas y preguntas (vale «yes»; las frases que se teclean para el acceso total y `--todo` también tienen versión inglesa).
  Manual de privacidad y README en inglés, órdenes del manos libres y recordatorios en inglés, y redes de seguridad inglesas (promesas, incapacidad, destrucción total).
  Marcador `N_()` para textos de constantes. El texto que lee la IA sigue en español a propósito; ver `docs/idiomas.md`.
- Fase 9: guía de uso (`docs/uso.md`), README renovado, pasos para publicar una versión (`docs/publicacion.md`) y paquete del AUR (`packaging/aur/`): instala las
  dependencias del sistema y la orden `lina-instalar` (el instalador de siempre). Sin probar con `makepkg`.
- Fase 8, paso 5: primer inglés, experimental (`idioma = "en"`). Traducciones de todas las frases envueltas, instrucciones inglesas para la IA, `comandos.en.txt`,
  reglas y redes de seguridad en inglés, y dos voces de Piper. Lo demás sigue en español; ver
  `docs/idiomas.md`. El manos libres acepta también «hey», «listen», «hi», «hello» y «okay» delante del nombre.
- Fase 8, paso 4: los textos fijos que Lina dice o muestra (frases, notificaciones, mensajes de las órdenes de voz, salida de `lina ia`) pasan por `T()`. Sin
  traducciones el español sale igual. `lina ia usar` ya no pide reiniciar siempre: el cambio se aplica en la siguiente petición. Quedan sin envolver `lina doctor`,
  `ayuda/`, las descripciones de las herramientas y los textos auxiliares para la IA.
- Fase 8, paso 3: las reglas que dependen del idioma pasan a tablas por idioma (instrucciones a la IA, archivo de palabras `comandos.<código>.txt`, frases de «aprende que…»,
  palabras que activan cada grupo de herramientas, fecha para la IA, palabras vacías de las notas). Las cifras solo se leen en palabras en español. Con
  `idioma = "es"` todo es igual que antes; ver `docs/idiomas.md`.
- Fase 8, paso 2: el reconocimiento de voz (Whisper) y las voces de Piper siguen el idioma activo. El catálogo de voces es por idioma, cada idioma tiene su voz de fábrica
  y, si la voz elegida es de otro idioma, se usa la de fábrica de este. Con `idioma = "es"` todo queda igual.
- Fase 8, paso 1: capa de idioma. Ajuste `idioma` (por ahora solo `es`) y `T("texto en español")` para los textos que el usuario lee u oye: el texto en español es la
  clave, las traducciones viven en `datos/idiomas/<código>.toml` y, si falta una, sale el español. Sin cambios visibles todavía.
- Documentos con diseño propio (`disenar_documento`): currículum, factura, cartel, menú, carta con membrete… Lina diseña el documento ella misma (HTML y CSS),
  lo convierte a PDF con el navegador que haya instalado (Chromium, Chrome, Brave, Edge, Vivaldi) o, si no hay, con WeasyPrint (lo instala bajo demanda),
  cuenta las páginas y, si no caben, se corrige una vez. No hay plantillas. El formato es el que pida el usuario: PDF (por defecto) o Word (.docx, pasando el mismo diseño por LibreOffice, que instala bajo demanda y con el que
  también mide las páginas). El HTML queda guardado para retocarlo. Se quitan
  los scripts y los recursos externos del HTML y las fotos locales se incrustan.

### Añadido
- Fase 7, paso 4: ya se puede elegir con qué IA habla Lina. Sección `[ia]` en los ajustes (proveedor, modelos, dirección base), claves `openai` y `anthropic`
  (`lina clave openai`), y `lina ia` para ver el estado, cambiar de proveedor (`lina ia usar anthropic`, `lina ia usar openai --modelo X --url http://localhost:11434/v1`),
  volver a Gemini (`lina ia volver`), listar los modelos del servicio (`lina ia modelos`) y probarlo (`lina ia probar`: dice si responde, si usa herramientas y si ve
  imágenes). Cambiar de proveedor por voz exige el atajo, porque decide a qué empresa se envía lo que dices. `lina doctor` mira el proveedor activo. Con un proveedor
  que no es Gemini Lina cuenta los tokens pero no controla el gasto en euros.
- Fase 7, pasos 2 y 3: proveedores `openai` (OpenAI y todo lo que copia su API: OpenRouter, Groq, Mistral, Ollama, LM Studio, vLLM, servidores de
  empresa, con dirección base propia y clave opcional) y `anthropic`. Probados contra servidores simulados con el formato publicado de cada API,
  todavía no contra los servicios reales, y sin activar: Lina sigue usando Gemini hasta el paso 4.

### Cambiado
- Fase 7, paso 1: la conversación con la IA pasa a una interfaz común (`proveedores.py`) y Gemini es el primer proveedor (`proveedor_gemini.py`).
  El bucle de herramientas, los reintentos, la espera de cuota, la cancelación y las mini-consultas de seguridad se escriben una sola vez y valen para
  cualquier proveedor. Para Gemini el comportamiento no cambia: antes de moverlo se añadieron 28 pruebas contra un servidor simulado que lo fijan.
  Ver [proveedores de IA](docs/proveedores-ia.md).
- Sustituye a `documento_en_columnas` (plantilla fija de currículum en Word, que no servía para otros documentos y no siempre cabía en una página).
- Código más fácil de mantener: `herramientas.py` pasa de 4 300 a unas 2 000 líneas y `asistente.py` de 3 600 a unas 1 800 (la clase `Asistente` reparte parte de sus métodos en cinco módulos `asistente_*.py`), repartidos en módulos con una sola
  responsabilidad (`clasificador`, `papelera`, `documentos`, `resolver`, `ejecucion`, `registro`, `procesos`, `declaraciones`, `ia`, `constantes`, `texto`, `opcionales`).
  El comportamiento no cambia salvo el arreglo de abajo. Ver [arquitectura](docs/arquitectura.md).
- Calidad: ruff comprueba más reglas (`F` completo, trampas de Python como argumentos mutables y variables de bucle capturadas); la CI mide la cobertura con `pytest-cov`
  y pasa mypy como aviso informativo, sin bloquear, mientras se anotan los módulos.
  La CI falla si la cobertura baja del 63 % (hoy es del 67 %).

### Arreglado
- Currículum (documento con columnas): la tabla llenaba el A4 sin margen y, al crecer un poco la cabecera, la hoja se iba a dos páginas; ahora deja casi 1 cm de holgura y la
  cabecera no crece (foto de 4 cm y párrafo vacío mínimo). Y una petición ya no deja tres documentos: si Lina rehace un documento que acaba de crear (porque no cabía), lo
  sustituye en vez de guardar «(2)» y «(3)»; lo que es tuyo nunca se sobrescribe.
- Los documentos con columnas decían «una página A4» aunque sin LibreOffice no se pueda medir si cabe; ahora avisan de que no lo han podido comprobar.
- La prueba del ayudante de root dependía de quién la ejecutara (fallaba fuera de root); ahora fija el usuario.
- La clase «lanzar» de la clasificación de comandos no se alcanzaba nunca: una segunda función con el mismo nombre tapaba a la buena, así que abrir un programa conocido
  con un enlace no se trataba como un lanzamiento. Con pruebas.

### Añadido
- Portabilidad de escritorio: `escritorio/sesion.py` detecta KDE, GNOME, XFCE, Cinnamon, sway, Hyprland y otros (Wayland o X11) y ofrece la ventana activa, la captura de pantalla
  y el portapapeles con el método de cada uno (kdotool/xdotool/swaymsg/hyprctl, spectacle/gnome-screenshot/xfce4-screenshooter/grim/scrot, wl-clipboard/xclip/xsel). Lo que no se
  puede hacer se dice, a ti y a la IA, en vez de fingirlo; en Wayland no se usan herramientas de captura de X11 (darían una imagen negra). `lina escritorio` y `lina doctor` lo
  muestran. Atajo global automático también en Cinnamon y XFCE, y la línea exacta para sway e Hyprland. Gestión de ventanas por voz en X11 (xdotool), y las acciones que solo
  existen en KWin se rechazan con una explicación fuera de KDE. Ver [escritorios](docs/escritorios.md).
- Instalador y primer arranque guiado: `install.sh` en seis pasos con `--simular`, `lina preparar` (comando, modelos, servicio de usuario o arranque de sesión, atajo global en KDE y GNOME),
  `lina bienvenida` (clave de Gemini con validación, prueba de micrófono, nombre, autonomía y privacidad), `lina doctor` (con `--red` e `--informe` anonimizado),
  `lina update` (con `--comprobar` y `--volver`) y `lina uninstall` (solo quita lo anotado en el manifiesto). Si falta la clave de Gemini, Lina avisa con una notificación
  y por voz (como mucho una vez al día) en vez de quedarse muda. Las voces descargadas se verifican (tamaño, formato y huella). Programas opcionales (portapapeles, YouTube)
  se instalan al usarlos, salvo en el perfil prudente. Ver [instalación](docs/instalacion.md).
- Portabilidad entre distribuciones: `plataforma.py` es ahora el único sitio que conoce pacman, apt, dnf y zypper (instalar, quitar, actualizar, buscar, comprobar,
  qué paquete trae un programa), con tablas de paquetes por familia y detección de lo que hay (servicios, audio, snapshots, arranque, GPU, juegos, copias).
  El filtro de comandos entiende los cuatro gestores, la política vigila el kernel y el arranque de cada familia y pide confirmación para PPA, COPR, `.deb`, `.rpm` y similares.
  Timeshift como alternativa a snapper. Las instrucciones para la IA se adaptan a la distribución. Contenedores de Arch, Debian, Fedora y openSUSE en la CI y
  `scripts/probar_en_contenedores.sh`. Ver [portabilidad](docs/portabilidad.md).
- Si Lina necesita ver la pantalla y no hay permiso, lo pide ella (explicando que la captura va a Google) y solo se activa si confirmas con el atajo; con «no» no insiste.
- Sin captura en la petición, Lina sabe que no ve nada y no describe la pantalla (solo conoce el título de la ventana).
- Estructura de proyecto con paquete `lina` (`src/`), comando `lina` y datos del usuario en las carpetas estándar XDG
  (`~/.config/lina`, `~/.local/share/lina`, `~/.local/state/lina`).
- Pruebas automáticas (`tests/`) y comprobación de que no se cuelan secretos ni datos personales.

- Cuatro voces en español (`es_MX-claude-high` por defecto, `es_ES-davefx-medium` y dos hablantes de `es_ES-sharvard-medium`),
  descargadas automáticamente la primera vez. Se elige con `lina voz NOMBRE`; el catálogo está organizado por idioma.

- Ajustes en un único archivo, `~/.config/lina/config.toml`, con validación, valores de fábrica y recarga en caliente; `lina config` para verlos y
  cambiarlos. Migra solo lo que había en `activacion.txt`, `voz.txt`, `presupuesto.txt` y `politica.txt` (ver `docs/configuracion.md`).
- Perfiles de autonomía (`autonomo`, `equilibrado`, `prudente`) e interruptores por categoría. Discos, arranque, cuentas, dinero y gasto se confirman siempre.
- Velocidad de la voz ajustable (`voz.velocidad`).
- Claves en el llavero del sistema (`lina clave gemini|pago|NOMBRE`), con respaldo en un archivo 600; la clave de pago exige un tope mensual; ninguna clave sale en el registro.
- Lina conoce su propia documentación, comandos y ajustes (herramienta `mis_ajustes`): consulta, prueba y cambia voces y cambia ajustes cuando se lo pides, sin frases fijas; lo que da más permisos solo con el atajo; claves y gasto no los toca ella. La voz elegida se oye al instante.
- Privilegios mínimos (`lina privilegios`): ayudante de root `lina-instalar` que solo instala paquetes de los repositorios del sistema, regla de sudoers que solo permite ese ayudante (con vista previa, consentimiento, validación con `visudo` y desinstalación), nivel «total» opcional con aviso y, sin regla, confirmación con el atajo y contraseña pedida por el sistema (polkit). La IA no puede tocar nada de esto.
- Privacidad: `lina privacidad` explica qué se envía a la IA y qué no, y pide permiso antes de enviar capturas de pantalla (no se envía ninguna hasta que se decide; la IA no puede decidirlo). `lina olvidar` borra diario, registro de acciones, recetas y registro del sistema. El registro de acciones rota solo y tapa las claves; `privacidad.registrar_preguntas` permite no dejar lo hablado en el registro.
- Más bloqueos contra contenido hostil: tuberías a un shell o intérprete, descargar y ejecutar en una misma orden, `sh -c "$(curl …)"`, conexiones `/dev/tcp`, código que descarga y ejecuta; piden el atajo el código libre que borra, los contenedores con acceso total, `find -delete/-exec` y `systemctl enable`. Las órdenes de la IA corren sin variables de entorno que parezcan claves. Modelo de amenazas y pruebas de ataque en `docs/seguridad.md` y `tests/test_ataques.py`.

### Eliminado
- `scripts/probar_gemini.py` (diagnóstico antiguo, atado al archivo de clave de antes) y código sin uso.

### Corregido
- Al cambiar de proveedor con Lina en marcha (`lina ia volver`, `lina ia usar …`) se seguía usando la clave del proveedor anterior: ahora la clave cambia con el
  proveedor en la siguiente petición, sin reiniciar, y nunca se envía la clave de uno a otro.
- Si un servidor rechazaba la petición, Lina la repetía sin herramientas y la IA podía decir que había hecho cosas que no había hecho. Ahora, si la causa es que no cabe en
  el contexto del modelo, no se reintenta y el registro dice qué hacer; y cuando sí se quitan las herramientas, se avisa a la IA de que no puede actuar.
- Bloqueo duro: la IA no puede ejecutar `lina config poner|perfil`, `lina clave` ni `lina voz NOMBRE` (cambiar sus propios permisos, gasto o claves es cosa del usuario).
- Pruebas antiguas puestas al día (`t_abrir`, `t_abrir2`).

- El resplandor ya no es una ventana a pantalla completa: son cuatro franjas finas en los bordes de cada monitor (y una sola capa si hay pantallas duplicadas). Si el compositor no deja pasar el ratón, solo se bloquean los bordes y no el escritorio.
- El resplandor de escucha ya no debe bloquear el ratón: la zona de entrada se vacía al crear la ventana, al mostrarla y ya mostrada.
- Al abrir un programa, ya no se avisa de que «ha terminado» cuando el usuario cierra su ventana.
- Las recetas solo se guardan si al final se da por cumplido lo pedido, y describen la petición original (no una queja como «No lo has hecho»).
- Una respuesta que afirma algo habiendo cargado herramientas pero sin hacer ni leer nada del equipo se revisa a fondo.

### Cambiado
- El asistente pasa a llamarse **Lina** (palabra de activación por defecto: «Lina»; el nombre es configurable).
