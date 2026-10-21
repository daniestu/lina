# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Controlar la música de Lina (mpv con socket) y no creerse el «hecho» de playerctl cuando no hay nada que controlar."""
import json
import socket
import subprocess
import threading

import pytest

from lina.nucleo import herramientas as H
from lina.nucleo import reproductor as RP


class MpvFalso:
    """Un servidor en un socket Unix que se comporta como el de mpv: manda un evento suelto y luego responde con el request_id."""
    def __init__(self, ruta, error="success", cierra_al_salir=True):
        self.recibidos, self.error, self.cierra = [], error, cierra_al_salir
        self.servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.servidor.bind(str(ruta))
        self.servidor.listen(1)
        threading.Thread(target=self.atender, daemon=True).start()

    def atender(self):
        conexion, _ = self.servidor.accept()
        with conexion, conexion.makefile("rw", encoding="utf-8") as f:
            f.write(json.dumps({"event": "property-change", "name": "pause"}) + "\n"); f.flush()
            for linea in f:
                orden = json.loads(linea)
                self.recibidos.append(orden["command"])
                if orden["command"] == ["quit"] and self.cierra:
                    return                                   # mpv sale sin contestar
                f.write(json.dumps({"error": self.error, "request_id": orden["request_id"]}) + "\n"); f.flush()


@pytest.mark.parametrize("accion,esperado", [
    ("pausar", ["set_property", "pause", True]), ("reanudar", ["set_property", "pause", False]),
    ("siguiente", ["playlist-next"]), ("anterior", ["playlist-prev"]), ("detener", ["quit"]),
])
def test_ordenes_al_mpv_de_lina(tmp_path, accion, esperado):
    ruta = tmp_path / "m.sock"
    mpv = MpvFalso(ruta)
    assert RP.enviar_mpv(accion, ruta) is True and mpv.recibidos == [esperado]


def test_si_mpv_rechaza_la_orden_o_no_hay_mpv_no_se_da_por_hecho(tmp_path):
    ruta = tmp_path / "m.sock"
    MpvFalso(ruta, error="property unavailable")
    assert RP.enviar_mpv("pausar", ruta) is False
    assert RP.enviar_mpv("pausar", tmp_path / "no_existe.sock") is False
    assert RP.enviar_mpv("bailar", ruta) is False


def test_lina_musica_desde_la_terminal(tmp_path, monkeypatch):
    ruta = tmp_path / "m.sock"
    MpvFalso(ruta)
    monkeypatch.setattr(RP, "ruta_mpv", lambda: ruta)
    salida = []
    assert RP.principal(["pausar"], salida.append) == 0
    assert RP.principal(["pausar"], salida.append) == 1 and "No hay música de Lina" in salida[-1]        # ya no hay nadie escuchando
    assert RP.principal([], salida.append) == 2 and RP.principal(["bailar"], salida.append) == 2


