# Aislar las órdenes de la IA (S9): diseño

*Escrito el 2026-11-15. Es solo diseño: no hay código hasta que el mantenedor lo apruebe. Fila S9 de `docs/plan-mejoras.md`.*

## Para qué

Hoy, lo que la IA puede hacer con `ejecutar_comando` lo frena un **filtro que lee el texto de la orden** (`clasificador.py`, `herramientas.py`, `politica.txt`).
S4, S6 y S5 han cerrado los rodeos medidos, pero una lista sobre el texto de bash nunca estará completa: un script que el filtro no lee, un programa con su
propio lenguaje de órdenes o una forma nueva de escribir lo mismo la rodean. Aislar es la defensa de fondo. La orden se ejecuta **dentro de un espacio donde lo
peligroso no se puede hacer**, aunque el filtro no lo haya visto: escribir en tus claves, leer los datos de Lina, dejar algo que arranque solo o mandar datos
fuera tras leer una web.

El filtro no se quita: sigue decidiendo qué se confirma y qué se bloquea, y sus motivos son los que oye el usuario. El aislamiento es la segunda capa, para lo
que el filtro deja pasar por error.

## Medido en el equipo del mantenedor (CachyOS, KDE Wayland)

- `bwrap` 0.13.1 instalado; los espacios de nombres de usuario sin privilegios están permitidos (`unprivileged_userns_clone = 1`).
- `bwrap --ro-bind / / --bind <carpeta> <carpeta> …` funciona sin privilegios: se escribe en la carpeta de la lista y no en la carpeta personal.
- Coste: unos **1,6 ms más por orden** (0,8 ms `bash -c true` frente a 2,4 ms con `bwrap`, media de 20). No se nota.
- **`--unshare-net` corta las conexiones, pero no la resolución de nombres**: `getent hosts` sigue respondiendo, porque pasa por el socket local de
  systemd-resolved (en `/run`). Una consulta de DNS puede llevar datos dentro del nombre. Al quitar la red también hay que tapar ese socket.
- El socket del bus de sesión (`$XDG_RUNTIME_DIR/bus`) sigue accesible con `--ro-bind / /`, porque un socket no se protege con «solo lectura». Por el bus se
  llega a la cartera de claves (Secret Service), a KWallet, a los portales y a `systemd --user`. Hay que decidir qué se deja pasar (ver abajo).

## Qué se aísla y qué no

| Camino | Hoy | Con S9 |
|---|---|---|
| `Ejecutor.ejecutar` (las órdenes de la IA: `bash -c` desde tu carpeta) | Sin aislar | **Aislado** (lo único que cambia) |
| `Ejecutor.lanzar` (abrir un programa conocido o un enlace, en su propio *scope* de systemd) | Sin aislar | Igual. Solo abre `APPS_PERMITIDAS` con enlaces o archivos tuyos, sin metacaracteres |
| Órdenes inocuas (volumen, `playerctl`, `lina musica`) | Sin aislar | Igual: son una lista cerrada de formas exactas y necesitan PipeWire y el bus |
| El ayudante de root (`raiz.py`), `sudo`/`pkexec`/`run0` | Fuera del servicio | Igual (ver «sudo») |
| El propio código de Lina, el diario, la papelera de Lina, las recetas y la memoria | En el proceso de Lina | Igual: lo escribe Lina, no la orden |

## Carpetas

Base: todo el sistema **de solo lectura** (`--ro-bind / /`), con `/dev` y `/proc` propios, un `/tmp` compartido (los programas lo usan para hablar entre sí,
y las zonas desechables de `politica.txt` incluyen `/tmp`) y `--die-with-parent` para que nada sobreviva a Lina por esta vía.

Escribibles (`--bind`), por lista:

- **Tu carpeta personal**, salvo lo de abajo. La mayoría de las órdenes útiles escriben ahí: documentos, descargas, configuración de programas
  (`kwriteconfig6` en `~/.config`), la papelera (`~/.local/share/Trash`) y las cachés.
