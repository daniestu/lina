# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El origen (atajo o «Oye Lina») va con cada petición, no con quien hable el último: pulsar el atajo para interrumpir una tarea de manos libres no le da
sus permisos, lo apuntado con «además…» conserva el suyo, y si un camino llega sin origen se trata como manos libres (lo restrictivo)."""
import shutil
import sys
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from lina.nucleo import comandos as C
from lina.nucleo import memoria as M
from lina.nucleo import rutas as RUT

A = None


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """memoria, modo privado y comandos.txt en una carpeta temporal; micrófono, pitidos y gasto simulados."""
    global A
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    A = asistente
    comandos = tmp_path / "comandos.txt"
    shutil.copyfile(RUT.DEFECTOS / "comandos.txt", comandos)
    monkeypatch.setattr(C, "archivo", lambda: comandos)
    monkeypatch.setitem(C._cache, "datos", None)
    monkeypatch.setitem(C._cache, "marca", "sin leer")
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "memoria.json")
    monkeypatch.setattr(A, "ARCHIVO_PRIVADO", tmp_path / "modo_privado")
    monkeypatch.setattr(A, "pitido", lambda f: None)
    monkeypatch.setattr(A.sd, "InputStream", MagicMock())
    monkeypatch.setattr(A.PRES, "avisos_pendientes", lambda: [])
    return tmp_path


def _asistente():
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado, a.origen_voz_libre, a.sustituida, a.interrumpiendo = False, False, False, False
    a.estado, a.cerrojo, a.fin_tarea = "esperando", threading.Lock(), threading.Event()
    a.fin_tarea.set()
    a.dicho = []
    a.decir = a.dicho.append
    a._hablar = a.dicho.append
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    a._preparar_contexto = lambda: None
    a._bajar_sonido = a._subir_sonido = lambda *x: None
    return a


def _textos():
    return [r["texto"] for r in M._cargar()]


def test_sin_origen_se_trata_como_manos_libres():
    assert A._origen_valido(None) == A._origen_valido("") == A._origen_valido("cualquier cosa") == "voz_libre"
    assert A._origen_valido("atajo") == "atajo"
    a = _asistente()
    a.modo_privado = True
    a.origen_voz_libre = False                                   # aunque lo último fuese el atajo, una petición sin origen no lo hereda
    a._atender("Quita el modo privado", 0.0)
    assert a.modo_privado and a.origen_voz_libre and "atajo" in a.dicho[-1]


def test_cada_peticion_guarda_su_origen_en_el_ejecutor_para_retomarla():
    a = _asistente()
    a._atender("activa el modo privado", 0.0, origen="atajo")
    assert a.ejecutor.origen == "atajo" and not a.origen_voz_libre
    a._atender("¿Estás en modo privado?", 0.0, origen="voz_libre")
    assert a.ejecutor.origen == "voz_libre" and a.origen_voz_libre


def test_el_atajo_da_origen_atajo():
    a = _asistente()
    pedidas = []
    a._transcribir = lambda audio, inicio, crono=None: "hola"
    a._atender = lambda *args, **k: pedidas.append(k.get("origen"))
    a._voz_a_respuesta(np.ones(A.FRECUENCIA, np.float32))
    assert pedidas == ["atajo"]


def test_interrumpir_con_el_atajo_no_da_permisos_a_una_tarea_de_manos_libres():
    a = _asistente()
    a.modo_privado = True
    a._atender("¿Estás en modo privado?", 0.0, origen="voz_libre")     # la tarea en curso vino de «Oye Lina»
    a.estado = "pensando"
    a._empezar_interrupcion()                                   # pulsas el atajo mientras piensa…
    assert a.origen_voz_libre and a.ejecutor.origen == "voz_libre"
    assert "atajo" in a._gestionar_modo_privado("quitar") and a.modo_privado   # …y esa tarea sigue sin poder quitar el modo privado


def test_una_peticion_nueva_con_el_atajo_si_es_del_atajo():
    a = _asistente()
    a.origen_voz_libre = True
    a.empezar_grabacion = A.Asistente.empezar_grabacion.__get__(a)
    a.empezar_grabacion()
    assert not a.origen_voz_libre


def _apuntar_y_terminar(a, texto, origen):
    """Lo dicho mientras trabaja se apunta para después con su origen; luego la tarea en curso termina y se atiende lo apuntado."""
    a.decidir_interrupcion = lambda t: ("ademas", "prueba")
    a.fin_tarea.clear()
    a._interrupcion_con_texto(texto, 0.0, origen=origen)
    assert a._cola() == [(texto, origen)]
    a.origen_voz_libre = False                                   # entre medias pulsas el atajo (como hacía antes _iniciar_grabacion)
    a._tarea(lambda: None)
    for _ in range(50):
        if a.fin_tarea.wait(0.05) and a.estado == "esperando":
            break


def test_ademas_por_manos_libres_conserva_su_origen_aunque_pulses_el_atajo():
    a = _asistente()
    _apuntar_y_terminar(a, "recuerda que mi navegador favorito es Brave", "voz_libre")
    assert _textos() == [] and "atajo" in a.dicho[-1]


def test_ademas_con_el_atajo_si_se_apunta():
    a = _asistente()
    _apuntar_y_terminar(a, "recuerda que mi navegador favorito es Brave", "atajo")
    assert _textos() == ["mi navegador favorito es Brave"]
