"""`lina olvidar`: borra lo que Lina guarda sobre ti. Siempre enseña antes qué y cuánto, y pide confirmación. No toca tus ajustes, claves, voces ni el gasto."""
import shutil
import subprocess
import sys
from pathlib import Path

from lina.nucleo import rutas as RUT

QUE = {
    "diario": ("el diario de cambios y las copias para deshacer (después no podrás deshacer lo anterior)", lambda: [RUT.DATOS / "diario"]),
    "acciones": ("el registro de las órdenes que se han ejecutado", lambda: [RUT.REGISTRO_ACCIONES, RUT.REGISTRO_ACCIONES.with_name(RUT.REGISTRO_ACCIONES.name + ".1")]),
    "recetas": ("las recetas aprendidas (cómo cambiar ajustes concretos)", lambda: [RUT.DATOS / "recetas.json"]),
    "registro": ("el registro del sistema de tu usuario (journalctl --user): incluye lo que dijiste y contesté", lambda: []),
}
TODO = ("diario", "acciones", "recetas", "registro")


def _tamano(ruta):
    ruta = Path(ruta)
    try:
        if ruta.is_dir():
            return sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file())
        return ruta.stat().st_size if ruta.exists() else 0
    except OSError:
        return 0


def _mb(n):
    return f"{n / 1_000_000:.1f} MB" if n >= 100_000 else f"{n / 1000:.0f} KB"


def borrar(que, ejecutar=subprocess.run):
    """Borra una categoría. Devuelve una línea para el usuario."""
    if que == "registro":
        try:
            ejecutar(["journalctl", "--user", "--rotate"], capture_output=True, timeout=30)
            r = ejecutar(["journalctl", "--user", "--vacuum-time=1s"], capture_output=True, text=True, timeout=30)
            return "Registro del sistema: " + ((r.stdout or r.stderr or "").strip().splitlines() or ["hecho"])[-1]
        except (OSError, subprocess.SubprocessError) as e:
            return f"Registro del sistema: no he podido ({e}). A mano:  journalctl --user --rotate && journalctl --user --vacuum-time=1s"
    n = 0
    for ruta in QUE[que][1]():
        n += _tamano(ruta)
        if ruta.is_dir():
            shutil.rmtree(ruta, ignore_errors=True)
        else:
            ruta.unlink(missing_ok=True)
    return f"Borrado: {que} ({_mb(n)})."


def principal(argv, entrada=input, salida=print, ejecutar=subprocess.run, es_terminal=None):
    terminal = sys.stdin.isatty() if es_terminal is None else es_terminal
    pedidos = list(TODO) if argv[:1] == ["todo"] else list(argv)
    if not pedidos:
        salida("Lo que Lina guarda de ti y se puede borrar:")
        for k, (texto, rutas) in QUE.items():
            tam = sum(_tamano(r) for r in rutas())
            salida(f"  lina olvidar {k:9} {texto}" + (f"  [{_mb(tam)}]" if rutas() else ""))
        salida("  lina olvidar todo      todo lo anterior\nNo toca tus ajustes, claves, voces ni el contador de gasto.")
        return 0
    malos = [p for p in pedidos if p not in QUE]
    if malos:
        salida(f"No sé olvidar «{malos[0]}». Mira lo que hay con:  lina olvidar")
        return 2
    if not terminal:
        salida("Borrar se decide en una terminal, tecleándolo tú.")
        return 2
    salida("Se va a borrar, sin posibilidad de recuperarlo:")
    for k in pedidos:
        salida(f"  · {QUE[k][0]}" + (f"  [{_mb(sum(_tamano(r) for r in QUE[k][1]()))}]" if QUE[k][1]() else ""))
    try:
        r = entrada("¿Seguro? Escribe «sí» para borrar: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        r = ""
    if r not in ("si", "sí", "s"):
        salida("No se ha borrado nada.")
        return 1
    for k in pedidos:
        salida(borrar(k, ejecutar))
    return 0
