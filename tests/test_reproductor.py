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


# ---- lina musica poner: yt-dlp descarga y se lo pasa a mpv; solo dice que suena si el audio avanza
class _Proc:
    """Un proceso falso: vive hasta que se le pide parar (o `muere_tras` comprobaciones)."""
    def __init__(self, pid=4242, muere_tras=None):
        self.pid, self.muere_tras, self.vueltas, self.parado = pid, muere_tras, 0, False
        self.stdout = type("S", (), {"close": lambda self: None})()

    def poll(self):
        self.vueltas += 1
        if self.parado or (self.muere_tras is not None and self.vueltas > self.muere_tras):
            return 1
        return None

    def terminate(self):
        self.parado = True


class _Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def _preparar(monkeypatch, tmp_path, mpv="/usr/bin/mpv", ytdlp="/usr/bin/yt-dlp", tiempos=(None, 0.1, 0.8), mpv_proc=None, yt_proc=None, error_yt=""):
    monkeypatch.setattr(RP.shutil, "which", lambda n: {"mpv": mpv, "yt-dlp": ytdlp}.get(n))
    lanzados, procesos = [], {"yt": yt_proc or _Proc(pid=111), "mpv": mpv_proc or _Proc(pid=222)}

    def popen(cmd, **k):
        lanzados.append((cmd, k))
        if cmd[0] == ytdlp:
            k["stderr"].write(error_yt)
            k["stderr"].flush()
            return procesos["yt"]
        return procesos["mpv"]
    monkeypatch.setattr(RP.subprocess, "Popen", popen)
    valores = iter(tiempos)
    monkeypatch.setattr(RP, "propiedad_mpv", lambda nombre, ruta=None, espera=1.0: next(valores, tiempos[-1]))
    monkeypatch.setattr(RP, "enviar_mpv", lambda accion, ruta=None, espera=1: False)
    reloj = _Reloj()
    return lanzados, procesos, tmp_path / "mpv.sock", reloj


def _poner(consulta, ruta, reloj, dicho, **k):
    return RP.poner(consulta, ruta=ruta, salida=dicho.append, reloj=reloj, dormir=reloj.dormir, **k)


def test_poner_suena_solo_cuando_el_audio_avanza(monkeypatch, tmp_path):
    lanzados, procesos, ruta, reloj = _preparar(monkeypatch, tmp_path, tiempos=(None, 0.0, 0.2, 0.7))
    dicho = []
    assert _poner("Queen", ruta, reloj, dicho) == 0 and dicho == ["Sonando: Queen."]
    yt, mpv = lanzados[0], lanzados[1]
    assert yt[0][0] == "/usr/bin/yt-dlp" and yt[0][-1] == "ytsearch1:Queen" and yt[0][yt[0].index("-o") + 1] == "-" and yt[1]["stdout"] is RP.subprocess.PIPE
    assert mpv[0][0] == "/usr/bin/mpv" and mpv[0][-1] == "-" and f"--input-ipc-server={ruta}" in mpv[0] and mpv[1]["stdin"] is procesos["yt"].stdout
    assert "--really-quiet" not in mpv[0]                                                  # sus errores tienen que quedar en el registro
    assert (tmp_path / "yt-dlp.pid").read_text() == "111"


def test_mpv_vivo_que_no_avanza_no_es_sonando(monkeypatch, tmp_path):
    """El fallo del registro: mpv vivo y contestando mientras intenta abrir el enlace, y luego 403. Ya no basta con que esté vivo."""
    lanzados, procesos, ruta, reloj = _preparar(monkeypatch, tmp_path, tiempos=(None,))
    dicho = []
    assert _poner("Queen", ruta, reloj, dicho, arranque_seg=5) == 1
    assert dicho[0].startswith("No ha empezado a sonar a tiempo") and "No suena nada" in dicho[0]
    assert procesos["mpv"].parado and procesos["yt"].parado                               # no se quedan procesos colgados


def test_si_mpv_se_cierra_dice_el_motivo_de_yt_dlp(monkeypatch, tmp_path):
    lanzados, procesos, ruta, reloj = _preparar(monkeypatch, tmp_path, tiempos=(None,), mpv_proc=_Proc(muere_tras=3),
                                                error_yt="ERROR: [youtube] h5Cp: HTTP Error 403: Forbidden\n")
    dicho = []
    assert _poner("Queen", ruta, reloj, dicho) == 1
    assert "No ha llegado a sonar" in dicho[0] and "403" in dicho[0] and "Sonando" not in dicho[0]


def test_un_enlace_va_por_el_mismo_camino(monkeypatch, tmp_path):
    lanzados, _, ruta, reloj = _preparar(monkeypatch, tmp_path)
    assert _poner("https://www.youtube.com/watch?v=h5Cp_04sKDM", ruta, reloj, []) == 0
    assert lanzados[0][0][-1] == "https://www.youtube.com/watch?v=h5Cp_04sKDM" and lanzados[1][0][-1] == "-"


def test_poner_sin_mpv_o_sin_ytdlp(monkeypatch, tmp_path):
    for faltan in ({"mpv": None}, {"ytdlp": None}):
        lanzados, _, ruta, reloj = _preparar(monkeypatch, tmp_path, **faltan)
        dicho = []
        assert _poner("Queen", ruta, reloj, dicho) == 1 and "No está instalado" in dicho[0] and lanzados == []
    dicho = []
    assert RP.poner("   ", salida=dicho.append) == 2


def test_detener_cierra_tambien_la_descarga(monkeypatch, tmp_path):
    ruta = tmp_path / "mpv.sock"
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)                       # hace de yt-dlp
    (tmp_path / "yt-dlp.pid").write_text(str(proc.pid))
    real_open = open

    def abrir(archivo, *a, **k):                                                           # su /proc/PID/cmdline dice yt-dlp
        if str(archivo) == f"/proc/{proc.pid}/cmdline":
            import io
            return io.BytesIO(b"/usr/bin/yt-dlp\x00-o\x00-\x00")
        return real_open(archivo, *a, **k)
    monkeypatch.setattr("builtins.open", abrir)
    try:
        RP.enviar_mpv("detener", ruta)
        assert proc.wait(timeout=5) is not None and not (tmp_path / "yt-dlp.pid").exists()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_detener_no_mata_un_proceso_que_no_es_yt_dlp(tmp_path):
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)                       # el número se reutilizó: ya no es yt-dlp
    (tmp_path / "yt-dlp.pid").write_text(str(proc.pid))
    try:
        assert RP.cerrar_descarga(tmp_path / "mpv.sock") is False and proc.poll() is None
    finally:
        proc.kill()


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
