# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A17: activar Lina con un botón o una combinación de cualquier dispositivo que no sea un teclado (un mando, un pedal, un botón USB…).

Lo que garantiza, por hechos:
- **Apagado de fábrica** (`activacion.boton` vacío): no se abre ni se lee ningún dispositivo.
- **Nunca un teclado**: antes de abrir nada se mira lo que el dispositivo dice que tiene (en /sys, que lee cualquiera); si tiene teclas de letras,
  no se abre. Así nunca se lee lo que escribes.
- **Sin quedárselo**: se abre solo para leer y nunca se pide la exclusiva (no hay ioctl EVIOCGRAB): el botón llega también a lo que estés usando, y
  el dispositivo no pierde nada (un mando conserva la vibración).
- **Sin permisos nuevos**: solo se lee lo que tu usuario ya puede leer; si no, se dice y no se pide entrar en ningún grupo.
- **Privacidad**: de lo que llega, solo se mira el botón elegido; todo lo demás se descarta sin guardarse. En el registro solo «botón pulsado».
- **Nada de ningún dispositivo concreto en el código**: se identifica por su fabricante, su modelo y su nombre tal como los da el sistema.

El ajuste se escribe con el asistente (`lina boton aprender`), no a mano: «VVVV:PPPP Nombre del dispositivo: código+código».
"""
import os
import re
import select
import struct
import time
from pathlib import Path

from lina.nucleo.idioma import N_, T

SYSFS = Path("/sys/class/input")
DEV = Path("/dev/input")
EV_KEY = 1
EVENTO = struct.Struct("llHHi")                                  # struct input_event: timeval, tipo, código, valor
BITS = struct.calcsize("l") * 8                                  # los mapas de bits de /sys van en palabras del tamaño de un long
# Las teclas de letras (KEY_Q…KEY_P, KEY_A…KEY_L, KEY_Z…KEY_M en input-event-codes.h): con muchas de ellas, es un teclado
LETRAS = set(range(16, 26)) | set(range(30, 39)) | set(range(44, 51))
MIN_LETRAS = 10
VUELTA = 3                                                       # segundos entre miradas al ajuste y a los dispositivos
_AJUSTE = re.compile(r"^([0-9a-f]{4}):([0-9a-f]{4}) (.+): (\d{1,4}(?:\+\d{1,4}){0,3})$")
# Nombres legibles de los botones más comunes (input-event-codes.h); el resto se dice por su número
NOMBRES = {272: "BTN_LEFT", 273: "BTN_RIGHT", 274: "BTN_MIDDLE", 275: "BTN_SIDE", 276: "BTN_EXTRA", 304: "BTN_SOUTH (A)", 305: "BTN_EAST (B)",
           307: "BTN_NORTH (X)", 308: "BTN_WEST (Y)", 310: "BTN_TL (LB)", 311: "BTN_TR (RB)", 312: "BTN_TL2", 313: "BTN_TR2",
           314: "BTN_SELECT", 315: "BTN_START", 316: "BTN_MODE", 317: "BTN_THUMBL (L3)", 318: "BTN_THUMBR (R3)"}


# ======================= el ajuste =======================
def leer_ajuste(texto):
    """(fabricante, modelo, nombre, (códigos…)) o None si está vacío o no tiene la forma que escribe el asistente."""
    m = _AJUSTE.match(str(texto or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3), tuple(sorted({int(c) for c in m.group(4).split("+")}))


def escribir_ajuste(fabricante, modelo, nombre, codigos):
    nombre = re.sub(r"[\x00-\x1f:]", " ", str(nombre)).strip()[:80]
    return f"{fabricante}:{modelo} {nombre}: {'+'.join(str(c) for c in sorted(set(codigos)))}"


def nombre_codigo(codigo):
    return NOMBRES.get(codigo, str(codigo))


# ======================= los dispositivos, por /sys (sin abrir nada) =======================
def _leer(ruta):
    try:
        return Path(ruta).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _teclas(hexa):
    """Los códigos de EV_KEY a partir del mapa de bits de /sys (palabras en hexadecimal, la más alta primero)."""
    codigos = set()
    for i, palabra in enumerate(reversed(hexa.split())):
        try:
            valor = int(palabra, 16)
        except ValueError:
            return set()
        for b in range(BITS):
            if valor >> b & 1:
                codigos.add(i * BITS + b)
    return codigos


def dispositivos(sysfs=SYSFS, dev=DEV):
    """[{ruta, nombre, fabricante, modelo, teclas, teclado, legible}] de los dispositivos de entrada con botones. Solo lee /sys: no abre ninguno."""
    salida = []
    for d in sorted(Path(sysfs).glob("event*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        teclas = _teclas(_leer(d / "device" / "capabilities" / "key"))
        if not teclas:
            continue
        ruta = Path(dev) / d.name
        salida.append({"ruta": str(ruta), "nombre": _leer(d / "device" / "name"), "fabricante": _leer(d / "device" / "id" / "vendor").lower(),
                       "modelo": _leer(d / "device" / "id" / "product").lower(), "teclas": teclas,
                       "teclado": len(teclas & LETRAS) >= MIN_LETRAS, "legible": os.access(ruta, os.R_OK)})
    return salida


def buscar(ajuste, sysfs=SYSFS, dev=DEV):
    """(dispositivo o None, motivo): «listo», «no_conectado», «teclado», «sin_permiso» o «sin_boton» (el dispositivo no tiene esos botones)."""
    fab, mod, nombre, codigos = ajuste
    iguales = [d for d in dispositivos(sysfs, dev) if (d["fabricante"], d["modelo"], d["nombre"]) == (fab, mod, nombre)]
    if not iguales:
        return None, "no_conectado"
    for d in iguales:
        if d["teclado"]:
            continue
        if not set(codigos) <= d["teclas"]:
            continue
        if not d["legible"]:
            return d, "sin_permiso"
        return d, "listo"
    return (iguales[0], "teclado") if all(d["teclado"] for d in iguales) else (iguales[0], "sin_boton")


# ======================= leer sin quedárselo =======================
def abrir(ruta):
    """Solo lectura y sin bloquear. Nunca EVIOCGRAB: el dispositivo sigue llegando a todo lo demás."""
    return os.open(ruta, os.O_RDONLY | os.O_NONBLOCK)


def botones(bloque):
    """[(código, valor)] de los eventos de botón de un trozo leído; lo demás (ejes, sincronías…) se descarta."""
    return [(codigo, valor) for k in range(0, len(bloque) - EVENTO.size + 1, EVENTO.size)
            for _, _, tipo, codigo, valor in [EVENTO.unpack_from(bloque, k)] if tipo == EV_KEY]


class Combinacion:
    """Se dispara una vez cuando están pulsados a la vez todos los botones elegidos; vuelve a valer cuando se sueltan todos."""

    def __init__(self, codigos):
        self.codigos, self.pulsados, self.disparada = set(codigos), set(), False

    def ver(self, codigo, valor):
        if codigo not in self.codigos or valor == 2:             # otro botón (no se mira) o la repetición de uno mantenido
            return False
        (self.pulsados.add if valor else self.pulsados.discard)(codigo)
        if not self.pulsados:
            self.disparada = False
        if self.pulsados == self.codigos and not self.disparada:
            self.disparada = True
            return True
        return False


def vigilar(al_pulsar, ajuste=None, log=print, sysfs=SYSFS, dev=DEV, dormir=time.sleep, parar=None, vuelta=VUELTA):
    """El hilo de Lina: mira el ajuste cada pocos segundos (no hace falta reiniciar al cambiarlo), abre el dispositivo elegido cuando está y llama a
    `al_pulsar` cuando se pulsa la combinación. Con el ajuste vacío no abre nada. `parar`: un threading.Event para terminar (las pruebas)."""
    if ajuste is None:
        from lina.nucleo import ajustes as AJ

        def ajuste():
            return AJ.actuales(log=lambda m: None).get("activacion", "boton")
    fd, actual, combinacion, avisado = None, None, None, ""
    while not (parar and parar.is_set()):
        elegido = leer_ajuste(ajuste())
        if elegido != actual:
            if fd is not None:
                os.close(fd)
            fd, actual, combinacion, avisado = None, elegido, (Combinacion(elegido[3]) if elegido else None), ""
        if actual and fd is None:
            disp, motivo = buscar(actual, sysfs, dev)
            if motivo == "listo":
                try:
                    fd = abrir(disp["ruta"])
                    log(f"Botón de activación: vigilando «{actual[2]}»")
                except OSError as e:
                    motivo = f"no se puede abrir ({e.strerror})"
            if fd is None and motivo != avisado:
                log(f"Botón de activación: {motivo}")             # una vez por motivo; nunca qué se pulsa
                avisado = motivo
        if fd is None:
            dormir(vuelta)
            continue
        try:
            listo = select.select([fd], [], [], vuelta)[0]
            if listo:
                bloque = os.read(fd, EVENTO.size * 64)
                if not bloque:
                    raise OSError("sin datos")                   # se ha cerrado: como desconectado
                for codigo, valor in botones(bloque):
                    if combinacion.ver(codigo, valor):
                        log("Botón de activación pulsado")
                        al_pulsar()
        except BlockingIOError:
            continue
        except OSError:
            log("Botón de activación: el dispositivo se ha desconectado; lo espero")
            os.close(fd)
            fd, avisado = None, "desconectado"
            combinacion = Combinacion(actual[3])
    if fd is not None:
        os.close(fd)


# ======================= el asistente: pulsas y se apunta =======================
def aprender(salida=print, entrada=input, sysfs=SYSFS, dev=DEV, espera=15, ahora=time.monotonic):
    """Abre (solo para leer) los dispositivos que no son teclado y que tu usuario puede leer, espera a que mantengas un botón o una combinación y la
    sueltes, y devuelve el ajuste (o None). Solo se miran los botones; nada se guarda salvo lo que elijas."""
    candidatos = [d for d in dispositivos(sysfs, dev) if not d["teclado"] and d["legible"]]
    sin_permiso = [d for d in dispositivos(sysfs, dev) if not d["teclado"] and not d["legible"]]
    if not candidatos:
        salida(T("No encuentro ningún dispositivo que no sea un teclado y que tu usuario pueda leer. Conecta el mando (o el pedal) y vuelve a probar."))
        if sin_permiso:
            salida(T("Hay {n} que tu usuario no puede leer; Lina no pide permisos nuevos para eso.", n=len(sin_permiso)))
        return None
    abiertos = {}
    for d in candidatos:
        try:
            abiertos[abrir(d["ruta"])] = d
        except OSError:
            pass
    salida(T("Mantén pulsado el botón o la combinación que quieras y suéltalo (tienes {s} s). Los teclados no se leen.", s=espera))
    pulsados, maximo, elegido = {}, {}, None
    fin = ahora() + espera
    try:
        while ahora() < fin and elegido is None and abiertos:
            for fd in select.select(list(abiertos), [], [], 0.2)[0]:
                try:
                    bloque = os.read(fd, EVENTO.size * 64)
                except BlockingIOError:
                    continue
                except OSError:
                    bloque = b""
                if not bloque:
                    abiertos.pop(fd, None)                   # se ha desconectado: se cierra y se deja de mirar
                    os.close(fd)
                    continue
                eventos = botones(bloque)
                for codigo, valor in eventos:
                    if valor == 2:
                        continue
                    p = pulsados.setdefault(fd, set())
                    (p.add if valor else p.discard)(codigo)
                    if valor:
                        maximo.setdefault(fd, set()).update(p)
                    if not p and maximo.get(fd):
                        elegido = (abiertos[fd], tuple(sorted(maximo[fd])))
                        break
                if elegido:
                    break
    finally:
        for fd in abiertos:
            os.close(fd)
    if not elegido:
        salida(T("No he visto ningún botón. No cambio nada."))
        return None
    d, codigos = elegido
    if len(codigos) > 4:
        salida(T("Son demasiados botones a la vez ({n}); prueba con uno o con una combinación de hasta cuatro.", n=len(codigos)))
        return None
    salida(T("He visto en «{nombre}»: {botones}.", nombre=d["nombre"], botones=" + ".join(nombre_codigo(c) for c in codigos)))
    salida(T("Ese botón llegará también a lo que estés usando (Lina no se queda el dispositivo): mejor uno o una combinación que no uses en tus juegos."))
    if str(entrada(T("¿Lo guardo? [s/N] "))).strip().lower() not in ("s", "si", "sí", "y", "yes"):
        salida(T("No cambio nada."))
        return None
    return escribir_ajuste(d["fabricante"], d["modelo"], d["nombre"], codigos)


# ======================= lina boton =======================
AYUDA = N_("""lina boton              qué botón activa a Lina y si está conectado
lina boton aprender     pulsas el botón o la combinación (de un mando, un pedal… nunca un teclado) y se apunta
lina boton quitar       vuelve a lo de fábrica: ningún botón""")


def estado(texto, sysfs=SYSFS, dev=DEV):
    """(«apagado» | «mal» | motivo de buscar(), ajuste leído o None)."""
    if not str(texto or "").strip():
        return "apagado", None
    elegido = leer_ajuste(texto)
    if not elegido:
        return "mal", None
    return buscar(elegido, sysfs, dev)[1], elegido


def principal(argv, salida=print, entrada=input, ajustes=None, sysfs=SYSFS, dev=DEV):
    if ajustes is None:
        from lina.nucleo import ajustes as AJ
        ajustes = AJ.actuales(log=lambda m: None)
    orden = argv[0] if argv else ""
    if orden == "aprender":
        nuevo = aprender(salida, entrada, sysfs, dev)
        if nuevo:
            ajustes.establecer("activacion", "boton", nuevo)
            salida(T("Guardado. Lina lo usa en unos segundos, sin reiniciar. Para quitarlo:  lina boton quitar"))
            return 0
        return 1
    if orden == "quitar":
        ajustes.establecer("activacion", "boton", "")
        salida(T("Quitado: ningún botón activa a Lina (el atajo de teclado sigue igual)."))
        return 0
    if orden in ("ayuda", "-h", "--help"):
        salida(T(AYUDA))
        return 0
    if orden:
        salida(T(AYUDA))
        return 2
    motivo, elegido = estado(ajustes.get("activacion", "boton"), sysfs, dev)
    salida(texto_estado(motivo, elegido))
    return 0


def texto_estado(motivo, elegido):
    if motivo == "apagado":
        return T("Ningún botón activa a Lina (de fábrica). Para elegir uno:  lina boton aprender")
    if motivo == "mal":
        return T("El ajuste activacion.boton no tiene la forma que escribe el asistente. Vuelve a elegirlo:  lina boton aprender")
    botones_ = " + ".join(nombre_codigo(c) for c in elegido[3])
    textos = {"listo": T("«{nombre}»: {botones}. Conectado y se puede leer.", nombre=elegido[2], botones=botones_),
              "no_conectado": T("«{nombre}»: {botones}. Ahora no está conectado; Lina lo abrirá cuando lo esté.", nombre=elegido[2], botones=botones_),
              "sin_permiso": T("«{nombre}»: {botones}. Está conectado, pero tu usuario no puede leerlo; Lina no pide permisos nuevos.", nombre=elegido[2], botones=botones_),
              "teclado": T("«{nombre}» es un teclado: Lina no lee teclados. Elige otro dispositivo:  lina boton aprender", nombre=elegido[2]),
              "sin_boton": T("«{nombre}» no tiene esos botones. Vuelve a elegirlos:  lina boton aprender", nombre=elegido[2])}
    return textos.get(motivo, motivo)
