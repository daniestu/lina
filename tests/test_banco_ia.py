# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A2: el banco de la IA. Con las respuestas grabadas de tests/datos/banco_ia.json, sin IA ni red. La pasada real es `lina probar-ia`, y ahí tampoco se ejecuta ninguna herramienta."""
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lina.nucleo import banco_ia as B
from lina.nucleo import declaraciones as DEC
from lina.nucleo import directas as DIR
from lina.nucleo import grupos as G

GRABADAS = json.loads((Path(__file__).parent / "datos" / B.ARCHIVO).read_text(encoding="utf-8"))["llamadas"]
CASOS = {c.frase: c for c in B.CASOS}


def test_cada_frase_tiene_su_grabacion_y_viceversa():
    assert set(GRABADAS) == set(CASOS)


def test_ninguna_frase_es_una_orden_directa():
    """Una orden directa actuaría de verdad en la pasada real."""
    assert [c.frase for c in B.CASOS if DIR.entender(c.frase) is not None] == []


@pytest.mark.parametrize("frase", list(GRABADAS))
def test_la_grabacion_pasa_el_juez(frase):
    assert B.juzgar(CASOS[frase], GRABADAS[frase])[0] == "bien"


def test_las_grabaciones_solo_usan_herramientas_que_existen():
    existen = {d["name"] for d in DEC.DECLARACIONES} | {G.META, "buscar_web"}
    assert {n for ll in GRABADAS.values() for n, _ in ll} <= existen


@pytest.mark.parametrize("caso, llamadas, motivo", [
    (B.Caso("x", debe=("buscar_web",)), [], "no ha usado buscar_web"),
    (B.Caso("x", debe=(("crear_documento", "disenar_documento"),)), [("notas", {})], "crear_documento/disenar_documento"),
    (B.Caso("x", nunca=("ejecutar_comando",)), [("ejecutar_comando", {"comando": "ls"})], "que aquí no toca"),
    (B.Caso("x", sin_herramientas=True), [("buscar_web", {})], "no hacía falta"),
    (B.Caso("x", debe=("buscar_web",), abre=True), [("buscar_web", {}), ("ejecutar_comando", {"comando": "ls"})], "no ha abierto"),
])
def test_el_juez_detecta_lo_que_esta_mal(caso, llamadas, motivo):
    nota, explicacion = B.juzgar(caso, llamadas)
    assert nota == "mal" and motivo in explicacion


def test_pedir_un_grupo_no_cuenta_como_usar_una_herramienta():
    assert B.juzgar(B.Caso("x", sin_herramientas=True), [(G.META, {"grupo": "web"})])[0] == "bien"


def test_la_pasada_apunta_y_no_ejecuta_nada():
    a, abiertas = MagicMock(), []
    real = MagicMock()
    a._ejecutar_herramienta = real

    def frase(texto, A, asistente, abiertas):
        assert asistente._ejecutar_herramienta("buscar_web", {"consulta": texto}).startswith("RESULTADOS DE BÚSQUEDA")
        assert asistente._ejecutar_herramienta("ejecutar_comando", {"comando": "rm x"}) == B.HECHO
    llamadas = B.pasar(B.Caso("hola"), MagicMock(_abortar=threading.Event()), a, abiertas, frase)
    assert [n for n, _ in llamadas] == ["buscar_web", "ejecutar_comando"]
    real.assert_not_called()


def test_pedir_un_grupo_lo_carga_de_verdad():
    a = MagicMock()
    a.cargar_grupo.return_value = "Cargado archivos: ya puedes usar hoja_calculo."

    def frase(texto, A, asistente, abiertas):
        assert asistente._ejecutar_herramienta(G.META, {"grupo": "archivos"}) == a.cargar_grupo.return_value
    llamadas = B.pasar(B.Caso("hola"), MagicMock(), a, [], frase)
    a.cargar_grupo.assert_called_once_with("archivos")
    assert llamadas == [(G.META, {"grupo": "archivos"})]


def test_grabar_deja_el_archivo_en_el_estado(monkeypatch, tmp_path):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(B.RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: GRABADAS[caso.frase])
    salida = []
    assert B.principal(["--grabar"], salida.append) == 0
    guardado = json.loads((tmp_path / B.ARCHIVO).read_text(encoding="utf-8"))
    assert guardado["origen"] == "modelo" and set(guardado["llamadas"]) == set(GRABADAS)


def test_si_alguna_falla_termina_con_error(monkeypatch):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: [])
    assert B.principal(["2"], lambda t: None) == 1


def test_ayuda():
    salida = []
    assert B.principal(["--help"], salida.append) == 0 and "probar-ia" in salida[0]


def test_cada_herramienta_declarada_tiene_quien_la_ejecute():
    """M2: lo que ofrece la IA y lo que se ejecuta no pueden separarse."""
    import sys
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    declaradas = {d["name"] for d in DEC.DECLARACIONES} | {G.META, "buscar_web", "usar_fuente", "necesito_datos_actuales"}
    assert declaradas - set(A.Asistente._HERRAMIENTAS) == set()


def test_una_herramienta_desconocida_lo_dice():
    import sys
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    assert A.Asistente.__new__(A.Asistente)._ejecutar_herramienta("no_existe", {}) == "Herramienta desconocida: no_existe"
