# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina di "frase"`: hablarle por texto a la Lina en marcha, por un socket Unix local.

El socket vive en $XDG_RUNTIME_DIR/lina (solo tuyo, se vacía al cerrar sesión), con permisos 0600, y además cada conexión se comprueba con
SO_PEERCRED: solo se atiende a tu mismo usuario. Protocolo de líneas JSON:
  cliente → {"texto": "...", "voz": false}       y, si pulsas Ctrl+C, {"para": true}
  Lina    → {"dice": "..."} por cada frase, y al final {"fin": true, "pendiente": bool}
            o, sin atenderla, {"ocupada": true} / {"error": "..."}
La petición entra con origen «texto»: como el atajo, pero sin confirmar acciones críticas ni subir el tope (eso lo decide asistente.py).
"""
import json
import os
import select
import socket
import struct
import threading
import time

from lina.nucleo.idioma import N_, T

MAX_TEXTO = 2000                 # caracteres de la frase
MAX_LINEA = 16 * 1024            # bytes de una línea del protocolo
ESPERA = 180                     # segundos que espera el cliente a que termine la petición

OK, NO_ARRANCADA, USO, OCUPADA, SIN_RESPUESTA, INTERRUMPIDO = 0, 1, 2, 3, 4, 130


# ---------------------------------------------------------------- comunes
def _enviar(conn, dato, cerrojo=None):
    linea = (json.dumps(dato, ensure_ascii=False) + "\n").encode("utf-8")
    if cerrojo is None:
        conn.sendall(linea)
        return
    with cerrojo:
        conn.sendall(linea)


def _leer_linea(conn, resto=b"", maximo=MAX_LINEA):
    """(línea, lo que sobra). Línea None si se cerró la conexión antes de terminarla; ValueError si es demasiado larga."""
    datos = resto
    while b"\n" not in datos:
        if len(datos) > maximo:
            raise ValueError("línea demasiado larga")
        trozo = conn.recv(4096)
        if not trozo:
            return None, b""
        datos += trozo
    linea, _, resto = datos.partition(b"\n")
    if len(linea) > maximo:
        raise ValueError("línea demasiado larga")
    return linea, resto


def validar_texto(texto):
    """La frase limpia, o ValueError con el motivo."""
    if not isinstance(texto, str):
        raise ValueError(T("falta la frase"))
    texto = texto.strip()
    if not texto:
        raise ValueError(T("falta la frase"))
    if "\n" in texto or "\r" in texto:
        raise ValueError(T("la frase tiene que ir en una sola línea"))
    if len(texto) > MAX_TEXTO:
        raise ValueError(T("la frase es demasiado larga (como mucho {n} caracteres)", n=MAX_TEXTO))
    return texto


# ---------------------------------------------------------------- servidor (dentro de la Lina en marcha)
def uid_de(conn):
    """El usuario del proceso al otro lado del socket (SO_PEERCRED: pid, uid, gid)."""
    _, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    return uid


def crear(ruta):
    """El socket escuchando en `ruta`, 0600. Lo que quedara de una vez anterior se borra (un socket viejo no sirve de nada)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(ruta.parent, 0o700)
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    viejo = os.umask(0o177)                     # que no exista ni un instante con más permisos
    try:
        s.bind(str(ruta))
    finally:
        os.umask(viejo)
    os.chmod(ruta, 0o600)
    s.listen(4)
    return s


