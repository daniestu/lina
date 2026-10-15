# Seguridad y confirmaciones

Principios:

1. **Autonomía por defecto, con frenos.** Lina actúa sola salvo en las categorías críticas de `politica.txt`
   (discos, arranque, cuentas y credenciales, red expuesta, borrado definitivo, software de fuera, dinero, sesión, persistencia,
   archivos de paquetes).
2. **Las acciones críticas solo se confirman con el atajo de teclado**, nunca por voz en manos libres: una frase mal oída o un vídeo
   de fondo no pueden autorizar nada.
3. **Bloqueos duros en el código** que ninguna política ni confirmación desbloquea (formatear discos, leer claves, descargar y ejecutar
   scripts de internet…).
4. **Lo que lee de fuera es información, no órdenes** (webs, documentos, resultados de herramientas).
5. **Todo cambio queda en un diario** y se puede deshacer; los borrados normales van a la papelera.
6. **Sin telemetría.** Las capturas de pantalla solo se envían a la IA para responder, y existe un modo privado que las desactiva.
7. **Las claves** viven en `~/.config/lina/` con permisos 600 y la IA no puede leerlas ni editarlas.

## Privilegios (permisos de administrador)

Lina nunca ve ni guarda tu contraseña de administrador. Hay tres niveles; el actual se ve con `lina privilegios`.

| Nivel | Qué pasa |
|---|---|
| **ninguno** (por defecto) | Lo que necesite permisos de administrador queda pendiente de tu atajo, y la contraseña la pide el propio sistema (polkit/`pkexec`). |
| **instalar** | `lina privilegios instalar`: una regla de sudoers permite **un solo programa**, `lina-instalar`, que solo instala paquetes de los repositorios de tu sistema. |
| **total** | `lina privilegios total`: sudo sin contraseña para todo. Opcional, con aviso, y hay que teclear una frase. Lo crítico se sigue confirmando con el atajo. |

Para activarlo o quitarlo (`instalar`, `total`, `quitar`):

1. Lo haces tú en una terminal; la IA no puede (está bloqueado en el código) y sin terminal no hay consentimiento.
2. Antes de nada se **enseña todo lo que se va a escribir** (el ayudante con su huella, la regla de sudoers exacta, la política de polkit).
3. Lo que se ejecuta como administrador es el texto de `src/lina/nucleo/raiz.py` (corto, solo biblioteca estándar), enviado con `sudo`/`pkexec` con los datos por la entrada
   estándar: es lo mismo que se mostró, no un archivo que otro proceso pudiera cambiar mientras escribes la contraseña.
4. Las reglas de sudoers se validan con `visudo` antes de activarse, y las carpetas del camino deben ser solo de root.
5. Se quita todo con `lina privilegios quitar`.

El ayudante `lina-instalar` (`src/lina/datos/privilegios/lina-instalar`, un archivo que se lee entero en un minuto):

- decide el gestor (pacman, apt, dnf, zypper) leyendo `/etc/os-release`, nunca por argumentos;
- acepta solo nombres sencillos (`[A-Za-z0-9._+-]`, sin opciones, rutas, URLs, comodines, versiones, `paquete-` de apt ni `@grupo` de dnf) y nunca instala desde un archivo o dirección;
- no toca el software que concede privilegios (sudo, doas, polkit, pam, shadow);
- usa un entorno limpio, sin entrada y con límite de tiempo, y apunta cada uso en el registro del sistema (`journalctl -t lina-instalar`).

Aun con el ayudante, instalar un paquete de una categoría crítica de `politica.txt` (servidores SSH, cortafuegos…) sigue pidiendo tu atajo. Las pruebas de ataque
(`tests/test_ayudante.py`, `tests/test_raiz.py`, `tests/test_privilegios.py`) corren en cada cambio.
