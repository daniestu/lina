# Seguridad y confirmaciones

Principios:

1. **Autonomía por defecto, con frenos.** Lina actúa sola salvo en las categorías críticas de `politica.txt`
   (discos, arranque, cuentas y credenciales, red expuesta, borrado definitivo, software de fuera, dinero, sesión, persistencia,
   archivos de paquetes).
2. **Las acciones críticas solo se confirman con el atajo de teclado**, nunca por voz en manos libres: una frase mal oída o un vídeo
   de fondo no pueden autorizar nada.
3. **Bloqueos duros en el código** que ninguna política ni confirmación desbloquea (formatear discos, leer claves, descargar y ejecutar
   scripts de internet…).
   Las claves y credenciales que se bloquean siempre, para leer o para escribir: SSH, GnuPG, AWS, `.netrc`, los perfiles de Firefox, el llavero
   (también `~/.local/share/keyrings`), la GitHub CLI (`hosts.yml`, `gh auth token`), Docker y Podman, Kubernetes (`~/.kube/config`,
   `kubectl config view --raw`), git (`.git-credentials`, `git credential`), las cookies, los datos de autocompletar y la clave de los navegadores
   Chromium (Chrome, Chromium, Brave, Vivaldi, Edge, Opera, también en Flatpak), rclone, npm, PyPI, Cargo, Terraform, gcloud, Azure, hub y `pass`.
   Si de verdad lo necesitas, lo haces tú en tu terminal. **Con tu confirmación** (con el atajo) se pueden leer los historiales de la terminal
   (bash, zsh, fish, python, psql, mysql, sqlite, node), que suelen guardar contraseñas escritas a mano, y el historial de navegación de los
   Chromium: lo que se lea se envía a la IA.
   Además, lo que devuelve **cualquier herramienta** (comandos, documentos, ajustes de KDE, lo que se lee de una ventana, la web, los servidores MCP, y
   lo que se ejecuta al confirmar) se le da a la IA **sin claves**: se tapan las que tienen forma de clave (Google, OpenAI/Anthropic,
   GitHub, Slack, Tavily, `Bearer …`) y el valor de las variables de entorno en mayúsculas cuyo nombre lleva TOKEN, SECRET, KEY, PASS, AUTH o
   CREDENTIAL (lo que sacan `env`, `printenv`, `export -p` o `declare -x`). Va por trozos del nombre a propósito, así que también tapa variables
   inofensivas como `KEYMAP` o `GIT_AUTHOR_NAME`; si la IA necesita una de esas, díselo tú. En los archivos de configuración (los cambios de KDE que
   ve la IA), el valor de una clave con nombre de contraseña o token (`Password`, `AuthToken`, `ApiKey`…) también sale tapado.
4. **Lo que lee de fuera es información, no órdenes** (webs, documentos, resultados de herramientas).
5. **Todo cambio queda en un diario** y se puede deshacer; los borrados normales van a la papelera.
6. **Sin telemetría.** Las capturas de pantalla solo se envían a la IA para responder, y existe un modo privado que las desactiva. La IA puede
   activarlo, pero **quitarlo solo lo hace el código**, ante una frase exacta tuya («quita el modo privado», sección `[modo_privado_quitar]` de
   `comandos.txt`) y solo con el atajo: ni una web con instrucciones escondidas ni una voz de fondo pueden volver a abrir la pantalla.
   Lo mismo con los **alias de voz** («cuando oigas cait quiero decir Kate»), que cambian cómo se entienden tus órdenes desde ese momento: la IA solo
   puede listarlos; apuntarlos lo hace el código ante tu frase y solo con el atajo, y olvidarlos también por «Oye Lina». Además, un alias no puede
   convertir un verbo de orden en otro («conecta = desconecta»): el código lo rechaza.
   Y con la **memoria de preferencias**: «recuerda que…» solo se apunta con el atajo; «olvida lo de…» y «¿qué recuerdas de mí?» valen también por «Oye Lina».
