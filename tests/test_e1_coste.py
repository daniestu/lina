# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""E1c: a una pregunta de información le van las reglas del núcleo sin las de actuar; si aun así la IA pide una acción, no se ejecuta y la petición se repite
con todas las reglas (la red), salvo que la herramienta no exista. Sin red ni IA. (E1d, resultados de búsqueda más cortos, se midió y se descartó.)"""
import re
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import grupos as G
from lina.nucleo import ia as IA


# ---------------------------------------------------------------- E1c: las reglas
def _numeros(texto):
    return sorted(int(n) for n in re.findall(r"(?<!\S)(\d{1,2})\) ", texto))


def test_las_reglas_de_informacion_no_llevan_las_de_actuar():
    completas, info = G.reglas_nucleo(), G.reglas_nucleo(solo_informacion=True)
    assert _numeros(completas) == list(range(1, 23))
    assert _numeros(info) == [n for n in range(1, 23) if n not in G.REGLAS_SOLO_ACCIONES]
    assert len(info) < 0.55 * len(completas)


@pytest.mark.parametrize("n", [1, 4, 19, 21])
def test_las_de_seguridad_y_honestidad_van_siempre(n):
    assert n not in G.REGLAS_SOLO_ACCIONES and f" {n}) " in " " + G.reglas_nucleo(solo_informacion=True)


def test_el_sistema_con_reglas_de_informacion():
    a = G.sistema("INSTR", "HECHOS", [], solo_informacion=True)
    assert "INSTR" in a and a.endswith("HECHOS") and "BORRAR" not in a and "DESTRUCCIÓN TOTAL" in a and "FUENTES HONRADAS" in a
    assert "BORRAR" in G.sistema("INSTR", "HECHOS", [])


# ---------------------------------------------------------------- E1c: qué peticiones y la red
@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[])
    a.forzar_busqueda = False
    a.A = A
    return a


@pytest.mark.parametrize("frase, info", [
    ("¿Cuánto mide la torre Eiffel?", True), ("qué tiempo hará mañana en Sevilla", True), ("¿Qué es el protocolo MCP?", True),
    ("Abre Firefox.", False), ("¿Puedes abrir Steam?", False), ("Ponme el partido del Barça.", False), ("Borra la carpeta de descargas.", False),
    ("Sube el volumen.", False),
    # el estado del propio equipo se mira con un comando: con todas las reglas desde el principio (aprobado el 2026-11-14)
    ("¿Cuánta memoria RAM está usando el equipo?", False), ("¿Qué juegos tengo instalados?", False), ("¿Cuánto espacio libre queda en el disco?", False),
    ("¿A qué temperatura está la CPU?", False), ("¿Qué procesos están gastando más?", False), ("How much memory is in use?", False),
    # lo demás sigue igual
    ("¿Qué has cambiado hoy en el equipo?", True), ("¿Cuánto llevo gastado este mes en la IA?", True), ("¿Cómo consigo plasma inestable?", True),
])
def test_que_peticiones_van_con_reglas_de_informacion(lina, frase, info):
    lina.pregunta_pura = frase
    assert lina._es_solo_informacion() is info


def test_una_herramienta_que_no_existe_no_dispara_la_red(lina):
    """Medida de E1c: la IA llamó a «ejecutando_comando», que no existe; la red repetía la petición entera para nada (fallaría igual con todas las reglas)."""
    lina.herramientas_turno = [{"name": "buscar_web"}, {"name": "ejecutar_comando"}]
    assert lina._es_accion("ejecutando_comando", {"comando": "free -h"}) is False
    assert lina._es_accion("ejecutar_comando", {"comando": "rm -r ~/Descargas"}) is True


@pytest.mark.parametrize("nombre, args, accion", [
    ("buscar_web", {"consulta": "x"}, False), ("leer_web", {"url": "https://x"}, False), ("ver_juegos", {}, False),
    ("ejecutar_comando", {"comando": "free -h"}, False), ("ejecutar_comando", {"comando": "rm -r ~/Descargas"}, True),
    ("abrir_app", {"nombre": "firefox"}, True), ("notas", {"accion": "anadir"}, True),
])
def test_que_es_una_accion(lina, nombre, args, accion):
    assert lina._es_accion(nombre, args) is accion


def test_la_red_una_accion_con_reglas_de_informacion_no_se_ejecuta(lina):
    lina.reglas_reducidas, lina.fuente_cerrada, lina.reintento_solo_web = True, False, False
    lina._ejecutar_herramienta = MagicMock(side_effect=AssertionError("no se ejecuta"))
    with pytest.raises(IA.NecesitaReglasCompletas):
        lina.ejecutar_herramienta("abrir_app", {"nombre": "firefox"})


def test_la_red_en_preguntar_ia_termina_el_turno_con_la_marca(monkeypatch):
    monkeypatch.setattr(IA, "_pausa_modelo", {})
    monkeypatch.setattr(IA.PRES, "registrar", lambda *x, **k: None)
    monkeypatch.setattr(IA, "_turno_medido", lambda *a, **k: MagicMock(llamadas=[IA.PROV.Llamada("abrir_app", {"nombre": "firefox"})], texto="", uso={}, modelo_real=None))

    def ejecutar(nombre, args):
        raise IA.NecesitaReglasCompletas()
    r = IA.preguntar_ia(MagicMock(), "clave", "m", "¿qué es firefox?", None, herramientas=[{"name": "abrir_app"}], ejecutar_herramienta=ejecutar)
    assert r == IA.REGLAS_COMPLETAS


def test_la_red_repite_la_peticion_con_todas_las_reglas(lina, monkeypatch):
    """Una «pregunta» que en realidad pedía actuar: el primer intento (reglas de información) pide abrir algo y se corta; el segundo va con todas las reglas."""
    A = lina.A
    sistemas = []

    def gemini(modo, modelo, pregunta, imagen, historial, **k):
        sistemas.append(k["sistema"])
        return A.REGLAS_COMPLETAS if len(sistemas) == 1 else "Te lo abro."
    lina._gemini = gemini
    lina.clave, lina.contexto, lina.historial, lina.acciones_confirmadas = "clave", {"tipo": "general"}, [], []
    lina.pregunta_pura = "¿Qué es Firefox?"
    for nombre in ("_preparar_grupos_mcp", "elegir_grupos"):
        setattr(lina, nombre, lambda *x, **k: [])
    lina._comprobar_antes = lambda: (None, "")
    lina._herramienta_de_fuente = lambda: []
    lina._buscar_igualmente = lambda p: False
    lina._con_pantalla_si_la_pide = lambda r, m, *x: (r, m)
    lina._insistir_si_hace_falta = lambda r, m, *x: (r, m)
    lina.asegurar_honestidad_final = lambda t: t
    lina.asegurar_pregunta_pendiente = lambda t: t
    monkeypatch.setattr(A.IAC, "modelos", lambda modo: ["m"])
    monkeypatch.setattr(A.H, "hechos_sistema", lambda: "HECHOS")
    r, _ = lina._responder("¿Qué es Firefox?", None)
    assert r == "Te lo abro." and len(sistemas) == 2 and "BORRAR" not in sistemas[0] and "BORRAR" in sistemas[1] and lina.reglas_reducidas is False
