# Portabilidad entre distribuciones

Lina no depende de una distribución concreta. Todo lo que cambia de una a otra (el gestor de paquetes, los nombres de los paquetes, qué herramienta
hace snapshots, cómo se arranca) vive en **un solo módulo**, `src/lina/nucleo/plataforma.py`; el resto del código pide operaciones («instalar»,
«quitar», «comprobar si está instalado») y no sabe si por debajo hay pacman, apt, dnf o zypper.

## Familias soportadas

| Familia | Distribuciones (por `ID` / `ID_LIKE` de `/etc/os-release`) | Gestor |
|---|---|---|
| `arch` | Arch, CachyOS, EndeavourOS, Manjaro, Garuda, Artix, ArcoLinux | pacman |
| `debian` | Debian, Ubuntu, Linux Mint, Pop!_OS, elementary, Zorin, Kali, KDE neon | apt-get |
| `fedora` | Fedora, RHEL, CentOS, Rocky, AlmaLinux, Nobara | dnf |
| `suse` | openSUSE Tumbleweed y Leap | zypper |

Si tu distribución es una derivada que no se reconoce, fuerza la familia con `LINA_DISTRO=debian` (o `arch`, `fedora`, `suse`) en el entorno del servicio.
Si no encaja en ninguna, Lina sigue funcionando pero no instala nada sola y te da la lista de paquetes que faltan para que los pongas tú.

## Qué hace el gestor de paquetes en cada familia

| Operación | Arch | Debian/Ubuntu | Fedora | openSUSE |
|---|---|---|---|---|
| Instalar | `pacman -S --noconfirm --needed` | `apt-get install -y --no-install-recommends --no-remove` | `dnf install -y` | `zypper --non-interactive install --no-recommends` |
| Quitar | `pacman -Rns --noconfirm` | `apt-get purge -y` | `dnf remove -y` | `zypper --non-interactive remove --clean-deps` |
| Actualizar todo | `pacman -Syu --noconfirm` | `apt-get update` + `apt-get upgrade -y` | `dnf upgrade -y --refresh` | `zypper --non-interactive update` |
| ¿Está instalado? | `pacman -Qq` | `dpkg-query -W` (`ii`) | `rpm -q` | `rpm -q` |
| ¿Qué paquete trae un programa? | `pacman -F` | `apt-file` (si está) | — | — |

Los paquetes de repositorios de terceros (AUR, PPA, COPR, OBS, Snap) y los `.deb`/`.rpm` sueltos **piden siempre confirmación**, igual que antes con el AUR.
El kernel, el gestor de arranque, las bibliotecas base y los controladores de la gráfica están vigilados con los nombres de cada familia (`politica.txt`).

El ayudante de root `lina-instalar` (ver [seguridad](seguridad.md)) ya soportaba las cuatro familias; en Debian y Ubuntu, si la primera instalación falla
(instalación nueva, listas de paquetes sin bajar), ejecuta `apt-get update` y lo repite una sola vez.

## Lo que Lina detecta en vez de suponer

`plataforma.capacidades()` lee del equipo (no lo da por hecho): distribución y familia, gestor, sistema de servicios (systemd, OpenRC, runit…), audio
(PipeWire o PulseAudio), snapshots (snapper o Timeshift), gestor de arranque (GRUB, systemd-boot, Limine, rEFInd), GPU (NVIDIA, AMD, Intel), escritorio y
sesión, y los módulos opcionales: Steam, Heroic, Lutris, MangoHud, GameMode, Flatpak y programas de copias (restic, borg…). Eso es lo que ve la IA como «datos del
sistema», sin «CachyOS» ni escritorio escritos a mano. Lo que no está se omite sin quejarse y, si hace falta, Lina lo dice.

**Snapshots.** Antes de cambiar el sistema Lina hace una snapshot con snapper (Btrfs) o con Timeshift. Si no hay ninguna de las dos, no puede crearla y, como
es la red de seguridad, **lo que cambie el sistema pide confirmación** en vez de hacerse solo (instalar paquetes sigue yendo directo). Instalar `snapper`
o `timeshift` y configurarlo devuelve el comportamiento normal.

## Añadir una distribución o un paquete

- Una distribución nueva de una familia ya conocida: añade su `ID` a `_IDS` en `plataforma.py` y a `_IDS` de `lina-instalar`.
- Un paquete que Lina necesita: añade una línea a `PAQUETES` con su nombre en cada familia (hay una prueba que exige las cuatro).
- Una familia nueva: añade una entrada a `FAMILIAS` (órdenes y textos), a `_ENTRADA_INSTALAR`, `_BANDERAS_INSTALAR` e `interpretar`, y a `lina-instalar`.

## Probarlo

```bash
pytest                                       # todo, con la familia Arch por defecto
LINA_DISTRO=fedora pytest tests/test_paquetes_familias.py   # una familia concreta
scripts/probar_en_contenedores.sh            # las cuatro, en contenedores (docker o podman)
```

La integración continua (`.github/workflows/ci.yml`) pasa las pruebas en contenedores de Arch, Debian, Fedora y openSUSE, y comprueba además que la
distribución detectada es la esperada (`tests/test_plataforma_real.py`).

## Lo que aún es solo de KDE Plasma

La portabilidad de **distribución** está hecha; la de **escritorio** es la Fase 5: hoy las ventanas, los atajos, las capturas (`spectacle`) y algunos
ajustes usan herramientas de KDE (`kdotool`, `qdbus`, `kwriteconfig`), y en GNOME o X11 esas funciones se degradan hasta entonces.
