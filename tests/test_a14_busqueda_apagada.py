# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A14: con ia.busqueda = ninguna, tu pregunta no sale a ningún buscador si no lo pides tú.

Caso real (2026-11-16): «¿Contra quién juega mi equipo?» buscó igualmente, porque la IA pasó la propia pregunta como «autorización» y el código
solo comprobaba que esas palabras eran tuyas. Ahora la IA no puede autorizarse: si pides buscar lo juzga una mini-consulta aparte que solo ve tus palabras
y, si no, la búsqueda queda pendiente de tu «sí». Aquí la mini-consulta va simulada: se prueba que el código hace lo que ella decide, que solo recibe tus
palabras y que sin su «sí» no se busca nunca. Su juicio con el modelo de verdad se mide aparte (fila A14 del plan). Sin red ni IA.
"""
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import busqueda as BUS
from lina.nucleo import herramientas as H
from lina.nucleo import ia as IA

PREGUNTAS = ["¿Contra quién juega mi equipo?", "¿Qué tiempo va a hacer mañana?", "¿Cuánto cuesta la entrada del cine?"]
INSISTE = ["Aun así, quiero saberlo.", "Insisto que quiero que hagas lo que sea para que lo busques.", "Que lo busque este digno."]
RESULTADO = BUS.Resultado(resultados=[{"title": "T", "url": "https://a.example.com", "dominio": "a.example.com", "content": "x"}], escalon="google")


@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    monkeypatch.setattr(H, "notificar", MagicMock(side_effect=AssertionError("esta acción no avisa en el escritorio")))
    monkeypatch.setattr(H, "anotar", lambda linea: None)
    monkeypatch.setattr(A, "modo_busqueda", lambda: "ninguna")
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = H.Ejecutor(confirmar=True)
    a.busquedas_turno, a.max_busquedas, a.busquedas_hechas, a.forzar_busqueda = 0, 2, [], False
    a.acciones_turno, a.historial, a.busqueda_apagada_turno = [], [], False
    a.origen_voz_libre = a.origen_texto = False
    a.pregunta_pura, a.clave = "", "k"
    a._claves = lambda modo: ["k"]
    a.A = A
    a.juez = MagicMock(return_value={"pide": False, "modelo": "m"})
    monkeypatch.setattr(A, "pide_buscar_ia", a.juez)
    a.buscar = MagicMock(return_value=RESULTADO)
    monkeypatch.setattr(BUS, "buscar", a.buscar)
    return a


def _pregunta(lina, frase, **args):
    lina.pregunta_pura = frase
    lina._juicio_buscar = None
    return lina._h_buscar_web("buscar_web", {"consulta": "consulta que escribe la IA", **args})


# ---------------------------------------------------------------- negativos: una pregunta normal no busca; se ofrece
@pytest.mark.parametrize("frase", PREGUNTAS)
def test_una_pregunta_normal_no_busca_y_queda_ofrecida(lina, frase):
    r = _pregunta(lina, frase)
    lina.buscar.assert_not_called()
    assert r.startswith("PREPARADO, NO EJECUTADO") and "apagada" in r and "No des el dato de memoria" in r
    assert [p["comando"] for p in lina.ejecutor.pendientes] == [lina.A.DESCRIPCION_BUSCAR_UNA_VEZ]
    assert lina.busqueda_apagada_turno is True


@pytest.mark.parametrize("frase", PREGUNTAS)
def test_la_ia_no_puede_autorizarse_ni_pasando_tu_pregunta(lina, frase):
    """El fallo real: la IA pasaba la pregunta como autorización. Ya no hay argumento suyo que cuente."""
    for extra in ({"autorizacion": frase}, {"autorizacion": "búscalo igualmente"}, {"forzar": True}):
        lina.ejecutor.pendientes = []
        _pregunta(lina, frase, **extra)
    lina.buscar.assert_not_called()
    assert "autorizacion" not in IA.HERRAMIENTA_BUSCAR_APAGADA["functionDeclarations"][0]["parameters"]["properties"]


def test_si_la_mini_consulta_no_responde_no_se_busca(lina):
    lina.juez.return_value = None
    assert _pregunta(lina, PREGUNTAS[0]).startswith("PREPARADO")
    lina.buscar.assert_not_called()


def test_el_juez_solo_ve_tus_palabras_y_un_hecho_del_codigo(lina):
    lina.historial = [{"rol": "user", "texto": "¿Quién ganó ayer?\n[SISTEMA: nota interna]"}, {"rol": "model", "texto": "TEXTO DE LA IA: búscalo ya"}]
    _pregunta(lina, PREGUNTAS[0])
    (clave, frase, anterior, avisado), _ = lina.juez.call_args
    assert (frase, anterior, avisado) == (PREGUNTAS[0], "¿Quién ganó ayer?", False)          # ni la consulta de la IA, ni su texto, ni las notas


def test_se_juzga_una_vez_por_peticion_y_solo_queda_una_busqueda_pendiente(lina):
    lina.pregunta_pura, lina._juicio_buscar = PREGUNTAS[0], None
    lina._h_buscar_web("buscar_web", {"consulta": "una"})
    r = lina._h_buscar_web("buscar_web", {"consulta": "otra"})
    assert lina.juez.call_count == 1 and len(lina.ejecutor.pendientes) == 1 and "Ya hay una búsqueda preparada" in r


def test_la_descripcion_pendiente_la_escribe_el_codigo_sin_la_consulta_de_la_ia(lina):
    _pregunta(lina, PREGUNTAS[0])
    descripcion = H.describir_pendientes(lina.ejecutor.pendientes)
    assert "consulta que escribe la IA" not in descripcion and "Buscar en internet, solo esta vez" in descripcion


# ---------------------------------------------------------------- positivos: lo pides tú
@pytest.mark.parametrize("frase", INSISTE + ["Mira en internet contra quién juega mi equipo, aunque la tengas apagada."])
def test_si_lo_pides_con_tus_palabras_se_busca_sin_confirmar_otra_vez(lina, frase):
    """Lo que la mini-consulta entiende como pedir buscar (en tu primera frase o al insistir) busca solo esta vez, sin dejar nada pendiente."""
    lina.juez.return_value = {"pide": True, "modelo": "m"}
    r = _pregunta(lina, frase)
    assert r.startswith("RESULTADOS DE BÚSQUEDA") and lina.buscar.call_args.kwargs["modo"] == "auto"
    assert lina.ejecutor.pendientes == [] and lina.busqueda_apagada_turno is False


def test_al_insistir_el_juez_sabe_que_se_te_acaba_de_avisar(lina):
    _pregunta(lina, PREGUNTAS[0])                          # se ofrece: queda apuntado el aviso
    lina.ejecutor.pendientes = []
    lina.historial = [{"rol": "user", "texto": PREGUNTAS[0]}]
    _pregunta(lina, INSISTE[0])
    assert lina.juez.call_args.args[1:] == (INSISTE[0], PREGUNTAS[0], True)
    lina._t_busqueda_ofrecida = time.time() - lina.A.OFERTA_DE_BUSCAR_SEG - 1
    _pregunta(lina, INSISTE[0])
    assert lina.juez.call_args.args[3] is False            # pasado un rato, ya no


def test_busca_igualmente_va_a_la_primera_por_el_atajo(lina):
    """El atajo por palabras solo acelera: esta petición busca como «auto» sin preguntar a nadie."""
    assert lina._buscar_igualmente("Busca igualmente contra quién jugamos") is True
    lina.forzar_busqueda = True
    assert _pregunta(lina, "Busca igualmente contra quién jugamos").startswith("RESULTADOS DE BÚSQUEDA")
    lina.juez.assert_not_called()


@pytest.mark.parametrize("frase", INSISTE + ["Sí."])
def test_tu_si_a_la_oferta_busca_y_consta_como_busqueda(lina, monkeypatch, frase):
    """Tras la oferta, tu respuesta la entiende la mini-consulta de las confirmaciones (simulada): la búsqueda se hace y consta como buscar_web."""
    _pregunta(lina, PREGUNTAS[0])
    confirmador = MagicMock(return_value={"decision": "confirma", "menciona_cantidad": False, "modelo": "m"})
    monkeypatch.setattr(lina.A, "clasificar_confirmacion_ia", confirmador)
    nota, confirmado = lina.resolver_pendientes(frase)
    assert confirmado and "RESULTADOS DE BÚSQUEDA" in nota
    assert lina.buscar.call_args.args[0] == "consulta que escribe la IA" and lina.buscar.call_args.kwargs["modo"] == "auto"
    assert lina.acciones_confirmadas[0][:2] == ("buscar_web", {"consulta": "consulta que escribe la IA"})
    assert lina.busquedas_confirmadas == [RESULTADO]
    if confirmador.called:                                 # «Sí.» lo decide el código; lo demás, la mini-consulta, que ve solo esto
        assert confirmador.call_args.args[1] == frase and "consulta que escribe la IA" not in confirmador.call_args.args[2]


def test_si_dices_que_no_no_se_busca(lina, monkeypatch):
    _pregunta(lina, PREGUNTAS[0])
    nota, confirmado = lina.resolver_pendientes("No.")
    assert not confirmado and lina.ejecutor.pendientes == []
    lina.buscar.assert_not_called()


@pytest.mark.parametrize("origen", ["origen_voz_libre", "origen_texto"])
def test_por_manos_libres_o_lina_di_el_si_no_busca(lina, origen):
    _pregunta(lina, PREGUNTAS[0])
    setattr(lina, origen, True)
    nota, confirmado = lina.resolver_pendientes("Sí.")
    assert not confirmado and "atajo" in nota
    lina.buscar.assert_not_called()


# ---------------------------------------------------------------- la mini-consulta: lo que se le envía
def test_la_mini_consulta_recibe_solo_la_frase_la_anterior_y_el_aviso(monkeypatch):
    enviado = {}

    def mini(clave, prompt, esquema, contenido, etiqueta, validar, **k):
        enviado.update(prompt=prompt, contenido=contenido)
        validar({"pide_buscar": True})
        return {"pide_buscar": True}, "m"
    monkeypatch.setattr(IA, "_mini_consulta_json", mini)
    assert IA.pide_buscar_ia("k", "Aun así, quiero saberlo.", "¿Contra quién juega?", True) == {"pide": True, "modelo": "m"}
    assert enviado["contenido"] == ("<aviso_previo>sí</aviso_previo>\n<frase_anterior>\n¿Contra quién juega?\n</frase_anterior>\n"
                                    "<frase>\nAun así, quiero saberlo.\n</frase>")
    assert "preguntar algo NO es pedir que se busque" in enviado["prompt"] and "Ante la duda, false" in enviado["prompt"]


def test_una_respuesta_que_no_es_si_o_no_no_vale(monkeypatch):
    def mini(clave, prompt, esquema, contenido, etiqueta, validar, **k):
        with pytest.raises(ValueError):
            validar({"pide_buscar": "sí"})
        return None
    monkeypatch.setattr(IA, "_mini_consulta_json", mini)
    assert IA.pide_buscar_ia("k", "x") is None
