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
def test_steam_y_protondb_y_lo_que_recibe_la_ia():
    datos = COMP.consultar("275850", get=red())
    assert datos == {"linux": False, "nivel": "gold"}
    texto = COMP.como_texto("No Man's Sky", datos)
    assert "versión para Linux: NO (se juega con Proton)" in texto and "gold (bien, con pocos problemas)" in texto and "sin cifras" in texto


def test_si_protondb_falla_basta_steam_y_si_fallan_los_dos_no_hay_nada():
    assert COMP.consultar("275850", get=red(protondb_ok=False)) == {"linux": False, "nivel": None}
    assert COMP.consultar("275850", get=red(steam_ok=False, protondb_ok=False)) is None


# ---------------------------------------------------------------- la conversación real, en el asistente (A13: contesta la IA con lo comprobado)
@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[])
    a.acciones_turno, a.historial, a.contexto, a.forzar_busqueda, a.compatibilidad_turno = [], [], {"tipo": "general"}, False, None
    reales = A.Asistente.ejecutar_herramienta

    def ejecutar(nombre, args):
        if nombre == "compatibilidad_linux":
            r = a._h_compatibilidad_linux(nombre, args)
        else:
            r = "RESULTADOS DE BÚSQUEDA (…):\n\n[1] T (nomanssky.com) https://nomanssky.com/x\nx"
        a.acciones_turno.append((nombre, args, r))
        return r
    a.ejecutar_herramienta = MagicMock(side_effect=ejecutar)
    monkeypatch.setattr(A, "modo_busqueda", lambda: "auto")
    monkeypatch.setattr(COMP, "juego_de", lambda frase, contexto, buscar=None: COMP.__dict__["_juego_real"](frase, contexto, BIBLIOTECA))
    monkeypatch.setattr(COMP, "consultar", lambda appid, get=None: COMP.__dict__["_consultar_real"](appid, red()))
    monkeypatch.setattr(COMP, "appid_por_nombre", lambda nombre, get=None: None)
    monkeypatch.setattr(AVB, "primera_vez", lambda motivo: ("Lina: he mirado Steam y ProtonDB", "ven el número del juego"))
    avisos = []
    monkeypatch.setattr(A.H, "notificar", lambda titulo, texto: avisos.append(titulo))
    a.avisos, a.A, a._reales = avisos, A, reales
    return a


COMP._juego_real, COMP._consultar_real = COMP.juego_de, COMP.consultar


@pytest.mark.parametrize("pregunta", [P1, "¿Funciona No Man's Sky en Linux?", "¿No Man's Sky es nativo o hace falta Proton?"])
def test_la_compatibilidad_llega_a_la_ia_como_dato_comprobado(lina, pregunta):
    """Tres formulaciones: la IA recibe lo que dicen Steam y ProtonDB y contesta ella; el aviso de privacidad sale antes de la respuesta."""
    lina.pregunta_pura = pregunta
    directa, nota = lina._comprobar_antes()
    assert directa is None and "DATOS COMPROBADOS" in nota and "versión para Linux: NO" in nota and "gold" in nota
    assert lina.avisos == ["Lina: he mirado Steam y ProtonDB"] and lina.compatibilidad_turno[1] == {"linux": False, "nivel": "gold"}


@pytest.mark.parametrize("dice", ["No Man's Sky es nativo de Linux y funciona perfectamente sin Proton.", "Tiene versión para Linux, no necesita Proton.",
                                  "Funciona de forma nativa en Linux."])
def test_si_la_ia_contradice_lo_comprobado_se_corrige(lina, dice):
    lina.compatibilidad_turno = ("No Man's Sky", {"linux": False, "nivel": "gold"})
    assert lina._no_contradice_lo_comprobado(dice).endswith("Corrijo: según la tienda de Steam, No Man's Sky no tiene versión para Linux; se juega con Proton.")


@pytest.mark.parametrize("dice", ["Según la tienda de Steam, No Man's Sky no tiene versión para Linux: se juega con Proton.", "No es nativo: necesita Proton.",
                                  "Según ProtonDB funciona bien con Proton."])
def test_lo_que_cuadra_no_se_toca(lina, dice):
    lina.compatibilidad_turno = ("No Man's Sky", {"linux": False, "nivel": "gold"})
    assert lina._no_contradice_lo_comprobado(dice) == dice


def test_la_conversacion_de_no_mans_sky(lina):
    """La real: «¿hay que hacer algo de Proton?» y después «creo que estás equivocado, sí requiere Proton»: las dos veces llegan los datos comprobados."""
    lina.pregunta_pura = P1
    _, nota1 = lina._comprobar_antes()
    lina.historial = [{"rol": "user", "texto": P1}, {"rol": "model", "texto": "No tiene versión para Linux."}]
    lina.acciones_turno, lina.pregunta_pura = [], P2
    _, nota2 = lina._comprobar_antes()
    assert "DATOS COMPROBADOS" in nota1 and "DATOS COMPROBADOS" in nota2 and "No defiendas lo de antes sin datos" in nota2


@pytest.mark.parametrize("frase", ["No tienes el resultado porque aún se está jugando.", "No, aún no ha concluido.", "Que te estoy diciendo que se está jugando ahora mismo."])
def test_discutir_un_dato_se_comprueba_con_una_busqueda(lina, frase):
    """Tres frases reales del 2026-11-15: el atajo adelanta la búsqueda si encaja; si no encaja, decide la IA con la regla de las instrucciones."""
    lina.historial = [{"rol": "user", "texto": "¿Quién ha ganado la final de los Worlds?"}, {"rol": "model", "texto": "Ganó T1, 3-1."}]
    lina.pregunta_pura = frase
    _, nota = lina._comprobar_antes()
    if COMP.discute_un_dato(frase):
        assert "No defiendas lo de antes" in nota
    else:
        assert nota == ""


def test_un_dato_de_juego_que_no_es_de_compatibilidad_se_busca_antes(lina):
    lina.pregunta_pura = "¿Cuándo sale la próxima actualización de No Man's Sky?"
    _, nota = lina._comprobar_antes()
    assert "ya lo he buscado" in nota and "nomanssky.com" in nota


def test_con_la_busqueda_apagada_discutir_no_defiende_lo_de_antes(lina, monkeypatch):
    monkeypatch.setattr(sys.modules["lina.nucleo.asistente"], "modo_busqueda", lambda: "ninguna")
    lina.historial = [{"rol": "user", "texto": "¿Qué planeta es mejor?"}]
    lina.pregunta_pura = "Creo que no es así."
    _, nota = lina._comprobar_antes()
    assert "no lo he podido comprobar" in nota and "solo esta vez" in nota


def test_lo_demas_no_se_toca(lina):
    for frase in ("Abre No Man's Sky.", "¿Cómo consigo plasma inestable?", "Cuéntame un chiste."):
        lina.pregunta_pura = frase
        assert lina._comprobar_antes() == (None, "")
    lina.ejecutar_herramienta.assert_not_called()
