# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Bloque D3: datos concretos de un juego se comprueban antes de contestar, y «creo que estás equivocado» se comprueba en vez de defender lo dicho.
El caso real, entero: No Man's Sky y Proton. Sin red: Steam, ProtonDB, la biblioteca y la búsqueda son simulados."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import compatibilidad as COMP

NMS = {"nombre": "No Man's Sky", "id": "275850", "origen": "steam"}
BIBLIOTECA = lambda q: [(84, NMS)] if "no man" in q.lower() else []      # noqa: E731
P1 = "Quiero jugar a No Man's Sky, lo tengo instalado en Steam, ¿hay que hacer algo de Proton?"
P2 = "Creo que estás equivocado, sí requiere Proton."


def respuesta(cuerpo, ok=True):
    r = MagicMock(ok=ok)
    r.json.return_value = cuerpo
    return r


def red(linux=False, nivel="gold", steam_ok=True, protondb_ok=True):
    def get(url, params=None, headers=None, timeout=None):
        assert headers["User-Agent"].startswith("Lina/")
        if "store.steampowered.com" in url:
            assert params["appids"] == "275850"
            return respuesta({"275850": {"success": True, "data": {"platforms": {"windows": True, "mac": True, "linux": linux}}}}, steam_ok)
        assert url == "https://www.protondb.com/api/v1/reports/summaries/275850.json"
        return respuesta({"tier": nivel, "total": 1787}, protondb_ok)
    return get


# ---------------------------------------------------------------- qué frases lo disparan
@pytest.mark.parametrize("frase, contexto, si", [
    (P1, {"tipo": "general"}, True),
    ("¿Funciona Elden Ring en Linux?", {"tipo": "general"}, False),                                 # no está en la biblioteca simulada ni dice «juego»
    ("¿Este juego funciona en Linux?", {"tipo": "general"}, True),
    ("¿Qué versión tiene ahora?", {"tipo": "juego", "nombre": "No Man's Sky", "clase": "steam_app_275850"}, True),
    ("¿Cuándo sale la próxima actualización de No Man's Sky?", {"tipo": "general"}, True),
    ("¿Cómo consigo plasma inestable?", {"tipo": "juego", "nombre": "No Man's Sky", "clase": "steam_app_275850"}, False),   # jugar, no un dato del juego
    ("Abre No Man's Sky con Proton.", {"tipo": "general"}, False),                                    # una orden: nunca
    ("Actualiza el sistema.", {"tipo": "general"}, False),
    ("¿Qué versión de Firefox tengo?", {"tipo": "general"}, False),                                   # sin juego de por medio
])
def test_que_dispara_la_comprobacion_previa(frase, contexto, si):
    assert COMP.pide_dato_de_juego(frase, contexto, buscar=BIBLIOTECA) is si


@pytest.mark.parametrize("frase, si", [(P2, True), ("Eso no es así.", True), ("¿Estás seguro? Me parece que no.", True), ("You're wrong.", True),
                                       ("Creo que sí, ponlo.", False), ("Vale, gracias.", False), ("¿Y cómo consigo platino?", False)])
def test_cuando_le_dices_que_se_equivoca(frase, si):
    assert COMP.discute_un_dato(frase) is si


def test_el_juego_sale_de_la_biblioteca_o_de_la_ventana():
    assert COMP.juego_de(P1, {"tipo": "general"}, buscar=BIBLIOTECA) == NMS
    assert COMP.juego_de("¿funciona con Proton?", {"tipo": "juego", "nombre": "No Man's Sky", "clase": "steam_app_275850"}, buscar=lambda q: []) == NMS
    assert COMP.juego_de("¿funciona con Proton?", {"tipo": "general"}, buscar=lambda q: [(70, NMS)]) is None      # un parecido de sonido no basta


@pytest.mark.parametrize("frase, si", [
    (P1, True), ("¿Funciona en Linux?", True), ("¿Es nativo?", True), ("¿Hace falta Proton?", True), ("¿Does it run on Linux?", True),
    ("¿Cuál es la mejor versión de Proton para este juego?", False),          # no pregunta si funciona: se busca, no lo decide el código
    ("¿Qué es Proton?", False),
])
def test_solo_si_pregunta_si_funciona_lo_decide_el_codigo(frase, si):
    assert COMP.pide_compatibilidad(frase) is si


# ---------------------------------------------------------------- lo que dice, decidido con código
def test_steam_y_protondb_deciden_y_la_frase_es_corta_y_sin_cifras():
    datos = COMP.consultar("275850", get=red())
    assert datos == {"linux": False, "nivel": "gold"}
    texto = COMP.frase("No Man's Sky", datos)
    assert texto == ("Según la tienda de Steam, No Man's Sky no tiene versión para Linux: se juega con Proton. "
                     "Y según ProtonDB, con Proton funciona bien, con pocos problemas.")
    assert not any(c.isdigit() for c in texto) and len(texto) < 200


