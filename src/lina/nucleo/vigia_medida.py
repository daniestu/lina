# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9g: el vigía de las medidas que ejecutan órdenes de verdad. Una foto de tu sistema real antes de empezar y otra después de cada petición; si algo ha
cambiado, la medida se para y dice qué.

Caso real (medida de A16b, 2026-11-22): dentro de una jaula «sin bus», `systemctl --user mask …` enmascaró el arranque de KDE Connect y otra orden paró
un temporizador, sin que la medida lo viera. La foto: el estado de las unidades de systemd de tu usuario y de sus temporizadores, lo que hay en
~/.config/autostart y ~/.config/systemd/user, los archivos de configuración de primer nivel de ~/.config y los nombres de lo que hay hasta dos niveles.
Solo mira (lee archivos y pregunta a systemd); no cambia nada. Lo que el escritorio cambia solo se descubre con dos fotos antes de empezar: lo que
difiere entre ellas cuenta como volátil, se enseña y no para la medida."""
import hashlib
import os
import subprocess
import time

from lina.nucleo.idioma import T

ESPERA_VOLATILES = 30          # segundos entre las dos fotos de antes de empezar
MAX_ARCHIVO = 2_000_000        # un archivo más grande se mira por tamaño y fecha, no por contenido


def _systemctl(args, ejecutar):
    try:
        r = ejecutar(["systemctl", "--user", *args, "--no-legend", "--no-pager", "--plain"], capture_output=True, text=True, timeout=20,
                     stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _huella(ruta):
    try:
        if os.path.islink(ruta):
            return "→ " + os.readlink(ruta)
        if os.path.getsize(ruta) > MAX_ARCHIVO:
            st = os.stat(ruta)
            return f"{st.st_size} bytes, {int(st.st_mtime)}"
        with open(ruta, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:16]
    except OSError:
        return "(no se puede leer)"


def foto(casa=None, ejecutar=subprocess.run):
    """{clave: valor} de lo que se vigila. Las claves dicen qué es («unidad:…», «temporizador:…», «archivo:…», «config:…», «existe:…»)."""
    casa = casa or os.path.expanduser("~")
    config = os.path.join(casa, ".config")
    datos = {}
    unidades = _systemctl(["list-unit-files"], ejecutar)
    if unidades is None:
        datos["unidad:(systemd)"] = "no responde"
    for linea in (unidades or "").splitlines():
        partes = linea.split()
        if len(partes) >= 2:
            datos[f"unidad:{partes[0]}"] = partes[1]
    for linea in (_systemctl(["list-units", "--type=timer", "--all"], ejecutar) or "").splitlines():
        partes = linea.split()
        if len(partes) >= 4:
            datos[f"temporizador:{partes[0]}"] = f"{partes[2]}/{partes[3]}"
    for sub in ("autostart", os.path.join("systemd", "user")):
        base = os.path.join(config, sub)
        for raiz, carpetas, archivos in os.walk(base, followlinks=False):
            for n in carpetas + archivos:
                ruta = os.path.join(raiz, n)
                if n in carpetas and not os.path.islink(ruta):
                    continue
                datos[f"archivo:{os.path.relpath(ruta, casa)}"] = _huella(ruta)
    try:
        primero = sorted(os.listdir(config))
    except OSError:
        primero = []
    for n in primero:
        ruta = os.path.join(config, n)
        datos[f"existe:.config/{n}"] = "sí"
        if os.path.isfile(ruta) or os.path.islink(ruta):
            datos[f"config:.config/{n}"] = _huella(ruta)
        elif os.path.isdir(ruta):
            try:
                for m in os.listdir(ruta):
                    datos[f"existe:.config/{n}/{m}"] = "sí"
            except OSError:
                pass
    return datos


def diferencias(antes, despues):
    """[(clave, antes, después)] de lo que ha cambiado, aparecido o desaparecido."""
    claves = sorted(set(antes) | set(despues))
    return [(k, antes.get(k), despues.get(k)) for k in claves if antes.get(k) != despues.get(k)]


def explicar(cambios, maximo=8):
    """Los cambios en frases cortas, para decirlo al parar."""
    lineas = []
    for clave, a, d in cambios[:maximo]:
        que, nombre = clave.split(":", 1)
        if a is None:
            lineas.append(T("ha aparecido {nombre} ({valor})", nombre=nombre, valor=d))
        elif d is None:
            lineas.append(T("ha desaparecido {nombre}", nombre=nombre))
        else:
            lineas.append(T("{nombre}: {antes} → {despues}", nombre=nombre, antes=a, despues=d))
    if len(cambios) > maximo:
        lineas.append(T("y {n} cambios más", n=len(cambios) - maximo))
    return lineas


class Vigia:
    """Uso: v = Vigia(); v.empezar(salida); … después de cada petición: if v.cambios(): parar."""

    def __init__(self, casa=None, ejecutar=subprocess.run, espera=ESPERA_VOLATILES, dormir=time.sleep):
        self.casa, self.ejecutar, self.espera, self.dormir = casa, ejecutar, espera, dormir
        self.base, self.volatiles = {}, set()

    def empezar(self, salida=print):
        salida(T("Miro tu sistema real antes de empezar ({s} s), para parar si la medida lo cambia…", s=self.espera))
        primera = foto(self.casa, self.ejecutar)
        self.dormir(self.espera)
        self.base = foto(self.casa, self.ejecutar)
        self.volatiles = {k for k, _, _ in diferencias(primera, self.base)}
        if self.volatiles:
            salida(T("Cambia solo, sin la medida (no la para): {lista}", lista=", ".join(sorted(k.split(":", 1)[1] for k in self.volatiles))[:300]))

    def cambios(self):
        """Lo que ha cambiado desde que empezó, sin lo volátil."""
        return [c for c in diferencias(self.base, foto(self.casa, self.ejecutar)) if c[0] not in self.volatiles]

    def parar_si_cambio(self, salida=print):
        """True (y lo dice) si la medida ha cambiado tu sistema real: quien llama se para."""
        cambios = self.cambios()
        if not cambios:
            return False
        salida(T("ME PARO: la medida ha cambiado tu sistema real. Lo que ha cambiado: {lista}. No deshago nada: decide tú.",
                 lista="; ".join(explicar(cambios))))
        return True


VigiaReal = Vigia          # el de verdad, también cuando las pruebas cambian Vigia por SinVigia (conftest)


class SinVigia:
    """Para las pruebas: no mira nada (las pruebas no pueden tocar tu sistema)."""

    def empezar(self, salida=print):
        pass

    def parar_si_cambio(self, salida=print):
        return False