- El disco de datos protegido (`RUTA_DATOS`), solo si existe, porque su papelera está allí.

**Tapadas del todo** (`--tmpfs` encima: ni se leen ni se escriben), las mismas que hoy protege `_RUTAS_PROTEGIDAS`: `~/.ssh`, `~/.gnupg`, las carteras de
claves (`~/.local/share/keyrings`, `kwalletd`), las credenciales de la nube y de los gestores de paquetes, los perfiles de los navegadores y **los datos de Lina**
(`~/.config/lina`, `~/.local/share/lina`, `~/.local/state/lina`). Así `grep -r clave ~`, un `python -c` o un script ya no pueden leerlas, se escriba como se
escriba. Es lo que la lista sobre bash (`_lectura_amplia`) no puede garantizar.

**De solo lectura** (`--ro-bind` encima): lo que deja algo arrancando solo, como dice la sección `persistencia` de `politica.txt`: `~/.bashrc`,
`~/.profile`, `~/.zshrc`, `~/.config/fish`, `~/.config/autostart`, `~/.config/systemd/user`, `~/.config/environment.d`, `~/.config/plasma-workspace/env` y
las capas de Vulkan. Cuando el usuario confirma uno de esos cambios con su «sí», la orden confirmada se ejecuta **con esas carpetas escribibles**: el
aislamiento sigue al permiso, no lo sustituye.

**Por decidir:** si `~/.local/bin` va en solo lectura (un programa ahí se ejecuta por nombre más tarde, que es otra forma de persistencia) o se deja escribible
porque `pipx` y `uv tool` instalan ahí. Propuesta: solo lectura, y escribible solo en órdenes confirmadas.

## Red

- **Por defecto, con red.** Muchas órdenes normales la necesitan (`curl -o`, `git clone`, `flatpak`, `dig`, `ping`). Quitarla siempre rompería demasiado.
- **Sin red en una tarea que ha leído contenido de fuera** (`ejecutor.contaminado`), que es justo el caso de S5. Con `--unshare-net` y tapando
  `/run/systemd/resolve` y el bus del sistema, para que tampoco salga nada por DNS. S5 sigue delante y da el motivo; el aislamiento cubre lo que la lista de S5
  no reconoce (`python -c` con `requests.post`, `ssh` con una orden, un programa de subida propio).
- **Excepción en una tarea contaminada:** las órdenes que solo descargan y que el usuario ha confirmado (`ejecutor.permiso`) van con red. Instalar paquetes ya
  va por el ayudante de root, fuera del aislamiento.

## El bus de sesión

Sin bus, fallan órdenes que hoy funcionan: `qdbus`/`gdbus` para KDE, `gsettings set`, `notify-send`, `kioclient` y `busctl --user`. Con el bus entero, la orden
puede pedir claves a la cartera por Secret Service. Propuesta, en dos pasos:

1. **Primera versión:** el bus **tapado en las tareas contaminadas** y abierto en las demás, como hoy. Se documenta como límite.
2. **Después** (pieza aparte): `xdg-dbus-proxy` con una lista de servicios con los que se puede hablar (KDE, `org.freedesktop.Notifications`, gsettings
   vía `ca.desrt.dconf`, MPRIS) y **sin** `org.freedesktop.secrets`, `org.kde.kwalletd*`, `org.freedesktop.systemd1` ni los portales. `xdg-dbus-proxy` es lo
   que usa Flatpak, y suele estar instalado con él.

## Cómo convive con lo que ya hay

- **El diario y deshacer.** `_capturar_previo` guarda la copia **antes** de ejecutar, desde el proceso de Lina (fuera del aislamiento), y deshacer restaura
  desde fuera. No cambia. Si la orden falla porque escribía en una carpeta protegida, `_verificar` ya ve que no cambió nada y el diario lo apunta sin efecto.
  La salida del error («Read-only file system», «Permission denied») le llega a la IA tal cual, y una regla le dice que es el aislamiento, no un fallo del
  programa, y que no lo intente de otra forma.
