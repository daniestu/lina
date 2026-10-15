"""`lina update`: actualiza Lina sin romper nada y permite volver atrás.

Si Lina se instaló desde un clon de git (lo normal con install.sh), actualiza con `git pull --ff-only`: nunca pisa cambios tuyos (si hay,
no toca nada), guarda la versión anterior para `lina update --volver` y reinstala dependencias solo si cambiaron. Si se instaló con pip,
usa pip. Después reinicia el servicio si estaba activo. Antes de cambiar nada enseña qué cambia y pregunta.
"""
import json
import subprocess
import sys
from pathlib import Path

from lina.nucleo import instalador as INST
from lina.nucleo import rutas as RUT

ARCHIVO = "actualizacion.json"
PAQUETE_PIP = "lina-asistente"
AYUDA = """lina update [--comprobar] [--si] [--volver]
    Actualiza Lina. Antes de cambiar nada te enseña qué trae y pregunta.
    --comprobar   solo dice si hay novedades, sin cambiar nada
    --si          no pregunta
    --volver      vuelve a la versión anterior a la última actualización"""


class Git:
    def __init__(self, carpeta, ejecutar=subprocess.run):
        self.carpeta, self.ejecutar = str(carpeta), ejecutar

    def __call__(self, *args, tiempo=120):
        try:
            r = self.ejecutar(["git", "-C", self.carpeta, *args], capture_output=True, text=True, timeout=tiempo)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)
        return r.returncode, (r.stdout or "").strip() if r.returncode == 0 else ((r.stderr or r.stdout or "").strip())


def _leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(ruta, datos):
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos), encoding="utf-8")
    except OSError:
        pass


def _fuente(ctx):
    v = ctx.manifiesto.de("instalado") or {}
    f = Path(v.get("fuente") or "")
    return f if v.get("fuente") and (f / ".git").exists() else None


def _reinstalar(ctx, fuente):
    ctx.salida("  · Actualizo las dependencias de Python…")
    r = ctx.ejecutar([sys.executable, "-m", "pip", "install", "-q", "-e", str(fuente)], capture_output=True, text=True)
    if r.returncode != 0:
        ctx.salida("  ✘ pip ha fallado: " + (r.stderr or r.stdout or "sin detalle").strip()[-200:])
        return False
    return True


def _reiniciar(ctx):
    if not ctx.which("systemctl"):
        return
    activo = ctx.ejecutar(["systemctl", "--user", "is-active", "lina.service"], capture_output=True, text=True)
    if (activo.stdout or "").strip() == "active":
        ctx.ejecutar(["systemctl", "--user", "restart", "lina.service"], capture_output=True, text=True)
        ctx.salida("  ✔ Servicio reiniciado con la versión nueva.")
    else:
        ctx.salida("  · Si Lina está en marcha, reiníciala para usar la versión nueva.")


