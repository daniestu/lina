"""Instalación de Lina en el equipo del usuario: lo que hace `lina preparar` (lo llama install.sh) y lo que deshace `lina uninstall`.

`install.sh` solo prepara el terreno (paquetes del sistema, entorno de Python); todo lo demás está aquí, en Python, para poder probarlo:
enlace del comando, modelos, servicio de usuario, atajo global y permisos de entrada. Cada cosa que se crea se anota en un manifiesto
(`~/.local/state/lina/instalacion.json`) y la desinstalación lo lee: quita exactamente lo que se puso, y nada más.

Nada con permisos de administrador se hace sin enseñarlo y que el usuario lo acepte.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lina import __version__
from lina.escritorio import atajo as ATAJO
from lina.nucleo import modelos as MOD
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

VERSION_MANIFIESTO = 1
UNIDAD = "lina.service"
REGLAS_ENTRADA = ["/etc/udev/rules.d/80-asistente-uinput.rules", "/etc/modules-load.d/asistente-uinput.conf"]   # las crea `lina interfaz preparar`
AYUDA = N_("""lina preparar [--simular] [--si] [--sin-modelos] [--sin-servicio] [--sin-atajo] [--atajo TECLA] [--entrada]
    Deja Lina lista para usarse: enlace del comando, modelos (Whisper y voz), servicio de usuario y atajo global.
    --simular      dice lo que haría, sin tocar nada
    --si           responde «sí» a las preguntas (menos a las de permisos de administrador, que siempre se hacen a mano)
    --entrada      además prepara el control de programas con la pantalla (permisos de /dev/uinput; pide administrador)
