# Instalación

## Con el instalador

```sh
git clone https://github.com/daniestu/lina.git
cd lina
./install.sh
```

También se puede ejecutar sin clonar a mano (`install.sh` baja el código él solo): `curl -fsSL <url-de-install.sh> | bash`. Lee el script antes de ejecutarlo;
con `--simular` dice todo lo que haría sin tocar nada.

`install.sh` hace seis cosas, y antes de cada cambio importante enseña qué va a hacer:

1. **Comprueba el sistema**: Python 3.11 o más reciente y qué distribución, gestor de paquetes y escritorio tienes.
2. **Consigue el código**: usa la carpeta desde la que lo ejecutas o clona el repositorio en `~/.local/share/lina/fuente`.
3. **Paquetes del sistema** (Python con venv y pip, un compilador, git, PortAudio, libnotify): enseña la orden exacta
   y la ejecuta con `sudo` solo si lo aceptas. Si no, la deja escrita para que la ejecutes tú.
4. **Entorno de Python** en `~/.local/share/lina/venv` e instalación de Lina.
5. **`lina preparar`**: el comando `lina` en `~/.local/bin`, los modelos (Whisper para oírte y la voz de Lina, unos 500 MB la primera vez),
   el servicio de usuario `lina.service` (o, sin systemd, el arranque automático de la sesión) y el atajo global (`Meta+Espacio` en KDE,
   `Ctrl+Alt+Espacio` en GNOME; con `--atajo TECLA` eliges otro).
6. **`lina bienvenida`**: te guía por la clave de Gemini (gratuita), el micrófono, el nombre, la libertad de Lina y la privacidad.

Opciones: `--simular`, `-y` (responde sí a todo menos a lo que da permisos de administrador), `--sin-sistema`, `--sin-bienvenida`, `--entrada`
(prepara el control de programas con la pantalla), `--atajo TECLA`, `--quitar`.

Todo lo que se crea queda apuntado en `~/.local/state/lina/instalacion.json`. El registro de la instalación está en `~/.local/state/lina/instalacion.log`.

## Después

| Comando | Para qué |
|---|---|
| `lina bienvenida` | repetir la configuración guiada |
| `lina doctor` | comprobar que todo está en su sitio y cómo arreglar lo que falle (`--red` prueba también la conexión y la clave; `--informe` lo da sin datos personales para pegar en una incidencia) |
| `lina update` | actualizar (te enseña qué trae y pregunta; `--comprobar` solo mira; `--volver` deshace la última actualización) |
| `lina atajo [TECLA]` | crear el atajo global si no lo hay |
| `lina modelos` | descargar o comprobar los modelos de voz |
| `lina uninstall` | quitar lo que puso el instalador; `--todo` además borra tus ajustes, claves y datos (te hace escribir «borrar todo») |

`lina update` solo actualiza una copia sin cambios tuyos (`git pull --ff-only`): si has modificado algo no lo pisa. Reinstala las dependencias de Python
únicamente si cambiaron y reinicia el servicio.

## Si algo falla

Ejecuta `lina doctor`: cada problema sale con la orden que lo arregla. Si no basta, `lina doctor --informe` genera un texto sin tu carpeta personal,
usuario, nombre del equipo, correos, direcciones IP ni claves, apto para abrir una incidencia.

## Qué no se ha podido comprobar todavía

El registro del atajo en KDE y GNOME y el servicio de systemd están cubiertos por pruebas con órdenes simuladas, no en un escritorio real de cada tipo;
en KDE puede hacer falta cerrar y abrir sesión para que el atajo responda. Las voces se verifican con una huella guardada al descargarlas (detecta
archivos que cambian o se corrompen después), pero el catálogo aún no incluye las sumas oficiales de cada modelo.
