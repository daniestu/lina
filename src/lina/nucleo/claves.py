# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Claves de acceso (Gemini, Tavily, servidores MCP…).

Se guardan en el llavero del sistema (Secret Service: GNOME Keyring, KWallet…) cuando lo hay, usando `secret-tool`; si no, en un archivo que solo
puedes leer tú (permisos 600) dentro de ~/.config/lina. Nunca se escriben en pantalla, ni se dictan por voz, ni aparecen en el registro:
`proteger_salida()` tapa en todo lo que Lina imprime tanto las claves que conoce como cualquier cosa con forma de clave.

  lina clave                    muestra qué claves hay y dónde están (sin enseñarlas)
  lina clave gemini             guarda la clave gratuita de Gemini
  lina clave pago               guarda la clave de pago de Gemini (te pide antes el tope mensual, que es obligatorio)
  lina clave NOMBRE             guarda otra clave (por ejemplo GITHUB_TOKEN para un servidor MCP)
  lina clave borrar NOMBRE      la quita de donde esté
  lina clave migrar             pasa al llavero las que estén en archivos
"""
import getpass
import os
import re
import shutil
import subprocess
import sys

from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T
from lina.nucleo.idioma import N_

CONOCIDAS = {"gemini": ("gemini.key", N_("clave gratuita de Gemini")), "gemini_pago": ("gemini_pago.key", N_("clave de pago de Gemini")),
             "tavily": ("tavily.key", N_("clave de Tavily (búsqueda)")),
             "openai": ("openai.key", N_("clave de OpenAI (o del servicio compatible que uses)")), "anthropic": ("anthropic.key", N_("clave de Anthropic"))}
ALIAS = {"gemini-pago": "gemini_pago", "pago": "gemini_pago", "gratis": "gemini", "gratuita": "gemini"}
SERVICIO = "lina"
ARCHIVO_MCP = "mcp_claves.env"
TIEMPO_LLAVERO = 8                      # segundos: si el llavero está bloqueado y pide desbloquearse, no se espera eternamente

_cache: dict = {}
BUSCAR = shutil.which                    # dónde está un programa (se cambia en las pruebas)


def normalizar(nombre):
    n = str(nombre or "").strip()
    n = ALIAS.get(n.lower(), n.lower() if n.lower() in CONOCIDAS else n)
    return n


def _valido(nombre):
    return nombre in CONOCIDAS or bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nombre or ""))


# ----------------------------------------------------------------------------------------------------------------------
# Llavero del sistema (secret-tool, del paquete libsecret)
# ----------------------------------------------------------------------------------------------------------------------
def _secret_tool(args, entrada=None, ejecutar=subprocess.run):
    """(código, salida) de `secret-tool`; código None si no está instalado o tarda demasiado."""
    try:
        r = ejecutar(["secret-tool", *args], input=entrada, capture_output=True, text=True, timeout=TIEMPO_LLAVERO)
        return r.returncode, (r.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return None, ""


def llavero_guardar(nombre, valor, ejecutar=subprocess.run):
    cod, _ = _secret_tool(["store", T("--label=Lina: {nombre}", nombre=nombre), "service", SERVICIO, "nombre", nombre], entrada=valor, ejecutar=ejecutar)
    if cod != 0:
        return False
    return llavero_leer(nombre, ejecutar) == valor                  # se comprueba leyendo: no se da por guardada una clave que no se puede recuperar


def llavero_leer(nombre, ejecutar=subprocess.run):
    cod, salida = _secret_tool(["lookup", "service", SERVICIO, "nombre", nombre], ejecutar=ejecutar)
    return salida.strip() if cod == 0 else ""


def llavero_borrar(nombre, ejecutar=subprocess.run):
    cod, _ = _secret_tool(["clear", "service", SERVICIO, "nombre", nombre], ejecutar=ejecutar)
    return cod == 0


def llavero_disponible(ejecutar=subprocess.run):
    """¿Está instalado secret-tool? (No admite --version, así que se mira si existe; que el llavero funcione de verdad se comprueba al guardar, leyendo de vuelta.)"""
    return bool(BUSCAR("secret-tool"))


# ----------------------------------------------------------------------------------------------------------------------
# Archivos con permisos 600 (respaldo)
# ----------------------------------------------------------------------------------------------------------------------
def _ruta_archivo(nombre):
    return RUT.CONFIG / (CONOCIDAS[nombre][0] if nombre in CONOCIDAS else ARCHIVO_MCP)


def archivo_leer(nombre):
    ruta = _ruta_archivo(nombre)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return ""
    if nombre in CONOCIDAS:
        return texto.strip()
    for linea in texto.splitlines():
        k, _, v = linea.partition("=")
        if k.strip() == nombre:
            return v.strip()
    return ""


def archivo_guardar(nombre, valor):
    ruta = _ruta_archivo(nombre)
    if nombre in CONOCIDAS:
        AJ.escribir_privado(ruta, valor + "\n")
    else:
        try:
            previas = [l for l in ruta.read_text(encoding="utf-8").splitlines() if l.split("=", 1)[0].strip() != nombre]
        except OSError:
            previas = []
        AJ.escribir_privado(ruta, "\n".join(previas + [f"{nombre}={valor}"]) + "\n")
    return ruta


def archivo_borrar(nombre):
    ruta = _ruta_archivo(nombre)
    if nombre in CONOCIDAS:
        try:
            ruta.unlink()
            return True
        except OSError:
            return False
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    resto = [l for l in lineas if l.split("=", 1)[0].strip() != nombre]
    if len(resto) == len(lineas):
        return False
    AJ.escribir_privado(ruta, "\n".join(resto) + ("\n" if resto else ""))
    return True


# ----------------------------------------------------------------------------------------------------------------------
# Lo que usa el resto de Lina
# ----------------------------------------------------------------------------------------------------------------------
def _quiere_llavero():
    try:
        if not (RUT.CONFIG / AJ.NOMBRE_ARCHIVO).exists():
            return True                                          # sin ajustes todavía: «auto». Leer una clave no debe crear el archivo
        return AJ.actuales(log=lambda m: None).get("privacidad", "almacen_claves") != "archivo"
    except Exception:
        return True


def obtener(nombre, ejecutar=subprocess.run):
    """El valor de la clave (llavero y, si no está ahí, archivo), o «» si no hay."""
    nombre = normalizar(nombre)
    if nombre in _cache:
        return _cache[nombre]
    valor = (llavero_leer(nombre, ejecutar) if _quiere_llavero() else "") or archivo_leer(nombre)
    if valor:
        _cache[nombre] = valor
    return valor


def donde_esta(nombre, ejecutar=subprocess.run):
    """'llavero', 'archivo', 'los dos' o '' (sin guardar)."""
    nombre = normalizar(nombre)
    ll = bool(_quiere_llavero() and llavero_leer(nombre, ejecutar))
    ar = bool(archivo_leer(nombre))
    return "los dos" if ll and ar else "llavero" if ll else "archivo" if ar else ""


def guardar(nombre, valor, ejecutar=subprocess.run):
    """Guarda la clave: en el llavero si se puede (y se comprueba), y si no en un archivo 600. Devuelve (dónde, detalle)."""
    nombre = normalizar(nombre)
    valor = str(valor or "").strip()
    if not _valido(nombre) or not valor or "\n" in valor or "\r" in valor:
        raise ValueError(T("nombre o valor de clave no válidos"))
    _cache.pop(nombre, None)
    if _quiere_llavero() and llavero_guardar(nombre, valor, ejecutar):
        archivo_borrar(nombre)                                       # que no quede una copia en claro
        _cache[nombre] = valor
        return "llavero", T("el llavero del sistema")
    ruta = archivo_guardar(nombre, valor)
    _cache[nombre] = valor
    return "archivo", T("{ruta} (solo lo puedes leer tú; no he encontrado un llavero del sistema que funcione)", ruta=ruta)


def borrar(nombre, ejecutar=subprocess.run):
    nombre = normalizar(nombre)
    _cache.pop(nombre, None)
    a = llavero_borrar(nombre, ejecutar) if _quiere_llavero() else False
    b = archivo_borrar(nombre)
    return a or b


def migrar_a_llavero(ejecutar=subprocess.run):
    """Pasa al llavero las claves que estén en archivos. Devuelve [(nombre, movida)]. Solo borra el archivo si la clave se lee bien del llavero."""
    hechas = []
    if not llavero_disponible(ejecutar):
        return hechas
    nombres = list(CONOCIDAS) + _nombres_en_archivo_mcp()
    for n in nombres:
        v = archivo_leer(n)
        if not v:
            continue
        if llavero_guardar(n, v, ejecutar):
            archivo_borrar(n)
            _cache.pop(n, None)
            hechas.append((n, True))
        else:
            hechas.append((n, False))
    return hechas


def _nombres_en_archivo_mcp():
    try:
        return [l.split("=", 1)[0].strip() for l in (RUT.CONFIG / ARCHIVO_MCP).read_text(encoding="utf-8").splitlines()
                if "=" in l and not l.strip().startswith("#")]
    except OSError:
        return []


def valor_mcp(nombre, ejecutar=subprocess.run):
    """Valor de una variable ${NOMBRE} de un servidor MCP: entorno, llavero o archivo."""
    return os.environ.get(nombre) or obtener(nombre, ejecutar)


# ----------------------------------------------------------------------------------------------------------------------
# Que no salgan en el registro
# ----------------------------------------------------------------------------------------------------------------------
_PATRONES = [re.compile(p) for p in (r"AIza[0-9A-Za-z_\-]{30,}", r"\bsk-[A-Za-z0-9_\-]{20,}", r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"\bgithub_pat_[A-Za-z0-9_]{30,}",
                                      r"\btvly-[A-Za-z0-9_\-]{16,}", r"\bxox[abpr]-[A-Za-z0-9\-]{20,}")]
_CON_PREFIJO = re.compile(r"(?i)((?:bearer\s+|x-goog-api-key['\"]?\s*[:=]\s*['\"]?|api[_-]?key['\"]?\s*[:=]\s*['\"]?))([A-Za-z0-9._\-]{16,})")
TAPADA = "«clave»"


def limpiar(texto):
    """El texto sin ninguna clave: las que Lina conoce y cualquier cosa con forma de clave (Google, OpenAI/Anthropic, GitHub, Slack, Tavily, Bearer…)."""
    t = str(texto)
    for v in sorted((v for v in _cache.values() if len(v) >= 8), key=len, reverse=True):
        t = t.replace(v, TAPADA)
    for p in _PATRONES:
        t = p.sub(TAPADA, t)
    return _CON_PREFIJO.sub(lambda m: m.group(1) + TAPADA, t)


class FiltroSalida:
    """Envuelve stdout/stderr para tapar claves en todo lo que se imprima (y por tanto en el registro de journalctl)."""

    def __init__(self, flujo):
        self._flujo = flujo

    def write(self, s):
        return self._flujo.write(limpiar(s))

    def __getattr__(self, nombre):
        return getattr(self._flujo, nombre)


def proteger_salida():
    for nombre in ("stdout", "stderr"):
        flujo = getattr(sys, nombre)
        if not isinstance(flujo, FiltroSalida):
            setattr(sys, nombre, FiltroSalida(flujo))


# ----------------------------------------------------------------------------------------------------------------------
# lina clave
# ----------------------------------------------------------------------------------------------------------------------
def _pedir_tope(entrada, salida):
    """El tope mensual es obligatorio al añadir una clave de pago: se pide (número mayor que 0) y se guarda en config.toml."""
    aj = AJ.actuales(log=lambda m: None)
    actual = aj.get("gasto", "tope_mensual_eur")
    salida(T("La clave de pago cuesta dinero de verdad, así que hace falta un tope mensual (cuando se alcance, Lina deja de usarla sola)."))
    for _ in range(3):
        texto = entrada(T("Tope mensual en euros (obligatorio; ahora está en {actual:g}): ", actual=actual)).strip()
        try:
            tope = float(texto.replace(",", "."))
            if tope <= 0:
                raise ValueError
            AJ.validar("gasto", "tope_mensual_eur", tope)
            aj.establecer("gasto", "tope_mensual_eur", tope)
            salida(T("Tope mensual: {tope:g} €.", tope=tope))
            return tope
        except ValueError:
            salida(T("Escribe un número mayor que 0 (por ejemplo 10)."))
    return None


def principal(argv, entrada=input, secreto=getpass.getpass, salida=print, ejecutar=subprocess.run):
    if not argv:
        todas = list(CONOCIDAS) + [n for n in _nombres_en_archivo_mcp() if n not in CONOCIDAS]
        hay = False
        for n in todas:
            d = donde_esta(n, ejecutar)
            if d:
                hay = True
                salida(T("  {n:16} guardada en: {d}", n=n, d=d))
        if not hay:
            salida(T("No hay ninguna clave guardada. Para la de Gemini:  lina clave gemini"))
        salida(T("Llavero del sistema: ") + ("disponible" if llavero_disponible(ejecutar) else T("no encontrado (se usan archivos con permisos 600; instala libsecret para usarlo)")))
        return 0
    orden = argv[0]
    if orden == "migrar" and len(argv) == 1:
        movidas = migrar_a_llavero(ejecutar)
        if not movidas:
            salida(T("No había nada que mover (o el llavero del sistema no está disponible)."))
        for n, bien in movidas:
            salida(f"  {n}: " + (T("movida al llavero") if bien else T("no he podido guardarla en el llavero; sigue en su archivo")))
        return 0
    if orden == "borrar" and len(argv) == 2:
        n = normalizar(argv[1])
        salida(T("Clave {n} ", n=n) + (T("borrada.") if borrar(n, ejecutar) else T("no estaba guardada.")))
        return 0
    if len(argv) != 1 or not _valido(normalizar(orden)):
        salida(__doc__)
        return 2
    nombre = normalizar(orden)
    if nombre == "gemini_pago" and _pedir_tope(entrada, salida) is None:
        salida(T("Sin tope mensual no guardo la clave de pago."))
        return 1
    valor = secreto(T("Pega aquí {nombre} (no se ve al escribir): ", nombre=nombre)).strip()
    if not valor or "\n" in valor:
        salida(T("No has escrito nada; no se ha guardado."))
        return 1
    try:
        _, detalle = guardar(nombre, valor, ejecutar)
    except ValueError as e:
        salida(T("No se ha guardado: {e}.", e=e))
        return 1
    salida(T("Guardada {nombre} en {detalle}. Reinicia a Lina para que la use:  systemctl --user restart lina", nombre=nombre, detalle=detalle))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