lina uninstall [--simular] [--si] [--todo]
    Quita lo que instaló Lina (servicio, atajo, comando, permisos). --todo borra también tus ajustes, claves y datos.""")


class Manifiesto:
    """Lista de lo que se ha creado, en un archivo JSON."""

    def __init__(self, ruta=None):
        self.ruta = Path(ruta or (RUT.ESTADO / "instalacion.json"))
        self.acciones = []
        try:
            d = json.loads(self.ruta.read_text(encoding="utf-8"))
            self.acciones = [a for a in d.get("acciones", []) if isinstance(a, dict) and isinstance(a.get("tipo"), str)]
        except (OSError, ValueError, AttributeError):
            pass

    def anotar(self, tipo, **datos):
        self.acciones = [a for a in self.acciones if a["tipo"] != tipo] + [{"tipo": tipo, **datos}]

    def quitar(self, tipo):
        self.acciones = [a for a in self.acciones if a["tipo"] != tipo]

    def de(self, tipo):
        return next((a for a in self.acciones if a["tipo"] == tipo), None)

    def guardar(self):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporal = self.ruta.with_name(self.ruta.name + ".nuevo")
            temporal.write_text(json.dumps({"version": VERSION_MANIFIESTO, "acciones": self.acciones}, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(temporal, self.ruta)
        except OSError:
            pass


class Contexto:
    """Todo lo que cambia entre producción y pruebas: rutas, cómo se pregunta, cómo se ejecuta."""

    def __init__(self, simular=False, si=False, home=None, entrada=input, salida=print, ejecutar=subprocess.run, manifiesto=None,
                 which=shutil.which, ejecutable=None, terminal=None):
        self.simular, self.si = simular, si
        self.home = Path(home or Path.home())
        self.entrada, self.salida, self.ejecutar, self.which = entrada, salida, ejecutar, which
        self.manifiesto = manifiesto or Manifiesto()
        self.ejecutable = Path(ejecutable) if ejecutable else _ejecutable_lina()
        self.terminal = sys.stdin.isatty() if terminal is None else terminal
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        self.config = Path(xdg_config) if xdg_config and os.path.isabs(xdg_config) else self.home / ".config"
        self.bin = self.home / ".local" / "bin"

    def preguntar(self, texto, por_defecto=True):
        """Sí/no. Con --si responde que sí; sin terminal, responde el valor por defecto."""
        if self.si:
            return True
        if not self.terminal:
            return por_defecto
        try:
            r = self.entrada(f"{texto} [{T('S/n') if por_defecto else T('s/N')}] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return por_defecto if not r else r in ("s", "si", "sí", "y", "yes")

    def aviso(self, simbolo, texto):
        self.salida(f"  {simbolo} {texto}")


def _ejecutable_lina():
    """El `lina` de este entorno de Python (el del venv), o el que haya en el PATH."""
    candidato = Path(sys.executable).with_name("lina")
    return candidato if candidato.exists() else Path(shutil.which("lina") or candidato)


# ---------------------------------------------------------------- pasos de la instalación
def paso_enlace(ctx):
    """~/.local/bin/lina → el lina del entorno de Python (para poder escribir «lina pulsar» en cualquier sitio)."""
    destino = ctx.bin / "lina"
    if ctx.simular:
        ctx.aviso("·", f"[simulación] enlazaría {destino} → {ctx.ejecutable}")
        return True
    if not ctx.ejecutable.exists():
        ctx.aviso("!", T("No encuentro el programa lina de este entorno ({v1}); no creo el enlace.", v1=ctx.ejecutable))
        return False
    if destino.exists() and not destino.is_symlink():
        ctx.aviso("!", T("{destino} ya existe y no es un enlace: no lo toco.", destino=destino))
        return False
    ctx.bin.mkdir(parents=True, exist_ok=True)
    if destino.is_symlink():
        destino.unlink()
    destino.symlink_to(ctx.ejecutable)
    ctx.manifiesto.anotar("enlace", ruta=str(destino))
    ctx.aviso("✔", T("Comando «lina» en {destino}", destino=destino))
    if str(ctx.bin) not in os.environ.get("PATH", "").split(":"):
        ctx.aviso("!", T("{v1} no está en tu PATH: añádelo para escribir «lina» en la terminal.", v1=ctx.bin))
    return True


def paso_modelos(ctx):
    todo, problemas = MOD.asegurar_todo(log=lambda m: ctx.aviso("·", m), simular=ctx.simular)
    if not todo:
        ctx.aviso("!", T("Faltan ") + ", ".join(problemas) + T(": sin ellos Lina no puede oír o hablar. Repite luego con:  lina modelos"))
    elif not ctx.simular:
        ctx.aviso("✔", T("Modelos de voz listos"))
    return todo


def texto_unidad(ejecutable):
    return ("[Unit]\nDescription=Lina, asistente de voz\nAfter=graphical-session.target pipewire.service\nPartOf=graphical-session.target\n\n"
            f"[Service]\nExecStart={ejecutable}\nRestart=on-failure\nRestartSec=3\nEnvironment=PYTHONUNBUFFERED=1\n\n[Install]\nWantedBy=graphical-session.target\n")


def paso_servicio(ctx, arrancar=True):
    """Servicio de usuario de systemd; sin systemd, el arranque automático de la sesión (XDG autostart), que sirve en cualquier escritorio."""
    if PL.detectar_init() == "systemd" and ctx.which("systemctl"):
        carpeta = ctx.config / "systemd" / "user"
        unidad = carpeta / UNIDAD
        if ctx.simular:
            ctx.aviso("·", f"[simulación] escribiría {unidad} y la activaría")
            return True
        carpeta.mkdir(parents=True, exist_ok=True)
        unidad.write_text(texto_unidad(ctx.ejecutable), encoding="utf-8")
        ctx.ejecutar(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
        r = ctx.ejecutar(["systemctl", "--user", "enable"] + (["--now"] if arrancar else []) + [UNIDAD], capture_output=True, text=True)
        ctx.manifiesto.anotar("servicio", ruta=str(unidad))
        if r.returncode != 0:
            ctx.aviso("!", T("No he podido activar el servicio: ") + (r.stderr or r.stdout or "sin detalle").strip()[:150])
            return False
        ctx.aviso("✔", T("Servicio de usuario lina.service ") + (T("activado y arrancado") if arrancar else T("activado")))
        escr = ATAJO.escritorio()
        if escr in ("sway", "hyprland", "otro"):
            ctx.aviso("!", T("Tu sesión puede no activar graphical-session.target, y entonces el servicio no arranca al iniciar sesión. Si pasa, añade a la configuración de tu escritorio:  exec {v1}   (comprueba con  lina doctor  tras reiniciar sesión)", v1=ctx.bin / 'lina'))
        return True
    arranque = ctx.config / "autostart" / "lina.desktop"
    if ctx.simular:
        ctx.aviso("·", f"[simulación] sin systemd: crearía {arranque} (arranque con la sesión)")
        return True
    arranque.parent.mkdir(parents=True, exist_ok=True)
    arranque.write_text(f"[Desktop Entry]\nType=Application\nName=Lina\nExec={ctx.ejecutable}\nIcon=audio-input-microphone\nTerminal=false\n", encoding="utf-8")
    ctx.manifiesto.anotar("autostart", ruta=str(arranque))
    ctx.aviso("✔", T("Sin systemd: Lina arrancará con tu sesión ({arranque}). Para arrancarla ya:  lina", arranque=arranque))
    return True


def paso_atajo(ctx, tecla=None):
    escr = ATAJO.escritorio()
    if ATAJO.ya_hay_atajo(escr, ctx.home, ctx.ejecutar, ctx.which):
        ctx.aviso("✔", T("Ya tienes un atajo para Lina: lo dejo como está."))
        return True
    tecla = tecla or ATAJO.TECLA_POR_DEFECTO.get(escr)
    if not tecla:
        ctx.aviso("!", ATAJO.a_mano(escr, ctx.bin / "lina"))
        return False
    if not ctx.simular and not ctx.preguntar(T("¿Creo el atajo global {tecla} para hablar con Lina?", tecla=tecla)):
        ctx.aviso("·", T("Vale. Cuando quieras, crea uno que ejecute:  {v1} pulsar", v1=ctx.bin / 'lina'))
        return False
    hecho, mensaje, nota = ATAJO.registrar(escr, tecla, str(ctx.bin / "lina"), ctx.home, ctx.simular, ctx.ejecutar, ctx.which)
    ctx.aviso("✔" if hecho else "!", mensaje)
    if hecho and nota:
        ctx.manifiesto.anotar("atajo", **nota)
    return hecho


def paso_entrada(ctx):
    """Control de programas con la pantalla (ydotool): necesita permisos sobre /dev/uinput. Lo hace `lina interfaz preparar`, que pide la contraseña."""
    ctx.salida(T("  Esto da a tu usuario permiso para crear teclado y ratón virtuales (/dev/uinput) y activa la accesibilidad; pide tu contraseña de administrador."))
    if not ctx.simular and not ctx.preguntar(T("¿Preparo el control de programas con la pantalla ahora?"), por_defecto=False):
        ctx.aviso("·", T("Lo dejo. Cuando quieras:  lina interfaz preparar"))
        return False
    if ctx.simular:
        ctx.aviso("·", "[simulación] ejecutaría:  lina interfaz preparar")
        return True
    guion = RUT.PAQUETE / "escritorio" / "interfaz.sh"
    r = ctx.ejecutar(["bash", str(guion), "preparar"])
    if r.returncode == 0:
        ctx.manifiesto.anotar("entrada", reglas=REGLAS_ENTRADA, servicio=str(ctx.config / "systemd" / "user" / "ydotoold.service"))
    return r.returncode == 0


def preparar(argv, ctx=None):
    """lina preparar: ver AYUDA."""
    if "-h" in argv or "--help" in argv or "ayuda" in argv:
        print(T(AYUDA))
        return 0
    tecla = None
    if "--atajo" in argv:
        i = argv.index("--atajo")
        tecla = argv[i + 1] if i + 1 < len(argv) else None
    ctx = ctx or Contexto(simular="--simular" in argv or "--dry-run" in argv, si="--si" in argv or "-y" in argv)
    ctx.salida(T("Preparando Lina") + (T(" (simulación: no se toca nada)") if ctx.simular else ""))
    fallos = []
    if not paso_enlace(ctx):
        fallos.append("comando")
    if "--sin-modelos" not in argv and not paso_modelos(ctx):
        fallos.append("modelos")
    if "--sin-servicio" not in argv and not paso_servicio(ctx, arrancar="--sin-arrancar" not in argv):
        fallos.append("servicio")
    if "--sin-atajo" not in argv and not paso_atajo(ctx, tecla):
        fallos.append("atajo")
    if "--entrada" in argv and not paso_entrada(ctx):
        fallos.append("entrada")
    if not ctx.simular:
        raiz = RUT.PAQUETE.parent.parent
        ctx.manifiesto.anotar("instalado", version=__version__, venv=sys.prefix, fuente=str(raiz) if (raiz / "pyproject.toml").exists() else "",
                              clonado=os.environ.get("LINA_CLONADO") == "1")
        ctx.manifiesto.guardar()
    ctx.salida("\n" + (T("Todo listo.") if not fallos else T("Hecho, salvo: ") + ", ".join(fallos) + T(". Mira arriba qué falta y cómo se arregla.")))
    return 0 if not fallos else 1


# ---------------------------------------------------------------- desinstalación
def plan_de_desinstalacion(ctx, todo=False):
    """[(descripción, función)] de lo que se quitaría, según el manifiesto."""
    m = ctx.manifiesto
    pasos = []
    if m.de("servicio"):
        ruta = Path(m.de("servicio")["ruta"])
        pasos.append((T("servicio de usuario ({ruta})", ruta=ruta), lambda ruta=ruta: _quitar_servicio(ctx, ruta)))
    if m.de("autostart"):
        ruta = Path(m.de("autostart")["ruta"])
        pasos.append((T("arranque automático ({ruta})", ruta=ruta), lambda ruta=ruta: _borrar(ruta)))
    if m.de("atajo"):
        nota = m.de("atajo")
        pasos.append((T("atajo global {v1}", v1=nota.get('tecla', '')), lambda nota=nota: ATAJO.quitar(nota, ctx.home, ctx.simular, ctx.ejecutar, ctx.which)))
    if m.de("enlace"):
        ruta = Path(m.de("enlace")["ruta"])
        pasos.append((T("comando {ruta}", ruta=ruta), lambda ruta=ruta: _borrar(ruta, solo_enlace=True)))
    if m.de("entrada"):
        e = m.de("entrada")
        pasos.append((T("permisos de /dev/uinput y servicio ydotoold (pide administrador)"), lambda e=e: _quitar_entrada(ctx, e)))
    if todo:
        pasos.append((T("TUS AJUSTES Y CLAVES ({v1}) y los llaveros de Lina", v1=RUT.CONFIG), lambda: _borrar_arbol(RUT.CONFIG, ctx)))
        pasos.append((T("TUS DATOS: recetas, diario, voces, modelos ({v1}, {v2}, {v3})", v1=RUT.DATOS, v2=RUT.ESTADO, v3=RUT.CACHE),
                      lambda: [_borrar_arbol(p, ctx) for p in (RUT.DATOS, RUT.ESTADO, RUT.CACHE)][-1]))
    v = m.de("instalado") or {}
    if v.get("clonado") and v.get("fuente") and Path(v["fuente"]).parent == RUT.DATOS:          # solo el código que bajó el instalador, nunca un clon tuyo
        pasos.append((T("código descargado por el instalador ({v1})", v1=v['fuente']), lambda v=v: _borrar_arbol(Path(v["fuente"]), ctx)))
    if v.get("venv") and Path(v["venv"]).parent == RUT.DATOS and Path(v["venv"]).name == "venv":
        pasos.append((T("entorno de Python ({v1})", v1=v['venv']), lambda v=v: _borrar_arbol(Path(v["venv"]), ctx)))
    return pasos


def _borrar(ruta, solo_enlace=False):
    ruta = Path(ruta)
    if solo_enlace and not ruta.is_symlink():
        return T("{ruta} no es un enlace: no lo toco", ruta=ruta)
    try:
        ruta.unlink(missing_ok=True)
    except OSError as e:
        return T("no he podido quitar {ruta} ({e})", ruta=ruta, e=e)
    return T("quitado {ruta}", ruta=ruta)


def _borrar_arbol(ruta, ctx):
    ruta = Path(ruta)
    if ctx.simular:
        return f"[simulación] borraría {ruta}"
    if ruta.is_dir() and ruta.resolve() != Path("/") and ruta != ctx.home:
        shutil.rmtree(ruta, ignore_errors=True)
    return T("borrado {ruta}", ruta=ruta)


def _quitar_servicio(ctx, ruta):
    if ctx.simular:
        return f"[simulación] desactivaría y quitaría {ruta}"
    ctx.ejecutar(["systemctl", "--user", "disable", "--now", UNIDAD], capture_output=True, text=True)
    out = _borrar(ruta)
    ctx.ejecutar(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
    return out


def _quitar_entrada(ctx, nota):
    if ctx.simular:
        return "[simulación] quitaría las reglas de /dev/uinput y el servicio ydotoold"
    servicio = Path(nota.get("servicio", ""))
    if servicio.name == "ydotoold.service":
        ctx.ejecutar(["systemctl", "--user", "disable", "--now", servicio.name], capture_output=True, text=True)
        servicio.unlink(missing_ok=True)
    reglas = [r for r in nota.get("reglas", []) if r in REGLAS_ENTRADA]
    r = ctx.ejecutar(["sudo", "rm", "-f", *reglas])
    return T("permisos de /dev/uinput quitados") if r.returncode == 0 else T("no he podido quitar los permisos de /dev/uinput (necesita administrador); quítalos tú: sudo rm ") + " ".join(reglas)


def desinstalar(argv, ctx=None):
    if "-h" in argv or "--help" in argv:
        print(T(AYUDA))
        return 0
    todo = "--todo" in argv
    ctx = ctx or Contexto(simular="--simular" in argv or "--dry-run" in argv, si="--si" in argv or "-y" in argv)
    pasos = plan_de_desinstalacion(ctx, todo)
    if not pasos:
        ctx.salida(T("No encuentro nada que quitar en el manifiesto de instalación (¿se instaló con install.sh?)."))
    else:
        ctx.salida(T("Voy a quitar:"))
        for d, _ in pasos:
            ctx.salida(f"  · {d}")
    if todo and not ctx.simular:
        ctx.salida(T("\n--todo borra también TUS AJUSTES, CLAVES y DATOS, y no se puede deshacer."))
        try:
            if not ctx.terminal or ctx.entrada(T("Para continuar escribe exactamente «borrar todo»: ")).strip().lower() not in ("borrar todo", T("borrar todo")):
                ctx.salida(T("No se ha quitado nada."))
                return 1
        except (EOFError, KeyboardInterrupt):
            return 1
    elif pasos and not ctx.simular and not ctx.preguntar(T("¿Sigo?")):
        ctx.salida(T("No se ha quitado nada."))
        return 1
    for d, f in pasos:
        try:
            ctx.salida(f"  ✔ {f()}")
        except Exception as e:                      # una pieza que falla no impide quitar las demás
            ctx.salida(f"  ! {d}: {e}")
    if not ctx.simular:
        ctx.manifiesto.acciones = [a for a in ctx.manifiesto.acciones if a["tipo"] == "instalado"] if not todo else []
        if not todo:
            ctx.manifiesto.guardar()
        ctx.salida(T("\nSi diste a Lina permisos de administrador (sudoers), quítalos con:  lina privilegios quitar"))
        v = ctx.manifiesto.de("instalado")
        if v and Path(v.get("venv", "")).parent != RUT.DATOS:
            ctx.salida(T("El entorno de Python ({v1}) no lo creó el instalador: bórralo tú si ya no lo quieres.", v1=v.get('venv')))
    return 0


def atajo_cli(argv, ctx=None):
    """lina atajo [TECLA]: crea (o deja como está) el atajo global."""
    ctx = ctx or Contexto(si="--si" in argv)
    teclas = [a for a in argv if not a.startswith("-")]
    ok = paso_atajo(ctx, teclas[0] if teclas else None)
    ctx.manifiesto.guardar()
    return 0 if ok else 1


def principal(argv):
    return preparar(argv)