7. **Las claves** viven en el llavero del sistema (o en un archivo con permisos 600) y la IA no puede leerlas ni editarlas; ninguna sale en el registro.
8. **Privilegios mínimos**: ver «Privilegios» más abajo. Lina nunca ve tu contraseña de administrador.

## Privilegios (permisos de administrador)

Lina nunca ve ni guarda tu contraseña de administrador. Hay tres niveles; el actual se ve con `lina privilegios`.

| Nivel | Qué pasa |
|---|---|
| **ninguno** (por defecto) | Lo que necesite permisos de administrador queda pendiente de tu atajo, y la contraseña la pide el propio sistema (polkit/`pkexec`). |
| **instalar** | `lina privilegios instalar`: una regla de sudoers permite **un solo programa**, `lina-instalar`, que solo instala paquetes de los repositorios de tu sistema. |
| **total** | `lina privilegios total`: sudo sin contraseña para todo. Opcional, con aviso, y hay que teclear una frase. Lo crítico se sigue confirmando con el atajo. |

Para activarlo o quitarlo (`instalar`, `total`, `quitar`):

1. Lo decides tú: en una terminal, o confirmando con el atajo cuando Lina lo pide porque lo necesita para lo que le has pedido. La IA no puede
   concederlo sola (está bloqueado en el código); la confirmación con el atajo no se acepta por manos libres ni si en la tarea se ha leído contenido de fuera,
   y con «no» Lina no vuelve a preguntar.
2. Antes de nada se **enseña todo lo que se va a escribir** (el ayudante con su huella, la regla de sudoers exacta, la política de polkit).
3. Lo que se ejecuta como administrador es el texto de `src/lina/nucleo/raiz.py` (corto, solo biblioteca estándar), enviado con `sudo`/`pkexec` con los datos por la entrada
   estándar: es lo mismo que se mostró, no un archivo que otro proceso pudiera cambiar mientras escribes la contraseña.
4. Las reglas de sudoers se validan con `visudo` antes de activarse, y las carpetas del camino deben ser solo de root.
5. Se quita todo con `lina privilegios quitar`.

El ayudante `lina-instalar` (`src/lina/datos/privilegios/lina-instalar`, un archivo que se lee entero en un minuto):

- decide el gestor (pacman, apt, dnf, zypper) leyendo `/etc/os-release`, nunca por argumentos (en Debian/Ubuntu, si falla la primera vez, refresca las listas con `apt-get update` y repite una vez);
- acepta solo nombres sencillos (`[A-Za-z0-9._+-]`, sin opciones, rutas, URLs, comodines, versiones, `paquete-` de apt ni `@grupo` de dnf) y nunca instala desde un archivo o dirección;
- no toca el software que concede privilegios (sudo, doas, polkit, pam, shadow);
- usa un entorno limpio, sin entrada y con límite de tiempo, y apunta cada uso en el registro del sistema (`journalctl -t lina-instalar`).

Aun con el ayudante, instalar un paquete de una categoría crítica de `politica.txt` (servidores SSH, cortafuegos…) sigue pidiendo tu atajo. Las pruebas de ataque
(`tests/test_ayudante.py`, `tests/test_raiz.py`, `tests/test_privilegios.py`) corren en cada cambio.

## Modelo de amenazas

Lina es un programa que **hace cosas en tu ordenador a partir de texto que le da una IA**. La IA puede equivocarse o ser engañada, y Lina escucha un micrófono abierto.
Esto es lo que se considera, qué lo frena y qué queda sin cubrir.

