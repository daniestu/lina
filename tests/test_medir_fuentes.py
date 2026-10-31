# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina fuentes medir`: la tanda con las etiquetas revisadas, cómo se clasifica cada respuesta, el criterio de A11 y que sin --lanzar no se llama a la IA.
Con un modelo simulado: estas pruebas no llaman a la IA ni van a la red."""
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import fuentes as F
from lina.nucleo import medir_fuentes as M
from lina.nucleo import proveedores as PROV
from lina.nucleo import tiempos as TIE


@pytest.fixture
def archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(F, "ARCHIVO", tmp_path / "fuentes.json")
    return tmp_path / "medida.jsonl"


def _usa(ident):
    return PROV.Respuesta(llamadas=[PROV.Llamada("usar_fuente", {"id": ident, "consulta": "x"})])


BUSCA = PROV.Respuesta(llamadas=[PROV.Llamada("buscar_web", {"consulta": "x"})])
RESPONDE = PROV.Respuesta(texto="Pues mira…")


def _perfecto(frase, juego):
    for grupo, (_, esperado, frases) in M.GRUPOS.items():
        if frase in frases:
            return _usa(esperado) if esperado else BUSCA


def _registros(modelo):
    return [{"grupo": g, "frase": f, "juego": j, "vuelta": v, "hizo": M.clasificar(modelo(f, j))} for g, f, j in M.casos() for v in range(M.REPETICIONES)]


def test_la_tanda_es_la_revisada():
    assert {g: len(v[2]) for g, v in M.GRUPOS.items()} == {"A": 10, "B": 17, "W": 5, "C": 19, "D": 10, "E": 10, "F": 4, "gris": 5}
    assert len(M.casos()) == 121 and sum(1 for c in M.casos() if c[2]) == 41
    gris = M.GRUPOS["gris"][2]
    for frase in ("¿Cómo convierto el cloro en sal?", "¿Cómo se fabrica ferrita magnetizada?", "¿Cómo mezclo dos minerales en el juego para obtener otro?",
                  "¿Para qué sirve el carbono condensado?", "¿Cómo mejoro la Golondrina a su versión superior?"):
        assert frase in gris and not any(frase in M.GRUPOS[g][2] for g in M.GRUPOS if g != "gris")
    assert M.GRUPOS["W"][1] == "f1" and "¿Cómo refi no el ferrito?" in M.GRUPOS["W"][2] and "¿Cómo refino el ferrico?" in M.GRUPOS["W"][2]
    assert "¿Cómo refino el ferrito?" in M.GRUPOS["B"][2] and "¿Dónde consigo ferrito?" in M.GRUPOS["C"][2]
    frases = [f for g, v in M.GRUPOS.items() for f in v[2]]
    assert len(frases) == len(set(frases))


@pytest.mark.parametrize("respuesta, hizo", [(_usa("f1"), "f1"), (_usa("f2"), "f2"), (_usa("f9"), "id_malo"), (BUSCA, "buscar_web"), (RESPONDE, "responde"),
                                             (PROV.Respuesta(llamadas=[PROV.Llamada("abrir_app", {})]), "otra")])
def test_clasificar(respuesta, hizo):
    assert M.clasificar(respuesta) == hizo


def test_un_modelo_perfecto_activa_la_herramienta_sola():
    r = M.resumir(_registros(_perfecto))
    assert r["graves"] == r["no_la_usa"] == 0 and M.decision(r) == "sola"
    assert r["total"] == (121 - 5 - 5) * M.REPETICIONES                         # los grises (con y sin juego) no cuentan


def _con_fallos(graves=(), no_usa=()):
    def modelo(frase, juego):
        return _usa("f1") if frase in graves else RESPONDE if frase in no_usa else _perfecto(frase, juego)
    return M.resumir(_registros(modelo))


def test_usarla_de_mas_es_grave_y_pide_r3():
    r = _con_fallos(graves=["¿Dónde consigo ferrito?", "¿Cómo gano dinero fácil en No Man's Sky?"])
    assert r["de_mas"] == 12 and r["juego_graves"] == 12 and M.decision(r) == "R3"


def test_dentro_del_mismo_juego_el_criterio_es_aparte():
    r = _con_fallos(graves=["¿Dónde consigo ferrito?"])                         # 6 de 333 (1,8 %) en total, pero 6 de 114 (5,3 %) en el mismo juego
    assert r["graves"] / r["total"] <= M.MAX_GRAVE and M.decision(r) == "R3"


def test_no_usarla_demasiado_pide_r2_y_dice_que_hizo():
    r = _con_fallos(no_usa=M.GRUPOS["W"][2] + M.GRUPOS["B"][2][:4])
    assert r["memoria"] == r["no_la_usa"] and r["no_la_usa"] / r["debian"] > M.MAX_NO_LA_USA and r["graves"] == 0 and M.decision(r) == "R2"


def test_el_id_equivocado_es_grave():
    r = _con_fallos(graves=M.GRUPOS["F"][2][:1])
    assert r["id_mal"] == 3 and r["graves"] == 3


def test_los_grises_se_ven_pero_no_cuentan():
    r = _con_fallos(graves=M.GRUPOS["gris"][2])
    assert r["graves"] == 0 and M.decision(r) == "sola" and r["gris"]["¿Cómo convierto el cloro en sal?"]["f1"] == 6
    salida = []
    M.informe(_registros(_perfecto), salida.append)
    assert any("Ambiguas" in t for t in salida)


def test_a_medias_no_se_decide():
    assert M.decision(M.resumir(_registros(_perfecto)[:50])) is None


def test_sin_lanzar_no_llama_a_nada(archivo):
    salida = []
    assert M.principal([], salida.append, preguntar=MagicMock(side_effect=AssertionError("no debía llamar a la IA")), archivo=archivo) == 0
    assert "363 llamadas" in salida[0] and "--lanzar" in salida[0] and not archivo.exists()
    assert M.principal(["otra"], salida.append, archivo=archivo) == 2


def test_medir_de_principio_a_fin_y_no_toca_las_fuentes_del_usuario(archivo):
    salida = []
    assert M.principal(["--lanzar"], salida.append, preguntar=_perfecto, archivo=archivo, dormir=lambda s: None) == 0
    assert len(M.leer(archivo)) == 363 and any("se activa usar_fuente sola" in t for t in salida) and not F.ARCHIVO.exists()


def test_si_se_acaba_el_cupo_para_y_continua_donde_iba(archivo):
    llamadas = []

    def con_cupo(frase, juego):
        llamadas.append(frase)
        return PROV.ErrorIA("cuota", 429, "demasiadas") if len(llamadas) > 10 else _perfecto(frase, juego)
    salida = []
    assert M.principal(["--lanzar"], salida.append, preguntar=con_cupo, archivo=archivo, dormir=lambda s: None) == 3
    assert len(M.leer(archivo)) == 10 and any("Parada" in t for t in salida)
    hechas = []
    assert M.principal(["--lanzar"], salida.append, preguntar=lambda f, j: hechas.append(f) or _perfecto(f, j), archivo=archivo, dormir=lambda s: None) == 0
    assert len(hechas) == 353 and len(M.leer(archivo)) == 363


def test_un_fallo_suelto_no_se_apunta_y_se_repite(archivo):
    errores = [PROV.ErrorIA("servidor", 503, "ocupado")]

    def modelo(frase, juego):
        return errores.pop() if errores else _perfecto(frase, juego)
    assert M.principal(["--lanzar"], lambda t: None, preguntar=modelo, archivo=archivo, dormir=lambda s: None) == 0
    assert len(M.leer(archivo)) == 362


def test_solo_usa_la_clave_gratuita_y_se_apunta_como_medida(monkeypatch):
    from lina.nucleo import claves as CL
    from lina.nucleo import ia_activa as IAC
    pedidas = []
    monkeypatch.setattr(CL, "obtener", lambda n, *a: pedidas.append(n) or "clave")
    ia = MagicMock(nombre="gemini")
    monkeypatch.setattr(IAC, "actual", lambda *a: ia)
    monkeypatch.setattr(IAC, "modelos", lambda m, *a: ["gemini-flash-lite-latest"])
    preguntar, motivo = M._preguntar_de_verdad()
    assert preguntar and motivo == "" and pedidas == ["gemini"]
    from lina.nucleo import ia as IA
    vistas = []
    monkeypatch.setattr(IA, "_turno_medido", lambda prov, clave, modelo, sistema, mensajes, **k: vistas.append((clave, modelo, mensajes, k, IA._motivo_actual.get())) or RESPONDE)
    preguntar("¿Cómo refino el ferrito?", True)
    clave, modelo, mensajes, k, motivo = vistas[0]
    assert (clave, modelo, motivo) == ("clave", "gemini-flash-lite-latest", "medida") and "videojuego «No Man's Sky»" in mensajes[0]["texto"]
    assert k["herramientas"][0]["name"] == "usar_fuente" and k["nivel"] == "minimal" and "medida" in TIE.MOTIVOS


def test_sin_gemini_no_mide(monkeypatch):
    from lina.nucleo import ia_activa as IAC
    monkeypatch.setattr(IAC, "actual", lambda *a: MagicMock(nombre="openai"))
    assert M._preguntar_de_verdad()[0] is None


def test_la_declaracion_lleva_los_temas_y_solo_ids_de_la_lista():
    d = F.declaracion_usar_fuente(M.FUENTES)
    assert d["name"] == "usar_fuente" and "f1: recetas de refinería de No Man's Sky" in d["description"]
    assert d["parameters"]["properties"]["id"]["enum"] == ["f1", "f2"] and "aunque sea del mismo juego" in d["description"]


def test_usar_fuente_no_se_le_da_a_la_ia_al_responder():
    from lina.nucleo import herramientas as H
    from pathlib import Path
    assert "usar_fuente" not in {d["name"] for d in H.DECLARACIONES}
    assert "usar_fuente" not in Path(H.__file__).with_name("asistente.py").read_text(encoding="utf-8")
