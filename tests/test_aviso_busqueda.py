# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Sin búsqueda la IA tiene necesito_datos_actuales y el código avisa una sola vez (lo hablado sin comandos; el comando, en la notificación).
Si Tavily llega a su límite (432 el plan, 433 el tope de gasto) se avisa como mucho una vez al mes; el 429 es de ritmo y no avisa. El «ya avisé»
se olvida al cambiar ia.busqueda y al guardar o borrar la clave de Tavily. Estado en tmp_path; ni red, ni llavero, ni notify-send de verdad."""
import json
import sys
import time
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import claves as CL
from lina.nucleo import ia as IA
from lina.nucleo import turnos as TU

OCTUBRE = time.mktime((2026, 10, 26, 12, 0, 0, 0, 0, -1))
NOVIEMBRE = time.mktime((2026, 11, 3, 12, 0, 0, 0, 0, -1))


class AjFalso:
    def __init__(self, busqueda):
        self.busqueda = busqueda

    def get(self, seccion, clave):
        return self.busqueda if (seccion, clave) == ("ia", "busqueda") else AJ.ESQUEMA[seccion][clave][0]


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(AVB.RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(IA, "_pausa_tavily", [0.0])                 # cada prueba empieza sin la pausa de un cupo agotado
    monkeypatch.setattr(IA, "hay_reserva", lambda: False)           # la búsqueda de reserva tiene sus propias pruebas (test_busqueda_reserva.py)
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    AVB.descartar()
    yield tmp_path
    AVB.descartar()


@pytest.fixture
def con(monkeypatch):
    def poner(busqueda, clave=None):
        monkeypatch.setattr(AJ, "actuales", lambda log=print: AjFalso(busqueda))
        monkeypatch.setattr(CL, "obtener", lambda nombre, *a: clave if nombre == "tavily" else None)
    return poner


# ---------------------------------------------------------------- la herramienta
@pytest.mark.parametrize("busqueda, clave, nombres", [
    ("tavily", None, ["necesito_datos_actuales"]),
    ("tavily", "tvly-x", ["buscar_web"]),
    ("ninguna", None, []),
    ("ninguna", "tvly-x", []),
    ("google", None, []),
])
def test_necesito_datos_actuales_solo_con_tavily_sin_clave(con, busqueda, clave, nombres):
    con(busqueda, clave)
    assert [d["name"] for d in IA.declaraciones_de_busqueda()] == nombres


def test_la_declaracion_es_minima():
    decl = IA.HERRAMIENTA_SIN_BUSQUEDA["functionDeclarations"]
    assert len(json.dumps(decl, ensure_ascii=False)) < 250
    assert decl[0]["parameters"] == {"type": "object", "properties": {}}


def test_cuenta_como_informar_y_no_como_meta():
    """Como meta, una petición que solo la llama dispararía el «reintento a fondo» por no haber hecho nada."""
    assert "necesito_datos_actuales" in TU.HERRAMIENTAS_DE_INFORMAR
    assert "necesito_datos_actuales" not in TU.HERRAMIENTAS_META


def _asistente(monkeypatch, busqueda="tavily"):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock()
    a.sustituida = a.interrumpiendo = False
    a.dicho = []
    a.decir = a.dicho.append
    notas = []
    monkeypatch.setattr(A.H, "notificar", lambda titulo, cuerpo="": notas.append((titulo, cuerpo)))
    monkeypatch.setattr(A.AJ, "actuales", lambda log=print: AjFalso(busqueda))
    return a, notas


def test_al_llamarla_la_ia_sabe_que_no_hay_busqueda_y_se_apunta_el_aviso(monkeypatch):
    a, _ = _asistente(monkeypatch)
    r = a._ejecutar_herramienta("necesito_datos_actuales", {})
    assert r == AVB.PARA_LA_IA_SIN_BUSQUEDA and "puede no estar al día" in r
    assert AVB.SIN_BUSQUEDA in AVB._pendientes
    a.ejecutor.contaminar.assert_not_called()


# ---------------------------------------------------------------- el aviso único
def test_se_avisa_una_sola_vez_corto_por_voz_y_el_comando_en_la_notificacion(monkeypatch):
    a, notas = _asistente(monkeypatch)
    a._ejecutar_herramienta("necesito_datos_actuales", {})
    a._dar_avisos_de_busqueda()
    assert len(a.dicho) == 1 and len(notas) == 1
    for tecnico in ("lina", "clave", "tavily", "ia.busqueda", "config"):
        assert tecnico not in a.dicho[0].lower()
    assert "lina clave tavily" in notas[0][1] and "ninguna" in notas[0][1]
    a._ejecutar_herramienta("necesito_datos_actuales", {})
    a._dar_avisos_de_busqueda()
    assert len(a.dicho) == 1 and len(notas) == 1


def test_sin_llamar_a_la_herramienta_no_hay_aviso(monkeypatch):
    a, notas = _asistente(monkeypatch)
    a._dar_avisos_de_busqueda()
    assert a.dicho == [] and notas == []


def test_con_ninguna_nunca_se_avisa(monkeypatch):
    a, notas = _asistente(monkeypatch, "ninguna")
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    a._dar_avisos_de_busqueda()
    assert a.dicho == [] and notas == []


def test_si_estas_hablando_no_se_habla_pero_se_notifica(monkeypatch):
    a, notas = _asistente(monkeypatch)
    a.interrumpiendo = True
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    a._dar_avisos_de_busqueda()
    assert a.dicho == [] and len(notas) == 1


def test_lo_apuntado_en_una_peticion_sin_responder_no_pasa_a_la_siguiente():
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    AVB.descartar()
    assert AVB.pendientes("tavily") == []


# ---------------------------------------------------------------- cuándo se olvida el «ya avisé»
def test_cambiar_ia_busqueda_vuelve_a_permitir_el_aviso():
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    assert len(AVB.pendientes("tavily")) == 1
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    assert AVB.pendientes("tavily") == []
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    assert len(AVB.pendientes("google")) == 1           # otro modo: lo de antes ya no vale


@pytest.fixture
def claves_en_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(CL, "_quiere_llavero", lambda: False)
    monkeypatch.setattr(CL, "archivo_guardar", lambda n, v: tmp_path / f"{n}.key")
    monkeypatch.setattr(CL, "archivo_borrar", lambda n: True)
    monkeypatch.setattr(CL, "llavero_borrar", MagicMock(side_effect=AssertionError("no debía tocar el llavero")))


@pytest.mark.parametrize("accion", ["guardar", "borrar"])
def test_guardar_o_borrar_la_clave_de_tavily_olvida_los_avisos(claves_en_tmp, estado, accion):
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    AVB.apuntar(AVB.LIMITE_PLAN)
    assert len(AVB.pendientes("tavily", OCTUBRE)) == 2
    CL.guardar("tavily", "tvly-nueva-0123456789") if accion == "guardar" else CL.borrar("tavily")
    assert not (estado / AVB.ARCHIVO).exists()
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    AVB.apuntar(AVB.LIMITE_PLAN)
    assert len(AVB.pendientes("tavily", OCTUBRE)) == 2


def test_guardar_otra_clave_no_olvida_los_avisos(claves_en_tmp, estado):
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    AVB.pendientes("tavily")
    CL.guardar("gemini", "AIza-otra-0123456789")
    assert (estado / AVB.ARCHIVO).exists()
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    assert AVB.pendientes("tavily") == []


# ---------------------------------------------------------------- el límite de Tavily (432 y 433)
def _tavily_responde(con, monkeypatch, codigo):
    con("tavily", "tvly-de-prueba")
    IA._pausa_tavily[0] = 0.0                                       # aquí se mide el aviso (una vez al mes), no la pausa tras un 432
    monkeypatch.setattr(requests, "post", MagicMock(return_value=MagicMock(ok=False, status_code=codigo, text="limit")))
    return IA.resultados_tavily("partido de hoy")


def test_432_el_plan_llego_a_su_limite(con, monkeypatch):
    r = _tavily_responde(con, monkeypatch, 432)
    assert r == AVB.PARA_LA_IA_LIMITE
    [(hablado, titulo, texto)] = AVB.pendientes("tavily", OCTUBRE)
    assert texto == "Tu plan de Tavily ha llegado a su límite de uso; se renueva cada ciclo o puedes ampliarlo en app.tavily.com"
    assert "tavily" not in hablado.lower() and "gratuit" not in texto


def test_433_el_tope_de_gasto_que_pusiste(con, monkeypatch):
    r = _tavily_responde(con, monkeypatch, 433)
    assert r == AVB.PARA_LA_IA_LIMITE
    [(hablado, titulo, texto)] = AVB.pendientes("tavily", OCTUBRE)
    assert texto == "Has llegado al límite de gasto que pusiste en Tavily; puedes subirlo en el panel (app.tavily.com)"
    assert hablado == AVB.HABLADO[AVB.LIMITE_PLAN] and "gratuit" not in texto


@pytest.mark.parametrize("codigo", [429, 500])
def test_otros_errores_no_avisan_del_limite(con, monkeypatch, codigo):
    r = _tavily_responde(con, monkeypatch, codigo)
    assert r == "La búsqueda web no está disponible ahora mismo."
    assert AVB.pendientes("tavily", OCTUBRE) == []


def test_el_limite_se_avisa_como_mucho_una_vez_al_mes(con, monkeypatch):
    _tavily_responde(con, monkeypatch, 432)
    assert len(AVB.pendientes("tavily", OCTUBRE)) == 1
    _tavily_responde(con, monkeypatch, 432)
    assert AVB.pendientes("tavily", OCTUBRE) == []
    _tavily_responde(con, monkeypatch, 433)                  # el otro motivo es otro aviso
    assert len(AVB.pendientes("tavily", OCTUBRE)) == 1
    _tavily_responde(con, monkeypatch, 432)
    assert len(AVB.pendientes("tavily", NOVIEMBRE)) == 1


def test_un_estado_roto_no_rompe_nada(estado):
    (estado / AVB.ARCHIVO).write_text("{roto", encoding="utf-8")
    AVB.apuntar(AVB.SIN_BUSQUEDA)
    assert len(AVB.pendientes("tavily")) == 1


def test_con_reserva_el_cupo_agotado_se_notifica_pero_no_se_dice(monkeypatch):
    a, notas = _asistente(monkeypatch)
    from lina.nucleo import asistente as A
    monkeypatch.setattr(A, "hay_reserva", lambda: True)
    AVB.apuntar(AVB.LIMITE_PLAN)
    a._dar_avisos_de_busqueda()
    assert a.dicho == [] and len(notas) == 1 and "DuckDuckGo" in notas[0][1]