def test_nativo():
    assert COMP.frase("Juego", {"linux": True, "nivel": "platinum"}) == "Según la tienda de Steam, Juego tiene versión para Linux, así que no necesita Proton."


def test_si_protondb_falla_basta_steam_y_si_fallan_los_dos_no_hay_nada():
    assert COMP.consultar("275850", get=red(protondb_ok=False)) == {"linux": False, "nivel": None}
    assert COMP.frase("No Man's Sky", {"linux": False, "nivel": None}) == "Según la tienda de Steam, No Man's Sky no tiene versión para Linux: se juega con Proton."
    assert COMP.consultar("275850", get=red(steam_ok=False, protondb_ok=False)) is None


# ---------------------------------------------------------------- la conversación real, en el asistente
@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[])
    a.acciones_turno, a.historial, a.contexto, a.forzar_busqueda = [], [], {"tipo": "general"}, False
    a.ejecutar_herramienta = MagicMock(return_value="RESULTADOS DE BÚSQUEDA (…):\n\n[1] T (nomanssky.com) https://nomanssky.com/x\nx")
    monkeypatch.setattr(A, "modo_busqueda", lambda: "auto")
    monkeypatch.setattr(COMP, "juego_de", lambda frase, contexto, buscar=None: COMP.__dict__["_juego_real"](frase, contexto, BIBLIOTECA))
    monkeypatch.setattr(COMP, "consultar", lambda appid, get=None: COMP.__dict__["_consultar_real"](appid, red()))
    AVB._pendientes.clear()
    return a


COMP._juego_real, COMP._consultar_real = COMP.juego_de, COMP.consultar


def test_la_conversacion_de_no_mans_sky(lina):
    """1) «¿hay que hacer algo de Proton?»: contesta el código con Steam y ProtonDB, sin llamar a la IA ni de memoria. 2) «creo que estás equivocado»: se
    comprueba otra vez y se dice lo comprobado, sin contradecirse."""
    lina.pregunta_pura = P1
    primera, nota = lina._comprobar_antes()
    assert nota == "" and primera.startswith("Según la tienda de Steam, No Man's Sky no tiene versión para Linux: se juega con Proton.")
    assert "nativ" not in primera and AVB.PRIMERA_COMPATIBILIDAD in AVB._pendientes
    lina.historial = [{"rol": "user", "texto": P1}, {"rol": "model", "texto": primera}]
    lina.acciones_turno, lina.pregunta_pura = [], P2
    segunda, nota = lina._comprobar_antes()
    assert segunda == "Lo he comprobado: " + primera and nota == ""
    lina.ejecutar_herramienta.assert_not_called()


def test_un_dato_de_juego_que_no_es_de_compatibilidad_se_busca_antes(lina):
    lina.pregunta_pura = "¿Cuándo sale la próxima actualización de No Man's Sky?"
    directa, nota = lina._comprobar_antes()
    lina.ejecutar_herramienta.assert_called_once_with("buscar_web", {"consulta": "¿Cuándo sale la próxima actualización de No Man's Sky?"})
    assert directa is None and "ya lo he buscado" in nota and "nomanssky.com" in nota


def test_si_discutes_algo_que_no_se_puede_comprobar_no_defiende_lo_de_antes(lina):
    lina.historial = [{"rol": "user", "texto": "¿Qué planeta es mejor para el cristal de tormenta?"}, {"rol": "model", "texto": "Uno con clima extremo."}]
    lina.pregunta_pura = "Eso no es así."
    lina.ejecutar_herramienta.return_value = "NO SE HA PODIDO BUSCAR: no tienes clave de Tavily."
    directa, _ = lina._comprobar_antes()
    assert directa == "No lo he podido comprobar; puede que tengas razón."
    lina.ejecutar_herramienta.return_value = "RESULTADOS DE BÚSQUEDA (…):\n\n[1] T (nomanssky.fandom.com) https://x\nx"
    directa, nota = lina._comprobar_antes()
    assert directa is None and "No defiendas lo de antes sin datos" in nota and "cristal de tormenta" in str(lina.ejecutar_herramienta.call_args)


def test_con_la_busqueda_apagada_lo_dice(lina, monkeypatch):
    monkeypatch.setattr(lina.A if hasattr(lina, "A") else sys.modules["lina.nucleo.asistente"], "modo_busqueda", lambda: "ninguna")
    lina.historial = [{"rol": "user", "texto": "¿Qué planeta es mejor?"}]
    lina.pregunta_pura = "Creo que no es así."
    assert lina._comprobar_antes()[0] == "No lo he podido comprobar porque la búsqueda está apagada; puede que tengas razón."


def test_lo_demas_no_se_toca(lina):
    for frase in ("Abre No Man's Sky.", "¿Cómo consigo plasma inestable?", "Cuéntame un chiste."):
        lina.pregunta_pura = frase
        assert lina._comprobar_antes() == (None, "")
    lina.ejecutar_herramienta.assert_not_called()