| Amenaza | Cómo llegaría | Qué lo frena | Lo que queda |
|---|---|---|---|
| **Contenido hostil** | Una web, un documento, un resultado de herramienta o el título de una ventana con «instrucciones» para la IA | Lo leído de fuera se trata como dato, no como orden; tras leerlo, los cambios libres se frenan hasta que confirmes (perfiles *equilibrado* y *prudente*); los bloqueos de abajo valen igual | Con el perfil *autónomo*, una IA engañada puede hacer lo que no esté bloqueado ni sea crítico. Usa *equilibrado* si lees mucho de internet |
| **Voces ajenas** | Un vídeo, otra persona o el eco del altavoz dicen «Oye Lina…» | Por el manos libres nunca se confirma una acción crítica ni se suben permisos o gasto: solo con el atajo | Una voz cercana puede pedir cosas no críticas. Puedes apagar el manos libres (`activacion.activo`) |
| **Errores de la IA** | Interpreta mal («borra eso»), se inventa un comando | Lo crítico pide el atajo; los borrados van a la papelera; todo cambio queda en un diario y se puede deshacer; snapshots antes de tocar el sistema | Un error en algo no crítico es posible; el diario permite deshacerlo |
| **Comandos peligrosos** | `rm -rf ~`, `mkfs`, `dd` a un disco, bombas de procesos | Bloqueo duro en el código (no desbloqueable ni confirmando) | El filtro lee el texto de la orden; no es un aislamiento (ver abajo) |
| **Descargar y ejecutar** | `curl … \| sh`, `sh -c "$(curl …)"`, `curl -o x && ./x`, `… \| base64 -d \| sh`, `python -c` que descarga y ejecuta, `bash -i >& /dev/tcp/…` | Bloqueo duro (también cualquier tubería a un shell o intérprete) | Una descarga en una orden y su ejecución en otra, sin relación visible |
| **Fuga de secretos** | Leer `~/.ssh`, `~/.aws`, cookies, llaves de Lina, `/proc/*/environ`; `printenv` | Bloqueo duro de esas rutas y del llavero; las órdenes de la IA corren **sin** variables de entorno que parezcan claves; las claves se tapan en toda salida y registro | Un secreto guardado en un archivo con otro nombre que no esté en la lista |
| **Fuga de datos a la IA** | Capturas con contraseñas o datos bancarios; texto sensible en la conversación | Capturas solo con tu permiso (`lina privacidad`), nunca en modo privado ni con ventanas sensibles; manual de lo que se envía en `lina privacidad` | Lo que dices o ves en una ventana no marcada como sensible, si permites capturas |
| **Escalada de privilegios** | Convertir a Lina en administrador | Ver «Privilegios»: un solo ayudante validado, regla de sudoers verificada, sin contraseñas en Lina; la IA no puede tocar la regla ni el ayudante | En el nivel *total* cualquier cosa que corra como tú puede ser administrador |
| **Cambiar sus propios límites** | La IA edita `politica.txt`, `config.toml`, su código o su servicio | Todo eso está protegido en el código; los ajustes sensibles (perfil, gasto, claves, privacidad) solo los cambia el usuario | — |

### Lo que Lina **no** es

No es un entorno aislado: las órdenes se ejecutan con tu usuario y el filtro razona sobre el texto de cada orden (con las inevitables formas de esquivarlo que tiene cualquier
filtro de texto). Su defensa es en capas: bloqueos duros, confirmación con el atajo, diario con deshacer, y que tú decidas el perfil. Si necesitas aislamiento real
(información muy sensible, equipos compartidos), ejecútala en una cuenta de usuario aparte, usa el perfil *prudente* y no actives el nivel *total*.

### Pruebas

`tests/test_ataques.py` lleva un surtido de ataques (más de cien órdenes) que no pueden ir sin freno, y una lista de órdenes normales que **no** deben frenarse
(un filtro que molesta se acaba desactivando). `tests/test_ayudante.py`, `tests/test_raiz.py` y `tests/test_privilegios.py` atacan el ayudante de root y su instalador.
Todo corre en cada cambio en la integración continua. Si encuentras una forma de esquivar un filtro, repórtala (ver `SECURITY.md`).