def _git_actualizar(ctx, fuente, comprobar, volver, estado, git=None):
    git = git or Git(fuente, ctx.ejecutar)
    c, sucio = git("status", "--porcelain")
    if c != 0:
        ctx.salida(f"  ✘ No puedo leer el repositorio de {fuente}: {sucio[:150]}")
        return 1
    if sucio and not comprobar:
        ctx.salida(f"  ✘ Hay cambios tuyos sin guardar en {fuente}; no toco nada. Guárdalos (git stash) y repite.")
        return 1
    c, actual = git("rev-parse", "HEAD")
    if volver:
        previo = _leer(estado).get("anterior")
        if not previo:
            ctx.salida("  No tengo guardada ninguna versión anterior a la que volver.")
            return 1
        ctx.salida(f"  Volveré a la versión {previo[:8]} (ahora: {actual[:8]}).")
        if not ctx.preguntar("¿Vuelvo?"):
            return 1
        cambios = git("diff", "--name-only", actual, previo)[1]
        c, e = git("reset", "--hard", previo)
        if c != 0:
            ctx.salida(f"  ✘ {e[:150]}")
            return 1
        ok = _reinstalar(ctx, fuente) if "pyproject.toml" in cambios.split() else True
        _guardar(estado, {"anterior": actual})              # y se puede volver a «adelante» con otra vuelta
        _reiniciar(ctx)
        ctx.salida("  ✔ Vuelto a la versión anterior." if ok else "  ! Vuelto, pero fallaron las dependencias: repite  pip install -e " + str(fuente))
        return 0 if ok else 1
    c, e = git("fetch", "--quiet")
    if c != 0:
        ctx.salida(f"  ✘ No he podido consultar si hay novedades (¿sin conexión?): {e[:150]}")
        return 1
    c, nuevas = git("log", "--oneline", "--no-decorate", "HEAD..@{u}")
    if c != 0:
        ctx.salida("  ! Tu copia no sigue ninguna rama remota; no sé de dónde actualizar.")
        return 1
    if not nuevas:
        ctx.salida("  ✔ Ya tienes la última versión.")
        return 0
    lineas = nuevas.splitlines()
    ctx.salida(f"  Hay {len(lineas)} cambio(s) nuevo(s):")
    for l in lineas[:15]:
        ctx.salida(f"    · {l[:100]}")
    if len(lineas) > 15:
        ctx.salida(f"    … y {len(lineas) - 15} más")
    if comprobar:
        ctx.salida("  Para actualizar:  lina update")
        return 0
    if not ctx.preguntar("¿Actualizo?"):
        ctx.salida("  Vale, lo dejo.")
        return 1
    cambios = git("diff", "--name-only", "HEAD", "@{u}")[1]
    c, e = git("pull", "--ff-only", "--quiet")
    if c != 0:
        ctx.salida(f"  ✘ No se ha podido actualizar sin pisar nada ({e[:150]}). Tu copia sigue como estaba.")
        return 1
    _guardar(estado, {"anterior": actual})
    ok = _reinstalar(ctx, fuente) if "pyproject.toml" in cambios.split() else True
    _reiniciar(ctx)
    ctx.salida("  ✔ Actualizada. Si algo va mal:  lina update --volver" if ok else "  ! Actualizada, pero fallaron las dependencias. Repite:  pip install -e " + str(fuente) + "   (o  lina update --volver)")
    return 0 if ok else 1


def _pip_actualizar(ctx, comprobar):
    if comprobar:
        r = ctx.ejecutar([sys.executable, "-m", "pip", "install", "--dry-run", "--upgrade", PAQUETE_PIP], capture_output=True, text=True)
        hay = r.returncode == 0 and "Would install" in (r.stdout or "")
        ctx.salida("  Hay una versión nueva en PyPI. Para actualizar:  lina update" if hay else "  ✔ No hay versión nueva (o no he podido consultarlo).")
        return 0
    if not ctx.preguntar("Se instaló con pip. ¿Ejecuto pip install --upgrade " + PAQUETE_PIP + "?"):
        return 1
    r = ctx.ejecutar([sys.executable, "-m", "pip", "install", "--upgrade", PAQUETE_PIP], capture_output=True, text=True)
    if r.returncode != 0:
        ctx.salida("  ✘ pip ha fallado: " + (r.stderr or r.stdout or "").strip()[-200:])
        return 1
    _reiniciar(ctx)
    ctx.salida("  ✔ Actualizada.")
    return 0


def principal(argv, ctx=None, git=None):
    if "-h" in argv or "--help" in argv:
        print(AYUDA)
        return 0
    ctx = ctx or INST.Contexto(si="--si" in argv or "-y" in argv)
    estado = RUT.ESTADO / ARCHIVO
    fuente = _fuente(ctx)
    ctx.salida("Actualizar Lina")
    if fuente:
        return _git_actualizar(ctx, fuente, "--comprobar" in argv, "--volver" in argv, estado, git)
    if "--volver" in argv:
        ctx.salida("  Volver atrás solo funciona si Lina se instaló con install.sh (desde git). Con pip:  pip install lina-asistente==VERSION")
        return 1
    return _pip_actualizar(ctx, "--comprobar" in argv)
