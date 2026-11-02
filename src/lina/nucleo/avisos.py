# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Avisos por iniciativa propia, opcionales y apagados de fábrica: disco casi lleno, batería baja y actualizaciones pendientes (A7).

Solo es una notificación de escritorio: Lina no habla, no llama a la IA y no cambia nada. Cada motivo avisa como mucho una vez al día, y la batería una vez
por descarga. Las actualizaciones se miran con órdenes fijas de solo lectura, sin privilegios. Un fallo al mirar nunca rompe nada: no hay aviso."""
import json
import os
import re
import shutil
import time
from pathlib import Path

from lina.nucleo import ajustes as AJ
from lina.nucleo import ejecucion as EJ
from lina.nucleo import plataforma as PL
from lina.nucleo import registro
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ARCHIVO = "avisos.json"
CADA_SEG = 300
DISCO_MINIMO_GB = 5
DISCO_MINIMO_PORCENTAJE = 5
BATERIA_MINIMA = 15
ACTUALIZACIONES_CADA_SEG = 6 * 3600
# (orden, códigos de salida que valen, líneas que son paquetes: lo que no encaje se ignora)
ACTUALIZACIONES = {"arch": (["checkupdates"], (0, 2), r"^\S+ \S+ -> \S+"),
                   "debian": (["apt", "list", "--upgradable"], (0,), r"^\S+/\S+ "),
                   "fedora": (["dnf", "-q", "check-update"], (0, 100), r"^\S+\.\S+\s+\S+\s+\S+$"),
                   "suse": (["zypper", "-q", "--no-refresh", "list-updates"], (0,), r"^v \|")}
TITULO = N_("Lina: aviso")
_ultima_mirada = [0.0]


def disco(ruta=None, uso=shutil.disk_usage):
    """El texto del aviso si queda poco sitio en tu carpeta personal; si no, None."""
    try:
        total, _, libre = uso(ruta or Path.home())
    except OSError:
        return None
    gb = libre / 1024 ** 3
    if gb >= DISCO_MINIMO_GB and libre * 100 / max(total, 1) >= DISCO_MINIMO_PORCENTAJE:
        return None
    return T("Te quedan {gb} GB libres en el disco.", gb=f"{gb:.1f}")


def bateria(carpeta="/sys/class/power_supply"):
    """(¿descargándose?, porcentaje) de la primera batería, o None si no hay."""
    try:
        for nombre in sorted(os.listdir(carpeta)):
            if nombre.startswith("BAT"):
                base = Path(carpeta) / nombre
                return base.joinpath("status").read_text().strip() == "Discharging", int(base.joinpath("capacity").read_text().strip())
    except (OSError, ValueError):
        pass
    return None


def actualizaciones(ejecutar=None, familia=None):
    """Cuántas actualizaciones hay pendientes, o None si no se ha podido saber (falta la orden, sin red…)."""
    ejecutar = ejecutar or (lambda orden: EJ._ejecutar_simple(orden, timeout=120))
    orden = ACTUALIZACIONES.get(familia or PL.detectar()["familia"])
    if not orden or not shutil.which(orden[0][0]):
        return None
    codigo, salida = ejecutar(orden[0])
    if codigo not in orden[1]:
        return None
    return sum(1 for linea in salida.splitlines() if re.match(orden[2], linea.strip()))


def _leer():
    try:
        d = json.loads((RUT.ESTADO / ARCHIVO).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir(d):
    try:
        RUT.ESTADO.mkdir(parents=True, exist_ok=True)
        (RUT.ESTADO / ARCHIVO).write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def pendientes(aj, ahora=None, bat=None, disc=None, act=None):
    """Los textos que toca avisar ahora con estos ajustes, y los marca como avisados."""
    ahora = time.time() if ahora is None else ahora
    bat, disc, act = bat or bateria, disc or disco, act or actualizaciones
    d, hoy, textos = _leer(), time.strftime("%Y-%m-%d", time.localtime(ahora)), []
    if aj.get("avisos", "disco") and d.get("disco") != hoy:
        texto = disc()
        if texto:
            d["disco"] = hoy
            textos.append(texto)
    if aj.get("avisos", "bateria"):
        estado = bat()
        if estado and estado[0] and estado[1] <= BATERIA_MINIMA:
            if not d.get("bateria"):
                d["bateria"] = True
                textos.append(T("Te queda el {n} % de batería.", n=estado[1]))
        else:                                                    # enchufada o por encima: la próxima descarga vuelve a avisar
            d.pop("bateria", None)
    if aj.get("avisos", "actualizaciones") and d.get("actualizaciones") != hoy and ahora - _ultima_mirada[0] >= ACTUALIZACIONES_CADA_SEG:
        _ultima_mirada[0] = ahora
        n = act()
        if n:
            d["actualizaciones"] = hoy
            textos.append(T("Tienes {n} actualizaciones pendientes.", n=n))
    _escribir(d)
    return textos


def vigilar(dormir=time.sleep, una_vez=False, notificar=registro.notificar):
    """El bucle de fondo. Lee los ajustes en cada vuelta: encenderlos no pide reiniciar."""
    while True:
        try:
            for texto in pendientes(AJ.actuales(log=lambda m: None)):
                notificar(T(TITULO), texto)
        except Exception as e:
            registro.log(f"Avisos: fallo {e!r}")
        if una_vez:
            return
        dormir(CADA_SEG)


def principal(argv, salida=print):
    """`lina avisos`: qué avisos tienes encendidos y qué diría cada uno ahora, sin notificar nada."""
    if argv:
        salida(T("Uso:  lina avisos   (se encienden con  lina config poner avisos.disco true, avisos.bateria o avisos.actualizaciones)"))
        return 2
    aj = AJ.actuales(log=lambda m: None)
    estado = bateria()
    n = actualizaciones()
    filas = [("disco", disco() or T("sin problema")),
             ("bateria", T("no hay batería") if estado is None else f"{estado[1]} %"),
             ("actualizaciones", T("no se ha podido saber") if n is None else str(n))]
    for clave, ahora in filas:
        salida(f"{clave:16} {T('encendido') if aj.get('avisos', clave) else T('apagado'):10} {ahora}")
    return 0
