# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V12: la visión no vuelve a esperar al modelo que acaba de agotar el tiempo, y el revisor no prueba un segundo modelo.

Caso real (2026-11-16): «Haz clic en el botón de siguiente episodio» tardó 79,5 s. Al localizar el botón, el mismo modelo agotó sus 25 s dos veces (en la
mirada siguiente y con la otra clave), y el revisor agotó sus 4 s con ese mismo modelo. Sin red ni IA: el proveedor es falso.
"""
import pytest

from lina.nucleo import ia as IA
from lina.nucleo import proveedores as PROV

FLASH, LITE = "gemini-flash-latest", "gemini-flash-lite-latest"
TIEMPO_AGOTADO = PROV.ErrorIA("red", None, "HTTPSConnectionPool(host='x', port=443): Read timed out. (read timeout=20)")
SIN_CONEXION = PROV.ErrorIA("red", None, "HTTPSConnectionPool(host='x', port=443): Max retries exceeded (Name or service not known)")
BIEN = PROV.Respuesta(texto='{"x": 1}', uso={}, modelo_real=LITE)


@pytest.fixture
def llamadas(monkeypatch):
    """Sustituye la llamada a la IA: `llamadas.da[modelo]` es lo que responde cada modelo; apunta (modelo, clave, timeout) de cada llamada."""
    class Llamadas(list):
        da: dict = {}
    hechas = Llamadas()
    for nombre in ("_pausa_modelo", "_pausa_vision", "_fallos_red"):          # cada prueba, sin pausas de otra
        monkeypatch.setattr(IA, nombre, {})

    def turno(proveedor, clave, modelo, sistema, mensajes, timeout=None, **k):
        hechas.append((modelo, clave, timeout))
        return hechas.da.get(modelo, BIEN)
    monkeypatch.setattr(IA, "_turno_medido", turno)
    monkeypatch.setattr(IA, "_registrar_uso", lambda *a, **k: None)
    monkeypatch.setattr(IA.PRES, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(IA.PRES, "una_sola_clave", lambda: False)
    monkeypatch.setattr(IA.PRES, "nombre_de", lambda clave: clave)
    return hechas


def _mirar(clave="gratis", modelos=(FLASH, LITE)):
    return IA.ver_imagen(clave, "imagen", "¿dónde está el botón?", "sistema", modelos=list(modelos), proveedor=object())


def test_tras_agotar_el_tiempo_la_mirada_siguiente_no_vuelve_a_ese_modelo(llamadas):
    llamadas.da = {FLASH: TIEMPO_AGOTADO}
    assert _mirar()[0] == '{"x": 1}'                       # Flash agota el tiempo y contesta Flash-Lite
    assert [m for m, _, _ in llamadas] == [FLASH, LITE]
    del llamadas[:]
    assert _mirar()[0] == '{"x": 1}'                       # la mirada siguiente (la ampliación, la comprobación): directamente Flash-Lite
    assert _mirar(clave="pago")[0] == '{"x": 1}'           # y con la otra clave tampoco se vuelve a esperar a Flash
    assert [m for m, _, _ in llamadas] == [LITE, LITE]


def test_a_los_diez_minutos_se_vuelve_a_probar(llamadas, monkeypatch):
    llamadas.da = {FLASH: TIEMPO_AGOTADO}
    _mirar()
    ahora = IA.time.time()
    monkeypatch.setattr(IA.time, "time", lambda: ahora + IA.PAUSA_VISION_SEG + 1)
    del llamadas[:]
    _mirar()
    assert llamadas[0][0] == FLASH


@pytest.mark.parametrize("fallo", [SIN_CONEXION, PROV.ErrorIA("servidor", 503, "ocupado")])
def test_un_fallo_que_no_es_de_tiempo_no_deja_la_pausa_de_vision(llamadas, fallo):
    llamadas.da = {FLASH: fallo}
    _mirar()
    assert IA._pausa_vision == {}


def test_la_pausa_de_vision_no_toca_las_preguntas_normales(llamadas):
    llamadas.da = {FLASH: TIEMPO_AGOTADO}
    _mirar()
    assert IA._pausa_modelo == {}                           # el modelo sigue disponible para contestar


def test_una_mirada_espera_veinte_segundos(llamadas):
    _mirar()
    assert llamadas[0][2] == IA.TIMEOUT_VISION == 20


# ---------------------------------------------------------------- el revisor
def _revisar():
    return IA.verificar_cumplimiento("gratis", "sube el volumen", [("ejecutar_comando", {"comando": "x"}, "código de salida: 0")], "Hecho.")


def test_el_revisor_con_su_modelo_en_pausa_no_prueba_otro_y_lo_apunta(llamadas, monkeypatch, capsys):
    monkeypatch.setattr(IA.IAC, "modelos", lambda modo: [LITE, FLASH])
    IA._pausa_modelo[IA._id_pausa(LITE, "gratis")] = IA.time.time() + 60
    assert _revisar() is False
    assert llamadas == []                                   # antes: 4 s esperando a Flash
    assert "la respuesta sale SIN REVISAR" in capsys.readouterr().out


def test_el_revisor_que_agota_el_tiempo_no_prueba_otro_y_lo_apunta(llamadas, monkeypatch, capsys):
    monkeypatch.setattr(IA.IAC, "modelos", lambda modo: [LITE, FLASH])
    llamadas.da = {LITE: TIEMPO_AGOTADO}
    assert _revisar() is False
    assert [m for m, _, _ in llamadas] == [LITE] and "SIN REVISAR" in capsys.readouterr().out


def test_el_revisor_que_contesta_no_apunta_nada(llamadas, monkeypatch, capsys):
    monkeypatch.setattr(IA.IAC, "modelos", lambda modo: [LITE, FLASH])
    llamadas.da = {LITE: PROV.Respuesta(texto='{"decision": "cumplido", "motivo": "ninguno"}', uso={}, modelo_real=LITE)}
    assert _revisar() is False and "SIN REVISAR" not in capsys.readouterr().out
