# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido
- Apagar y reiniciar: la herramienta `energia` solo sabía hacerlo AHORA, y la IA podía decirte «dentro de una hora y media, ¿lo hago?» sobre un `systemctl poweroff`: tu «sí»
  confirmaba la frase y el equipo se apagaba al momento. Ahora `apagar` y `reiniciar` aceptan `valor` (minutos u hora del día) y programan con `shutdown`, hay
  `cancelar_apagado`, y la pregunta de confirmación de las órdenes de energía la escribe el código a partir del comando real («Voy a apagar el equipo dentro de 90 minutos,
  ¿lo hago?»), de modo que no puede contradecir lo que se va a ejecutar. `estado` avisa si hay un apagado programado.

### Cambiado
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