def atender(conn, lina, uid=uid_de, log=print):
    """Una conexión: comprueba quién es, lee la frase y la pasa a `lina` (empezar_texto, esperar_texto, parar_texto, fin_texto)."""
    cerrojo = threading.Lock()
    try:
        if uid(conn) != os.getuid():
            log("Canal: conexión de otro usuario: la cierro")
            return
        try:
            linea, resto = _leer_linea(conn)
            if linea is None:
                return
            pedido = json.loads(linea.decode("utf-8"))
            texto = validar_texto(pedido.get("texto") if isinstance(pedido, dict) else None)
        except (ValueError, UnicodeDecodeError) as e:
            _enviar(conn, {"error": str(e)})
            return
        vivo = [True]

        def enviar(frase):
            if not vivo[0]:
                return
            try:
                _enviar(conn, {"dice": str(frase)}, cerrojo)
            except OSError:
                vivo[0] = False                 # el cliente se fue (se le acabó la espera): Lina sigue con la tarea igualmente

        if not lina.empezar_texto(texto, bool(pedido.get("voz")), enviar):
            _enviar(conn, {"ocupada": True})
            return
        while not lina.esperar_texto(0.2):
            if not vivo[0]:
                continue
            try:
                listo, _, _ = select.select([conn], [], [], 0)
                if not listo:
                    continue
                linea, resto = _leer_linea(conn, resto)
            except (OSError, ValueError):
                linea = None
            if linea is None:
                vivo[0] = False                 # se cerró sin pedir que pare: no se cancela nada
                continue
            try:
                if json.loads(linea.decode("utf-8")).get("para"):
                    log("Canal: Ctrl+C en la terminal: cancelo la petición")
                    lina.parar_texto()
            except (ValueError, UnicodeDecodeError, AttributeError):
                pass
        final = lina.fin_texto()
        if vivo[0]:
            _enviar(conn, {"fin": True, "pendiente": bool(final.get("pendiente"))}, cerrojo)
    except OSError as e:
        log(f"Canal: {e!r}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def servir(ruta, lina, log=print, uid=uid_de):
    """El hilo que escucha `lina di`. Cada conexión, en su propio hilo (la de una petición ocupada se rechaza al momento)."""
    try:
        s = crear(ruta)
    except OSError as e:
        log(f"Canal: no he podido crear {ruta} ({e!r}); lina di no funcionará")
        return None
    log(f"Canal: escucho lina di en {ruta}")

    def bucle():
        while True:
            try:
                conn, _ = s.accept()
            except OSError:
                return                          # se cerró al salir
            threading.Thread(target=atender, args=(conn, lina), kwargs={"uid": uid, "log": log}, daemon=True).start()
    threading.Thread(target=bucle, daemon=True).start()
    return s


def cerrar(s, ruta):
    try:
        if s is not None:
            s.close()
        ruta.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- cliente (lina di)
AYUDA = N_("lina di [--voz] [--esperar N] \"FRASE\"\n    Le dices algo por escrito a la Lina en marcha, como si lo dijeras con el atajo, y la respuesta sale aquí.\n"
           "    --voz: también en voz alta.  --esperar N: segundos que espera la respuesta (de fábrica, 180).\n"
           "    Lo que pide confirmación no se confirma por aquí: pulsa el atajo y di «sí».")


def principal(argv, ruta=None, salida=print, error=None):
    import sys
    from lina.nucleo import rutas as RUT
    error = error or (lambda t: print(t, file=sys.stderr))
    voz, esperar, palabras = False, ESPERA, []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ("-h", "--help", "ayuda"):
            salida(T(AYUDA))
            return OK
        if a == "--voz":
            voz = True
        elif a == "--esperar" and args:
            try:
                esperar = max(1, int(args.pop(0)))
            except ValueError:
                error(T(AYUDA))
                return USO
        else:
            palabras.append(a)
    if not palabras:
        error(T(AYUDA))
        return USO
    return di(ruta or RUT.SOCKET, " ".join(palabras), voz=voz, esperar=esperar, salida=salida, error=error)

def di(ruta, texto, voz=False, esperar=ESPERA, salida=print, error=print):
    """Manda la frase a la Lina en marcha y escribe lo que dice. Devuelve el código de salida."""
    try:
        texto = validar_texto(texto)
    except ValueError as e:
        error(T("No la mando: {e}.", e=e))
        return USO
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.connect(str(ruta))
    except OSError:
        c.close()
        error(T("Lina no está en marcha. Arráncala con:  systemctl --user start lina"))
        return NO_ARRANCADA
    limite = time.monotonic() + esperar
    resto = b""
    try:
        _enviar(c, {"texto": texto, "voz": bool(voz)})
        while True:
            queda = limite - time.monotonic()
            if queda <= 0:
                error(T("Lina no ha terminado en {s} s; sigue con ello (lo que diga, en su registro).", s=esperar))
                return SIN_RESPUESTA
            c.settimeout(min(queda, 1.0))
            try:
                linea, resto = _leer_linea(c, resto)
            except socket.timeout:
                continue
            if linea is None:
                error(T("Lina ha cerrado la conexión sin terminar."))
                return SIN_RESPUESTA
            dato = json.loads(linea.decode("utf-8"))
            if "dice" in dato:
                salida(dato["dice"])
            elif dato.get("ocupada"):
                error(T("Estoy con otra cosa; prueba cuando termine."))
                return OCUPADA
            elif "error" in dato:
                error(T("No la mando: {e}.", e=dato["error"]))
                return USO
            elif dato.get("fin"):
                if dato.get("pendiente"):
                    salida(T("Pendiente de tu confirmación: pulsa el atajo y di «sí» (o «cancela»)."))
                return OK
    except KeyboardInterrupt:
        try:
            _enviar(c, {"para": True})
        except OSError:
            pass
        error(T("Le he pedido que pare."))
        return INTERRUMPIDO
    except (OSError, ValueError) as e:
        error(T("Se ha cortado la conexión con Lina ({e}).", e=type(e).__name__))
        return SIN_RESPUESTA
    finally:
        c.close()
