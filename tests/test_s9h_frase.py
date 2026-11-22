# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9h: una frase no se queda sin receta por cómo empieza ni por cómo está dicha. Si se aprende lo deciden los hechos del cambio; la forma de la frase
solo decide si queda el atajo de repetirla sin IA, que es conservador porque solo acelera. Caso real: «Que Caffeine no se abra solo…» no daba receta."""
import pytest

from lina.nucleo import recetas as REC

ORDEN = "printf '[Desktop Entry]\\nHidden=true\\n' > ~/.config/autostart/caffeine.desktop"
PASOS = [{"herr": "ejecutar_comando", "args": {"comando": ORDEN, "motivo": "ocultarla"}}]


@pytest.fixture(autouse=True)
def recetas(tmp_path, monkeypatch):
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(REC, "_en_privado", lambda: False)


@pytest.mark.parametrize("frase", ["Que Caffeine no se abra solo al iniciar sesión", "Quiero que Caffeine no arranque solo cuando enciendo",
                                   "¿Puedes hacer que Caffeine no se abra solo?", "Quita Caffeine del arranque y que no vuelva"])
def test_se_aprende_con_nombre_general_y_la_ia_la_encuentra(frase):
    r = REC.aprender_pasos(frase, PASOS, nombre="quitar una app del inicio automático", valor="caffeine")
    assert r and r["ajuste"] == "quitar una app del inicio automático" and "{valor}" in r["pasos"][0]["args"]["comando"]
    nota, ids = REC.ofrecer("Que Steam no se abra solo al quitarlo del inicio automático")
    assert ids == [r["id"]] and "{valor}" in nota


def test_sin_nombre_general_la_frase_da_nombre_a_la_receta():
    r = REC.aprender_pasos("Que Caffeine no se abra solo al iniciar sesión", PASOS)
    assert r and r["ajuste"].startswith("Que Caffeine no se abra solo")


def test_el_atajo_sin_ia_sigue_siendo_conservador():
    """Lo que no es una orden sencilla no se repite sin IA aunque la receta esté comprobada: la IA decide si encaja."""
    r = REC.aprender_pasos("Que Caffeine no se abra solo", PASOS, verificada=True)
    assert r["frases"] == [] and REC.para_frase("Que Caffeine no se abra solo") is None
    s = REC.aprender_pasos("quita caffeine del arranque", PASOS, verificada=True)
    assert s["frases"] and REC.para_frase("quita caffeine del arranque")


def test_lo_que_depende_del_momento_solo_con_nombre_general():
    assert REC.aprender_pasos("ciérralo", PASOS, atajo=False) is None
    r = REC.aprender_pasos("ciérralo", PASOS, atajo=False, nombre="quitar una app del inicio automático")
    assert r and r["frases"] == []


def test_los_hechos_siguen_mandando():
    """Lo que nunca se aprende sigue sin aprenderse, diga lo que diga la frase: tras leer de fuera, en privado, nada repetible o demasiados pasos."""
    assert REC.aprender_pasos("Que Caffeine no se abra solo", PASOS, web=True) is None
    assert REC.aprender_pasos("Que Caffeine no se abra solo", []) is None
    assert REC.aprender_pasos("Que Caffeine no se abra solo", [{"herr": "notas", "args": {}}]) is None


# ---------------------------------------------------------------- «No quiero que…»: por el hecho de si hay algo antes
def _asistente(frase, historial, general=None):
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = SimpleNamespace(cambio_comprobado=True, duda="", contaminado="", receta_turno=False, pendientes=[])
    a.modo_privado, a.turno_aceptado, a.insistiendo = False, True, False
    a.pregunta_pura, a.historial = frase, historial
    a.acciones_turno = [("ejecutar_comando", {"comando": ORDEN, "motivo": "ocultarla"}, "código de salida: 0 (0 s)\n\n✔ existe el archivo")]
    a._recetas_de_pasos_activas = lambda: True
    a._generalizar_receta = lambda frase, ordenes: general
    a._REC = lambda: REC
    return a


FRASE_NO = "No quiero que Caffeine arranque al iniciar sesión"


def test_un_no_sin_nada_antes_es_la_peticion():
    _asistente(FRASE_NO, [])._aprender_pasos()
    [r] = REC._cargar()
    assert r["pedido"] == FRASE_NO and r["frases"]


def test_un_no_con_algo_antes_solo_con_nombre_general_y_sin_atajo():
    antes = [{"rol": "user", "texto": "Pregunta: abre Caffeine"}, {"rol": "model", "texto": "Abierto."}]
    _asistente(FRASE_NO, antes)._aprender_pasos()
    assert REC._cargar() == []
    _asistente(FRASE_NO, antes, general=("quitar una app del inicio automático", "caffeine"))._aprender_pasos()
    [r] = REC._cargar()
    assert r["ajuste"] == "quitar una app del inicio automático" and r["frases"] == [] and "{valor}" in r["pasos"][0]["args"]["comando"]
