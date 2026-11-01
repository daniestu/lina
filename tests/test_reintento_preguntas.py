# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S12: lo del caso 7 de la prueba en vivo. Un «no he podido» en una pregunta lanzó un reintento a fondo con comandos sobre la carpeta personal. Ahora insistir en una pregunta solo
admite la web, con el modelo rápido y hasta 60 s; las órdenes insisten como siempre. Sin red ni IA: `_gemini` simulado."""
import sys
from unittest.mock import MagicMock

import pytest

PREGUNTA = "¿qué dice la página de pruebas?"
ORDEN = "abre Steam"
WEB = {"name": "buscar_web"}
LEER = {"name": "leer_web"}
HERRAMIENTAS = [WEB, LEER, {"name": "ejecutar_comando"}, {"name": "mas_herramientas"}, {"name": "pensar_a_fondo"}]
LECTURA = ("ejecutar_comando", {"comando": "ls ~/Documentos"}, "código de salida: 0")
CAMBIO = ("ejecutar_comando", {"comando": "kwriteconfig6 --key a b"}, "código de salida: 0")


@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], duda=None, efecto_sin_comprobar=False, recetas_diferidas=[], profundo=False)
    a.acciones_turno, a.pedir_profundo, a.obstaculo, a.insistiendo = [], "", "", False
    a.fuente_cerrada, a.reintento_solo_web, a.clave, a.historial = False, False, "clave", []
    a.guion_herramientas, a.paso_guion = [], 0
    a.pantalla_adjunta = False
    a.tope_de_tarea = MagicMock(return_value=None)
    a._cerrar_receta_interfaz = MagicMock()
    a._avisar_voz = MagicMock()
    a._gemini = MagicMock(return_value="Respuesta del reintento.")
    a.revisar_respuesta = MagicMock()
    monkeypatch.setattr(A.IAC, "modelos", lambda grupo: [grupo])
    monkeypatch.setattr(A, "verificar_cumplimiento", lambda *x, **k: False)
    a.A = A
    return a


def _insistir(a, peticion, respuesta="No he podido leer esa página."):
    a.pregunta_pura = peticion
    return a._insistir_si_hace_falta(respuesta, "ligero", "rapido", peticion, None, list(HERRAMIENTAS), "sistema")


def _llamada(a):
    args, k = a._gemini.call_args
    return args, k


def test_una_pregunta_insiste_solo_con_la_web_y_el_modelo_rapido(lina):
    r, modelo = _insistir(lina, PREGUNTA)
    args, k = _llamada(lina)
    assert r == "Respuesta del reintento." and args[0] == "rapido" and k["herramientas"] == [WEB, LEER]
    assert lina.reintento_solo_web is True and lina.max_tiempo == lina.A.TIEMPO_INSISTIR_SIN_AJUSTES == 60
    assert k["timeout"] == lina.A.TIMEOUT_INSISTIR_SIN_AJUSTES


def test_la_nota_no_lleva_el_no_pares_ni_la_instalacion(lina):
    _insistir(lina, PREGUNTA)
    nota = _llamada(lina)[0][2]
    assert "Solo puedes usar buscar_web y leer_web" in nota
    for prohibido in ("no pares", "instala", "mcp_servidores", "Tienes ordenador"):
        assert prohibido not in nota
    lina._avisar_voz.assert_not_called()


def test_con_lecturas_previas_sigue_siendo_pregunta(lina):
    lina.acciones_turno = [LECTURA]
    _insistir(lina, PREGUNTA)
    assert lina.reintento_solo_web is True


@pytest.mark.parametrize("nombre", ["ejecutar_comando", "mas_herramientas", "pensar_a_fondo", "abrir_app", "buscar_archivos"])
def test_el_codigo_rechaza_lo_demas_aunque_la_ia_lo_pida(lina, nombre):
    lina.reintento_solo_web = True
    lina._ejecutar_herramienta = MagicMock(side_effect=AssertionError("no debía ejecutarse"))
    assert "sin más herramientas" in lina.ejecutar_herramienta(nombre, {"comando": "grep -rn x ~"})


@pytest.mark.parametrize("nombre", ["buscar_web", "leer_web"])
def test_la_web_si_se_ejecuta(lina, nombre):
    lina.reintento_solo_web = True
    lina.crono = None
    lina._ejecutar_herramienta = MagicMock(return_value="ok")
    assert lina.ejecutar_herramienta(nombre, {}) == "ok"


def test_una_orden_insiste_como_siempre(lina):
    _insistir(lina, ORDEN)
    args, k = _llamada(lina)
    assert args[0] == "profundo" and k["herramientas"] == HERRAMIENTAS and lina.reintento_solo_web is False
    assert "no pares" in args[2]


def test_una_pregunta_con_la_que_se_cambio_algo_insiste_como_siempre(lina):
    lina.acciones_turno = [CAMBIO]
    _insistir(lina, "¿puedes cambiar el tema?")
    assert lina.reintento_solo_web is False and _llamada(lina)[1]["herramientas"] == HERRAMIENTAS


def test_con_una_duda_de_un_cambio_insiste_como_siempre(lina):
    lina.ejecutor.duda = "no se ha podido comprobar"
    _insistir(lina, PREGUNTA, "Hecho.")
    assert lina.reintento_solo_web is False and _llamada(lina)[0][0] == "profundo"


def test_si_la_ia_pidio_pensar_conserva_su_modelo_pero_no_las_herramientas(lina):
    lina.pedir_profundo = "es difícil"
    _insistir(lina, PREGUNTA, "Déjame pensarlo: la respuesta es que depende de tres cosas.")
    args, k = _llamada(lina)
    assert args[0] == "profundo" and k["herramientas"] == [WEB, LEER] and lina.reintento_solo_web is True


def test_lee_esa_pagina_si_la_web_bloquea_insiste_como_siempre(lina):
    lina.obstaculo = "leer la página https://ejemplo.test/p: la web no deja leerla a un programa"
    _insistir(lina, "lee la pagina")
    assert lina.reintento_solo_web is False and _llamada(lina)[0][0] == "profundo" and "mcp_servidores" in _llamada(lina)[0][2]


def test_preguntar_por_una_pagina_que_bloquea_se_queda_en_la_web(lina):
    lina.obstaculo = "leer la página https://ejemplo.test/p: la web no deja leerla a un programa"
    _insistir(lina, PREGUNTA)
    assert lina.reintento_solo_web is True and _llamada(lina)[1]["herramientas"] == [WEB, LEER]


CORTESIA = ["¿Puedes abrir Steam?", "¿Me abres Steam?", "¿Podrías subir el volumen?", "¿Me puedes poner música?", "¿Quieres cerrar el navegador?", "¿Te importa apagar la pantalla?",
            "¿Sabrías instalar VLC?", "¿Me subes el volumen?", "¿Me pones una canción?", "¿Te importaría bajar el brillo?", "¿Puedes reiniciar el Bluetooth?", "Oye, ¿podrías quitar el sonido?",
            "¿Nos pones música?", "¿Podrías, por favor, abrir Firefox?", "¿Me lo abres?", "¿Puedes ponerme música?"]
INFORMACION = ["¿Qué dice esta página?", "¿Cuánto cuesta un Steam Deck?", "¿Qué es la ferrita?", "¿Cómo abro Steam?", "¿Puedes decirme qué hora es?", "¿Me dices el precio del oro?",
               "¿Me explicas qué es un kernel?", "¿Sabrías decirme quién ganó ayer?", "¿Podrías contarme qué pasó?", "¿Cuándo sale el juego?", "¿Dónde consigo ferrita?",
               "¿Por qué sube el precio?", "¿Quién abrió la tienda?", "¿Qué pasa si subo el volumen?"]


@pytest.mark.parametrize("frase", CORTESIA)
def test_la_cortesia_con_un_verbo_de_hacer_conserva_el_reintento_con_el_equipo(lina, frase):
    _insistir(lina, frase)
    args, k = _llamada(lina)
    assert lina.reintento_solo_web is False and k["herramientas"] == HERRAMIENTAS and args[0] == "profundo"


@pytest.mark.parametrize("frase", INFORMACION)
def test_la_pregunta_de_informacion_se_queda_en_la_web(lina, frase):
    _insistir(lina, frase)
    args, k = _llamada(lina)
    assert lina.reintento_solo_web is True and k["herramientas"] == [WEB, LEER] and args[0] == "rapido"


def test_orden_de_cortesia_en_ingles(monkeypatch):
    from lina.nucleo import idioma as IDI
    from lina.nucleo import turnos as TU
    monkeypatch.setattr(IDI, "actual", lambda: "en")
    assert TU.orden_de_cortesia("Can you open Steam?") and TU.orden_de_cortesia("Could you please turn up the volume?")
    assert not TU.orden_de_cortesia("Can you tell me the time?") and not TU.orden_de_cortesia("What does this page say?")


def test_pide_accion_no_cambia():
    from lina.nucleo import turnos as TU
    assert TU.pide_accion("¿Puedes abrir Steam?") is False


def test_el_modo_a_fondo_pedido_no_reintenta_ni_cambia(lina):
    lina.pregunta_pura = PREGUNTA
    r = lina._insistir_si_hace_falta("No he podido.", "m", "profundo", PREGUNTA, None, list(HERRAMIENTAS), "s")
    assert r == ("No he podido.", "m")
    lina._gemini.assert_not_called()
    assert lina.reintento_solo_web is False


def test_el_primer_intento_conserva_sus_comandos(lina):
    lina.crono = None
    lina._ejecutar_herramienta = MagicMock(return_value="ok")
    assert lina.ejecutar_herramienta("ejecutar_comando", {"comando": "ls"}) == "ok"