- **La papelera.** `tratar_borrado` convierte `rm` en `gio trash` o `trash-put`, que escriben en `~/.local/share/Trash` (escribible) y, en el disco de datos,
  en su `.Trash-UID` (escribible si ese disco existe). Falta comprobar que `gio trash` en archivos locales funciona sin `gvfsd` (si no, se le deja su socket). **Prueba obligatoria**, en una carpeta temporal:
  mandar a la papelera, ver la papelera y restaurar.
- **`sudo`, `pkexec` y `run0`.** Dentro de `bwrap` no funcionan (no se puede ganar privilegios: `no_new_privs`). Hoy ya pasan casi siempre por tu atajo:
  `PRIV.adaptar` usa el ayudante de root para instalar, y lo demás con `sudo` es crítico o pide la contraseña. Propuesta: **se quedan fuera del aislamiento**,
  como ahora, con su confirmación y la snapshot de antes. Se documenta como límite. Aislar también lo de root sería otra fase (un `systemd-run` del sistema con
  `ProtectHome=read-only`, desde el ayudante), y no compensa mientras todo eso pida tu «sí».
- **Los programas con ventana.** Abrir un programa va por `lanzar` (fuera, en su *scope*). Si la IA abre uno con `ejecutar_comando` (`motivo` de abrir, o un
  reproductor con `setsid … &`), dentro del aislamiento no tendría su configuración en orden ni el portal de archivos. Propuesta: esas órdenes, que el código
  ya reconoce (`_motivo_es_abrir`, `_es_lanzamiento_persistente`), se **reconducen a `lanzar`** si el programa es de `APPS_PERMITIDAS` o un reproductor de
  `_REPRODUCTORES` sin metacaracteres. Si no, se ejecutan aisladas con el socket de Wayland, X11 y PipeWire, y si no funciona se dice.
- **El perfil y las confirmaciones.** No cambian. El aislamiento no pide nada nuevo al usuario: solo hace que lo que el filtro no vio falle sin daño.

## Cuando no se puede aislar

- Sin `bwrap`, o con los espacios de nombres de usuario cerrados. Ubuntu, desde la 23.10, los limita con AppArmor salvo que el programa tenga su perfil;
  algunas distribuciones endurecidas los apagan.
- **Propuesta:** `ia.aislar = auto` de fábrica. Aísla si se puede; si no, funciona como hoy y `lina doctor` dice por qué y cómo activarlo. Con `si`, sin
  aislamiento no se ejecuta nada de la IA salvo lectura e inocuo. Con `no`, se apaga.
- `systemd-run --user -p ProtectHome=read-only` no sirve de reserva: en un servicio de usuario esa propiedad también necesita espacios de nombres de usuario.

## Piezas, en orden, cada una con su prueba

| Pieza | Qué | Pruebas | Tamaño |
|---|---|---|---|
| S9a | `nucleo/aislamiento.py`: construir la orden de `bwrap` a partir de una descripción (escribibles, tapadas, solo lectura, red sí/no, bus sí/no). Sin usarla aún | Lo que se construye para cada caso; con `bwrap` de verdad, en carpetas temporales: escribir en la lista sí, en una tapada no, leer una tapada no, red cortada sin DNS | M |
| S9b | `ia.aislar` (`auto`, `si`, `no`) y `lina doctor` (si se puede aislar y por qué no) | Con `bwrap` falso o ausente: `auto` ejecuta como hoy y lo dice; `si` no ejecuta | S |
| S9c | Usarlo en `Ejecutor.ejecutar`, con red y bus según la tarea; las órdenes confirmadas con las carpetas de su permiso | Las órdenes reales del registro de acciones del mantenedor (sin texto personal) siguen funcionando: una lista fija de 40–60 en un HOME temporal. Las peligrosas fallan sin daño | M |
| S9d | Reconducir las órdenes de abrir un programa a `lanzar` | Las formas que se reconducen y las que no | S |
| S9e | `xdg-dbus-proxy` con lista de servicios | Hablar con Notifications sí; con `org.freedesktop.secrets` no | M |
| S9f | Uso real: una semana con `ia.aislar = auto` contando las órdenes que fallan por el aislamiento (solo el código de error y el programa, sin texto) | Se decide con datos si `auto` queda de fábrica | S (más una semana de uso) |

