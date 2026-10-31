# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Punto 2: al preguntar qué pasó, o «…, ¿no?», la IA recibe lo que consta (escrito por el código), no solo su propia respuesta anterior. Con la conversación real de
«Ábreme Steam», donde se inventó que Steam tardaba en aparecer y contestó «Exacto». Sin red ni IA: esto prueba lo que se le da, no lo que acaba diciendo."""
import inspect
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import herramientas as H
from lina.nucleo import turnos as TU

VARIOS = "Hay varios programas que encajan con «Steam»: «Steam» (id steam). Elige el que corresponde."
PRIMERA = [("abrir_app", {"nombre": "Steam"}, VARIOS)] * 10
SEGUNDA = [("abrir_app", {"nombre": "steam"}, "Abierto «Steam». Ya está: no hace falta comprobar nada más.")]


def _lectura(c):
    return H.clasificar(c)[0] == "lectura"


@pytest.fixture
def a():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    x = A.Asistente.__new__(A.Asistente)
    x.hechos_recientes = []
    return x


@pytest.mark.parametrize("frase", ["Ahora sí que lo habías abierto. ¿Qué había pasado antes? ¿Por qué había fallado?",
                                   "O sea que la primera vez sí que funcionó, solo que yo no lo había visto porque estaba tardando en ejecutarse, ¿no?",
                                   "¿Lo has abierto?", "Funcionó, ¿verdad?", "¿Por qué no ha sonado?"])
def test_detecta_las_preguntas_por_lo_que_paso(frase):
    assert TU.pregunta_por_lo_anterior(frase)


@pytest.mark.parametrize("frase", ["Ábreme Steam", "¿Qué hora es?", "¿Por qué el cielo es azul?", "Cuéntame un dato curioso", "¿Cómo se hace una tortilla?"])
def test_lo_demas_no(frase):
    assert not TU.pregunta_por_lo_anterior(frase)


def test_los_hechos_del_caso_real():
    h = TU.hechos_de_peticion(PRIMERA, _lectura, "Ábreme Steam.")
    assert h[0].startswith("abrir_app Steam → Hay varios programas") and h[0].endswith("(×10)") and h[1:] == ["no consta que se hiciera lo pedido"]


def test_lo_que_se_hizo_consta_como_hecho():
    h = TU.hechos_de_peticion(SEGUNDA, _lectura, "No, no lo has abierto.")
    assert h[0].startswith("abrir_app steam → Abierto «Steam»") and len(h) == 1
    assert "código 1: No such key" in TU.hechos_de_peticion([("ejecutar_comando", {"comando": "x"}, "código de salida: 1 (0 s)\n\nNo such key.")], _lectura)[0]


def test_sin_herramientas_lo_dice():
    assert TU.hechos_de_peticion([], _lectura, "Cuéntame algo") == ["no se usó ninguna herramienta"]


def test_la_nota_avisa_de_que_su_respuesta_no_es_prueba_y_de_no_dar_la_razon():
    n = TU.nota_de_hechos([{"hora": "17:00:21", "pedido": "Ábreme Steam.", "hechos": TU.hechos_de_peticion(PRIMERA, _lectura, "Ábreme Steam."), "dijo": "Abierto."}])
    for texto in ("17:00:21", "no consta que se hiciera lo pedido", "Respondiste: «Abierto.»", "NO es prueba", "di que no lo sabes", "no le des la razón"):
        assert texto in n
    assert TU.nota_de_hechos([]) == ""


def test_la_conversacion_real(a):
    a.acciones_turno = PRIMERA
    a._apuntar_hechos("Ábreme Steam.", "Abierto.")
    a.acciones_turno = SEGUNDA
    a._apuntar_hechos("No, no lo has abierto.", "Abierto.")
    a.pregunta_pura = "O sea que la primera vez sí que funcionó, solo que yo no lo había visto porque estaba tardando en ejecutarse, ¿no?"
    h = a._hechos_al_caso()
    assert [r["pedido"] for r in h] == ["Ábreme Steam.", "No, no lo has abierto."] and "no consta que se hiciera lo pedido" in h[0]["hechos"]
    assert "Abierto «Steam»" in h[1]["hechos"][0]


def test_una_pregunta_normal_no_lleva_hechos_y_caducan(a):
    a.acciones_turno = PRIMERA
    a._apuntar_hechos("Ábreme Steam.", "Abierto.")
    a.pregunta_pura = "¿Qué hora es?"
    assert a._hechos_al_caso() == []
    a.pregunta_pura = "¿Qué ha pasado?"
    assert a._hechos_al_caso()
    a.hechos_recientes[0]["t"] = time.time() - 1000
    assert a._hechos_al_caso() == []


def test_solo_las_ultimas_y_no_se_comparten_entre_asistentes(a):
    a.acciones_turno = []
    for i in range(7):
        a._apuntar_hechos(f"p{i}", "r")
    assert [r["pedido"] for r in a.hechos_recientes] == ["p3", "p4", "p5", "p6"]
    from lina.nucleo import asistente as A
    assert A.Asistente.hechos_recientes == []


def test_se_elige_el_modelo_a_fondo_y_la_nota_no_entra_en_el_historial():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    f = inspect.getsource(A.Asistente._atender)
    assert '"profundo", "preguntas por lo que ha pasado"' in f
    assert f.index("pregunta_sin_receta = pregunta") < f.index("nota_de_hechos(hechos)")


# ---------------------------------------------------------------- correcciones tras el primer uso real
@pytest.mark.parametrize("frase", ["Entonces si yo te pido alguna receta, tú miras en esa fuente y me dices cuál es.", "Entonces no quiero nada más."])
def test_entonces_al_hablar_de_otra_cosa_no_es_preguntar_por_lo_anterior(frase):
    assert not TU.pregunta_por_lo_anterior(frase)


@pytest.mark.parametrize("frase", ["Entonces sí funcionó", "Entonces no ha servido de nada", "Entonces es que no lo abriste"])
def test_entonces_sobre_lo_que_paso_si(frase):
    assert TU.pregunta_por_lo_anterior(frase)


def test_el_modo_privado_no_apunta_hechos_ni_los_da_y_borra_los_que_habia(a, tmp_path, monkeypatch):
    from lina.nucleo import asistente as A
    monkeypatch.setattr(A, "ARCHIVO_PRIVADO", tmp_path / "privado")
    a.acciones_turno = PRIMERA
    a._apuntar_hechos("Ábreme Steam.", "Abierto.")
    a.pregunta_pura = "¿Qué ha pasado?"
    assert a._hechos_al_caso()
    a._poner_modo_privado(True)
    assert a.hechos_recientes == [] and a._hechos_al_caso() == []
    a._apuntar_hechos("Ábreme Steam.", "Abierto.")
    assert a.hechos_recientes == []
    a._poner_modo_privado(False)
    a._apuntar_hechos("Ábreme Steam.", "Abierto.")
    assert len(a.hechos_recientes) == 1
