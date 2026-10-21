# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Bajar lo que suena mientras Lina te escucha, como el coche cuando le hablas, y devolverlo a como estaba al terminar.

No toca el volumen general ni silencia nada: baja el volumen de CADA programa que está sonando (la serie, la canción, el juego) a una fracción de lo que tenía
y, al acabar, lo devuelve. Para que nunca se quede bajo:
  · se apunta lo bajado en un archivo; si Lina se cierra a medias, al arrancar lo devuelve;
  · un temporizador lo devuelve solo si la escucha se alarga demasiado;
  · si en medio tocaste tú el volumen de un programa, ese no se toca;
  · si algo falla (sin pactl, un programa que se cierra), no pasa nada: sigue todo como estaba."""
import json
import os
import re
import subprocess
import threading

from lina.nucleo import rutas as RUT

MAX_SEGUNDOS = 60               # una escucha no dura más; pasado esto se devuelve el volumen aunque nadie lo pida
NIVEL_POR_DEFECTO = 20          # % de lo que tenía
_PROPIOS = {"piper", "lina"}    # programas de Lina (su voz, sus pitidos) que nunca se bajan
FUENTE_ECO = "lina_eco"


def pactl(*args, tiempo=4):
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=tiempo)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def leer_programas(texto):
    """De la salida de `pactl list sink-inputs`: [{"id", "volumen" (%), "app"}] de los que suenan de verdad (ni pausados ni silenciados ni de Lina)."""
    salida = []
    for bloque in re.split(r"\n(?=Sink Input #)", texto or ""):
        m = re.match(r"\s*Sink Input #(\d+)", bloque)
        if not m or re.search(r"Corked:\s*yes", bloque) or re.search(r"Mute:\s*yes", bloque):
            continue
        porcentajes = [int(p) for p in re.findall(r"/\s*(\d+)%\s*/", (re.search(r"^\s*Volume:.*$", bloque, re.M) or [""])[0])]
        if not porcentajes:
            continue
        def propiedad(k, bloque=bloque):
            return (re.search(rf'{re.escape(k)}\s*=\s*"([^"]*)"', bloque) or [None, ""])[1]
        binario, pid = os.path.basename(propiedad("application.process.binary")).lower(), propiedad("application.process.id")
        if binario in _PROPIOS or pid == str(os.getpid()) or FUENTE_ECO in bloque:
            continue
        salida.append({"id": m.group(1), "volumen": round(sum(porcentajes) / len(porcentajes)), "app": propiedad("application.name") or binario})
    return salida


class Atenuador:
    def __init__(self, nivel=NIVEL_POR_DEFECTO, ejecutar=pactl, archivo=None, log=print, segundos=MAX_SEGUNDOS):
        self.nivel, self.ejecutar, self.log, self.segundos = max(0, min(100, int(nivel))), ejecutar, log, segundos
        self.archivo = archivo or (RUT.EJECUCION / "sonido_bajado.json")
        self.bajados = {}                       # id → {"original", "bajado", "app"}
        self.duenos = set()                     # quién ha pedido bajarlo (el atajo, el manos libres): se devuelve cuando ya no queda nadie
        self.cerrojo = threading.RLock()
        self.reloj = None

    # ----- archivo de seguridad
    def _apuntar(self):
        try:
            self.archivo.parent.mkdir(parents=True, exist_ok=True)
            if self.bajados:
                self.archivo.write_text(json.dumps(self.bajados), encoding="utf-8")
            else:
                self.archivo.unlink(missing_ok=True)
        except OSError:
            pass

    def _devolver(self, bajados):
        """Devuelve el volumen a lo apuntado, salvo a los programas que ya no existen o cuyo volumen has tocado tú."""
        if not bajados:
            return 0
        ahora = {p["id"]: p for p in leer_programas(self.ejecutar("list", "sink-inputs"))}
        devueltos = 0
        for ident, d in bajados.items():
            actual = ahora.get(ident)
            if actual is None or abs(actual["volumen"] - d["bajado"]) > 3 or (d.get("app") and actual["app"] != d["app"]):
                continue
            self.ejecutar("set-sink-input-volume", ident, f"{d['original']}%")
            devueltos += 1
        return devueltos

    # ----- uso
    def bajar(self, dueno="atajo"):
        """Baja lo que suena. Se puede llamar varias veces; no hace nada si ya está bajado."""
        with self.cerrojo:
            self.duenos.add(dueno)
            if self.bajados:
                return len(self.bajados)
            for p in leer_programas(self.ejecutar("list", "sink-inputs")):
                bajado = max(0, round(p["volumen"] * self.nivel / 100))
                if bajado >= p["volumen"]:
                    continue
                self.ejecutar("set-sink-input-volume", p["id"], f"{bajado}%")
                self.bajados[p["id"]] = {"original": p["volumen"], "bajado": bajado, "app": p["app"]}
            self._apuntar()
            if self.bajados:
                self.log(f"Sonido: bajo lo que suena mientras te escucho ({', '.join(sorted({d['app'] for d in self.bajados.values() if d['app']})) or 'programas'})")
                if self.reloj:
                    self.reloj.cancel()
                self.reloj = threading.Timer(self.segundos, self.subir, kwargs={"todos": True})
                self.reloj.daemon = True
                self.reloj.start()
            return len(self.bajados)

    def subir(self, dueno="atajo", todos=False):
        """Devuelve el volumen cuando ya nadie lo necesita bajo (o ya, si `todos`)."""
        with self.cerrojo:
            self.duenos.discard(dueno)
            if todos:
                self.duenos.clear()
            if self.duenos or not self.bajados:
                return 0
            bajados, self.bajados = self.bajados, {}
            if self.reloj:
                self.reloj.cancel()
                self.reloj = None
            n = self._devolver(bajados)
            self._apuntar()
            if n:
                self.log("Sonido: devuelto a como estaba")
            return n

    def recuperar(self):
        """Al arrancar: si Lina se cerró con el sonido bajado, lo devuelve."""
        try:
            bajados = json.loads(self.archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        if not isinstance(bajados, dict):
            return 0
        n = self._devolver({k: v for k, v in bajados.items() if isinstance(v, dict) and {"original", "bajado"} <= set(v)})
        self.archivo.unlink(missing_ok=True)
        if n:
            self.log("Sonido: Lina se cerró con el volumen bajado; lo devuelvo a como estaba")
        return n