**Criterio para darlo por bueno**, antes de S9f: (1) todas las pruebas de hoy en verde; (2) la lista de órdenes reales de S9c funciona igual, con un 0 %
de regresiones; (3) las órdenes peligrosas de la lista de pruebas fallan aisladas aunque el filtro no las vea: escribir en `~/.ssh`, leer
`~/.config/lina`, escribir `~/.bashrc` sin permiso y conectar fuera en una tarea contaminada; (4) la papelera y deshacer funcionan igual.

**Coste:** sin IA ni clave de pago. Unas cinco piezas de código (S9a–S9e, M+S+M+S+M) más una semana de uso para S9f. Se puede parar tras S9c: con eso ya
cubre carpetas y red, que es lo que pide la fila S9.

## Decidido por el mantenedor (2026-11-15)

1. **`~/.local/bin` en solo lectura**, salvo en las órdenes que confirme.
2. **El bus tapado solo en las tareas contaminadas** en la primera versión (S9e, el filtro con `xdg-dbus-proxy`, queda para después). En esas tareas también se
   tapan el bus del sistema y el socket de systemd-resolved. Fuera de ellas, el bus y `$XDG_RUNTIME_DIR` se quedan como hoy: el registro de acciones del
   mantenedor muestra órdenes autónomas que los necesitan (`warp-cli`, `kdotool`, `playerctl`, `kscreen-doctor`, `systemctl --user`, `bluetoothctl`, `mpv`).
3. **`ia.aislar` apagado de fábrica** (`no`). El mantenedor lo activa en su equipo una semana para medirlo (S9f) y pasa a `auto` antes del servicio de pago.
4. **`sudo`, `pkexec` y `run0`, fuera del aislamiento**, documentado como límite.

**Hecho el 2026-11-15: S9a, S9b y S9c** (`nucleo/aislamiento.py`, `ia.aislar` con su línea en `lina doctor`, `Ejecutor.ejecutar`; la IA no puede cambiar `ia.aislar`). Cuando una orden aislada falla por algo que el aislamiento impide, la IA recibe una nota para no intentarlo de otra forma, y en el registro de acciones queda `[aislamiento] PROGRAMA rc=N`, sin más texto: es lo que se cuenta en la semana de S9f. S9d (reconducir a `lanzar`), S9e y S9f, después.

**Para la semana de medida (S9f):** `lina config poner ia.aislar auto`, y al cabo de la semana `grep -c '\[aislamiento\]' ~/.local/state/lina/acciones.log` y `grep '\[aislamiento\]' ~/.local/state/lina/acciones.log | sort | uniq -c` para ver qué programas fallan. Lo esperable que falle hasta S9d: abrir el navegador con `ejecutar_comando` cuando no estaba abierto (su perfil está tapado).

**Límites de la primera versión** (además del de `sudo`): una ruta protegida que **no existe** no se puede tapar sin crearla en tu carpeta, así que no se
tapa (la sigue vigilando el filtro de texto: `politica.txt` y `_lectura_amplia`); los sockets abstractos del bus, si tu sistema los usa, siguen al alcance
mientras haya red, porque van con el espacio de red y no con las carpetas.
## Preguntas que se le hicieron

1. ¿`~/.local/bin` en solo lectura, salvo en órdenes confirmadas?
2. ¿Bus tapado solo en tareas contaminadas (primera versión), o esperar a `xdg-dbus-proxy` (S9e) para activarlo?
3. ¿`ia.aislar = auto` de fábrica desde el principio, o `no` hasta S9f?
4. ¿`sudo` fuera del aislamiento, como se propone, documentado como límite?
