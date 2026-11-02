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
        return [], ["Hecho."], 0.1
    llamadas, dicho = B.pasar(B.Caso("hola"), MagicMock(_abortar=threading.Event()), a, abiertas, frase)
    assert [n for n, _ in llamadas] == ["buscar_web", "ejecutar_comando"] and dicho == "Hecho."
    real.assert_not_called()


def test_pedir_un_grupo_lo_carga_de_verdad():
    a = MagicMock()
    a.cargar_grupo.return_value = "Cargado archivos: ya puedes usar hoja_calculo."

    def frase(texto, A, asistente, abiertas):
        assert asistente._ejecutar_herramienta(G.META, {"grupo": "archivos"}) == a.cargar_grupo.return_value
        return [], [], 0.1
    llamadas, _ = B.pasar(B.Caso("hola"), MagicMock(), a, [], frase)
    a.cargar_grupo.assert_called_once_with("archivos")
    assert llamadas == [(G.META, {"grupo": "archivos"})]


def test_grabar_deja_el_archivo_en_el_estado(monkeypatch, tmp_path):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(B.RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: (GRABADAS[caso.frase], "Vale."))
    salida = []
    assert B.principal(["--grabar"], salida.append) == 0
    guardado = json.loads((tmp_path / B.ARCHIVO).read_text(encoding="utf-8"))
    assert guardado["origen"] == "modelo" and set(guardado["llamadas"]) == set(GRABADAS)


def test_si_alguna_falla_termina_con_error(monkeypatch):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: ([], ""))
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


def _pasada(**notas):
    return {f: n for f, n in notas.items()}


def test_comparar_ignora_lo_inestable_antes_y_separa_el_resto():
    a1 = _pasada(fija="bien", baila="bien", cae="bien", duda="bien", sube="mal", suelta="bien")
    a2 = _pasada(fija="bien", baila="mal", cae="bien", duda="bien", sube="mal")
    d1 = _pasada(fija="bien", baila="mal", cae="mal", duda="mal", sube="bien")
    d2 = _pasada(fija="bien", baila="mal", cae="mal", duda="bien", sube="bien")
    assert B.comparar(a1, a2, d1, d2) == {"inestables": ["baila"], "incompletas": ["suelta"], "regresiones": ["cae"], "dudosas": ["duda"], "mejoras": ["sube"], "iguales": ["fija"]}


def test_una_frase_inestable_antes_no_cuenta_como_regresion_aunque_caiga():
    assert B.comparar({"x": "mal"}, {"x": "bien"}, {"x": "mal"}, {"x": "mal"})["regresiones"] == []


PASADA = "Paso 2 frases…\n[23:09:12] Búsqueda «bien hecho»\nbien  Una frase.\n      ha elegido lo esperado: notas\nmal   Otra frase.\n      no ha usado notas: -\nBien: 1 · mal: 1\n"


def test_lee_las_notas_entre_las_lineas_del_registro():
    assert B.notas_de(PASADA) == {"Una frase.": "bien", "Otra frase.": "mal"}


def _archivos(tmp_path, *textos):
    rutas = []
    for i, texto in enumerate(textos):
        rutas.append(str(tmp_path / f"p{i}.txt"))
        Path(rutas[-1]).write_text(texto, encoding="utf-8")
    return rutas


def test_el_informe_dice_lo_ignorado_y_termina_con_error_si_hay_regresiones(tmp_path):
    otra = PASADA.replace("bien  Una", "mal   Una")
    cae = PASADA.replace("bien  Una", "mal   Una").replace("mal   Otra", "mal   Otra")
    salida = []
    assert B.principal(["--comparar", *_archivos(tmp_path, PASADA, otra, cae, cae)], salida.append) == 0
    texto = "\n".join(salida)
    assert "Ignoradas, porque ya cambian entre las dos pasadas de antes: 1" in texto and "  Una frase." in texto and "0 regresiones" in texto
    salida.clear()
    assert B.principal(["--comparar", *_archivos(tmp_path, PASADA, PASADA, cae, cae)], salida.append) == 1
    assert "Regresiones: bien antes y mal en las dos de después: 1" in salida[-3] or any("Regresiones" in s and ": 1" in s for s in salida)


def test_comparar_con_mal_uso_lo_dice(tmp_path):
    salida = []
    assert B.principal(["--comparar", "uno"], salida.append) == 2
    assert B.principal(["--comparar", *_archivos(tmp_path, "", PASADA, PASADA, PASADA)], salida.append) == 2 and "ninguna frase" in salida[-1]
    assert B.principal(["--comparar", "/no/existe", "b", "c", "d"], salida.append) == 2


def test_la_pasada_real_se_registra_como_medida(monkeypatch):
    from lina.nucleo import ia as IA
    from lina.nucleo import probar_ponme as PON
    vistos = []
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: vistos.append(IA._motivo_fijo[0]) or ([], ""))
    B.principal(["1"], lambda t: None)
    assert vistos == ["medida"] and IA._motivo_fijo[0] is None


GITHUB_ANTES = ["Voy a añadir el servidor de GitHub, ¿lo hago?", "Puedo añadir el servidor de GitHub: ¿lo hago?"]
GITHUB_DESPUES = ["Configura el token con lina clave github.", "Primero configura el token con lina clave github."]


def test_detecta_el_cambio_real_de_la_respuesta_de_github():
    motivos = B.cambio_de_forma(*GITHUB_ANTES, *GITHUB_DESPUES)
    assert "ya no: pide permiso" in motivos and "ya no: hace una pregunta" in motivos and "ahora: «lina clave»" in motivos


def test_redactar_lo_mismo_de_otra_forma_no_avisa():
    assert B.cambio_de_forma("Te he abierto el partido.", "El partido ya está abierto.", "Abierto el partido.", "Te abro el partido: abierto.") == []


def test_un_rasgo_que_ya_bailaba_antes_no_avisa():
    assert B.cambio_de_forma("Lo añado. ¿Lo hago?", "Lo añado sin más.", "Lo añado sin más.", "Lo añado ya mismo.") == []


def _con_dicho(dicho):
    return f"bien  Conéctate a GitHub.\n      ha elegido lo esperado: mcp_servidores\n      dice: {dicho}\nBien: 1 · mal: 0\n"


def test_el_informe_avisa_aunque_la_nota_sea_la_misma_y_no_es_regresion(tmp_path):
    rutas = _archivos(tmp_path, *[_con_dicho(d) for d in GITHUB_ANTES + GITHUB_DESPUES])
    salida = []
    assert B.principal(["--comparar", *rutas], salida.append) == 0
    texto = "\n".join(salida)
    assert "Cambian de forma de responder, aunque la nota sea la misma: 1" in texto and "¿lo hago?" in texto and "lina clave github" in texto


def test_con_pasadas_antiguas_dice_que_no_compara_respuestas(tmp_path):
    salida = []
    B.principal(["--comparar", *_archivos(tmp_path, PASADA, PASADA, PASADA, PASADA)], salida.append)
    assert any("no traen lo que dijo Lina" in s for s in salida)


def test_la_pasada_imprime_lo_que_dice_en_una_linea(monkeypatch):
    from lina.nucleo import probar_ponme as PON
    monkeypatch.setattr(PON, "_asistente", lambda: (MagicMock(), MagicMock(), []))
    monkeypatch.setattr(B, "pasar", lambda caso, *a: ([], "Una\nrespuesta"))
    salida = []
    B.principal(["1"], salida.append)
    assert B.dichos_de("\n".join(salida) + "\n") == {B.CASOS[0].frase: "Una respuesta"}