def test_playerctl_sin_reproductor_no_cuenta_como_hecho(monkeypatch):
    def falso(rc, salida):
        return lambda *a, **k: subprocess.CompletedProcess(a, rc, salida, "")
    monkeypatch.setattr(subprocess, "run", falso(0, ""))
    assert "No se ha hecho nada" in H._sin_reproductor() and H._sin_reproductor().startswith("código de salida: 1")
    monkeypatch.setattr(subprocess, "run", falso(1, ""))
    assert "No se ha hecho nada" in H._sin_reproductor()
    monkeypatch.setattr(subprocess, "run", falso(0, "spotify\nfirefox.instance123\n"))
    assert H._sin_reproductor() == ""                                   # hay reproductores: el comando sigue su camino
    def sin_playerctl(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", sin_playerctl)
    assert H._sin_reproductor() == ""                                   # sin playerctl lo dirá «command not found»


def test_el_comando_playerctl_se_detiene_ante_la_falta_de_reproductor(monkeypatch):
    monkeypatch.setattr(H, "_sin_reproductor", lambda: "código de salida: 1 (0 s)\n\nNo se ha hecho nada")
    ejecutados = []
    ej = H.Ejecutor()
    ej.ejecutar = lambda comando, motivo: ejecutados.append(comando) or "código de salida: 0 (0 s)"
    assert "No se ha hecho nada" in ej.herramienta({"comando": "playerctl pause", "motivo": "x"})
    assert ejecutados == []
    ej.herramienta({"comando": "playerctl status", "motivo": "x"})          # leer el estado no se frena
    assert ejecutados == ["playerctl status"]


def test_la_orden_lina_musica_es_inocua():
    assert H.clasificar("lina musica detener")[0] == "inocuo" and H.clasificar("lina musica pausar")[0] == "inocuo"


# ---- lina musica poner: solo dice que suena si suena
class _Proc:
    def __init__(self, vivo=True):
        self.vivo = vivo
    def poll(self):
        return None if self.vivo else 1
    def terminate(self):
        self.vivo = False


def _preparar(monkeypatch, tmp_path, mpv="/usr/bin/mpv", ytdlp="/usr/bin/yt-dlp", busqueda=None, proc=None, responde=True):
    monkeypatch.setattr(RP.shutil, "which", lambda n: {"mpv": mpv, "yt-dlp": ytdlp}.get(n))
    lanzados = []
    monkeypatch.setattr(RP.subprocess, "run", busqueda or (lambda *a, **k: subprocess.CompletedProcess(a, 0, "https://x/audio\n", "")))
    monkeypatch.setattr(RP.subprocess, "Popen", lambda cmd, **k: lanzados.append(cmd) or (proc or _Proc()))
    monkeypatch.setattr(RP, "enviar_mpv", lambda accion, ruta=None, espera=1: responde if accion == "vivo" else False)
    monkeypatch.setattr(RP.time, "sleep", lambda s: None)
    return lanzados, tmp_path / "mpv.sock"


def test_poner_suena(monkeypatch, tmp_path):
    lanzados, ruta = _preparar(monkeypatch, tmp_path)
    dicho = []
    assert RP.poner("Queen", ruta=ruta, salida=dicho.append) == 0
    assert dicho == ["Sonando: Queen."] and lanzados[0][0] == "/usr/bin/mpv" and f"--input-ipc-server={ruta}" in lanzados[0] and lanzados[0][-1] == "https://x/audio"


def test_poner_sin_mpv_o_sin_ytdlp(monkeypatch, tmp_path):
    for faltan in ({"mpv": None}, {"ytdlp": None}):
        _, ruta = _preparar(monkeypatch, tmp_path, **faltan)
        dicho = []
        assert RP.poner("Queen", ruta=ruta, salida=dicho.append) == 1 and "No está instalado" in dicho[0]


def test_poner_no_encuentra(monkeypatch, tmp_path):
    _, ruta = _preparar(monkeypatch, tmp_path, busqueda=lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "ERROR: no hay red\n"))
    dicho = []
    assert RP.poner("Queen", ruta=ruta, salida=dicho.append) == 1 and "no hay red" in dicho[0] and "No suena nada" in dicho[0]


def test_poner_mpv_muere_o_no_responde(monkeypatch, tmp_path):
    _, ruta = _preparar(monkeypatch, tmp_path, proc=_Proc(vivo=False))
    dicho = []
    assert RP.poner("Queen", ruta=ruta, salida=dicho.append) == 1 and "No suena nada" in dicho[0]
    _, ruta = _preparar(monkeypatch, tmp_path, responde=False)
    t = iter(range(0, 1000, 5))
    monkeypatch.setattr(RP.time, "time", lambda: next(t))
    dicho = []
    assert RP.poner("Queen", ruta=ruta, salida=dicho.append, arranque_seg=12) == 1 and "No suena nada" in dicho[0]


def test_poner_enlace_no_pasa_por_ytdlp(monkeypatch, tmp_path):
    lanzados, ruta = _preparar(monkeypatch, tmp_path, ytdlp=None)
    assert RP.poner("https://youtu.be/x", ruta=ruta, salida=lambda t: None) == 0 and lanzados[0][-1] == "https://youtu.be/x"


def test_poner_es_inocuo_y_persistente():
    assert H.clasificar('lina musica poner "Queen"')[0] in {"inocuo", "autonomo"}
    assert H._es_lanzamiento_persistente('lina musica poner "Queen"')


def test_receta_que_lanza_mpv_se_descarta(monkeypatch, tmp_path):
    from lina.nucleo import recetas as R
    archivo = tmp_path / "recetas.json"
    archivo.write_text(json.dumps([
        {"ajuste": "música de queen", "tipo": "pasos", "nucleo": ["queen"], "pasos": [{"herr": "ejecutar_comando", "args": {"comando": "setsid mpv --no-video x &"}}]},
        {"ajuste": "volumen", "tipo": "pasos", "nucleo": ["volumen"], "pasos": [{"herr": "ejecutar_comando", "args": {"comando": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 40%"}}]}]))
    monkeypatch.setattr(R, "ARCHIVO", archivo)
    assert [r["ajuste"] for r in R._cargar()] == ["volumen"]
