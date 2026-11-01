# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina fuentes medir`: la tanda con las etiquetas revisadas, cómo se clasifica cada respuesta, el criterio de A11 y que sin --lanzar no se llama a la IA.
Con un modelo simulado: estas pruebas no llaman a la IA ni van a la red."""
import json
import time
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
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "medida.jsonl")
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


# ---------------------------------------------------------------- --grupos, --variante y --comprobar
def _respuestas():
    pedidas = []

    def preguntar(frase, juego):
        pedidas.append(frase)
        return _perfecto(frase, juego)
    return preguntar, pedidas


def test_grupos_solo_mide_esos_y_no_decide(archivo):
    preguntar, pedidas = _respuestas()
    salida = []
    assert M.principal(["--grupos", "C,D", "--lanzar"], salida.append, preguntar, archivo, lambda s: None) == 0
    assert len(pedidas) == len(M.casos({"C", "D"})) * M.REPETICIONES == 144
    assert {r["grupo"] for r in M.leer(archivo)} == {"C", "D"}
    texto = "\n".join(salida)
    assert "Resultado parcial" in texto and "Cumple el límite" in texto and "Decisión:" not in texto


def test_grupos_rellena_lo_que_falta_sin_repetir(archivo):
    M.principal(["--grupos", "F", "--lanzar"], lambda t: None, _respuestas()[0], archivo, lambda s: None)
    preguntar, pedidas = _respuestas()
    M.principal(["--grupos", "F,E", "--lanzar"], lambda t: None, preguntar, archivo, lambda s: None)
    assert len(pedidas) == len(M.casos({"E"})) * M.REPETICIONES


def test_cada_variante_tiene_su_archivo_y_la_descripcion_es_otra(archivo):
    assert M.ruta("base") == M.ARCHIVO and M.ruta("r1") != M.ruta("base")
    con = F.declaracion_usar_fuente(M.FUENTES, F.DESCRIPCION_R1)["description"]
    assert con.startswith("Busca en una web") and "Si dudas, no la uses" in con and "f2: " in con
    assert F.declaracion_usar_fuente(M.FUENTES)["description"].startswith(F.DESCRIPCION_BASE)


@pytest.mark.parametrize("args", [["--grupos"], ["--grupos", "Z"], ["--variante", "r9"], ["--otra"], ["--comprobar", "--grupos", "C"]])
def test_argumentos_malos_no_lanzan_nada(archivo, args):
    salida = []
    assert M.principal(args + ["--lanzar"], salida.append, MagicMock(side_effect=AssertionError), archivo, lambda s: None) == 2
    assert "Uso:" in salida[0]


def _guardados(archivo, filas):
    with open(archivo, "w", encoding="utf-8") as f:
        for grupo, frase, hizo in filas:
            for v in range(M.REPETICIONES):
                f.write(json.dumps({"grupo": grupo, "frase": frase, "juego": False, "vuelta": v, "hizo": hizo}, ensure_ascii=False) + "\n")


BUENA = M.GRUPOS["A"][2][0]
MALA = M.GRUPOS["C"][2][0]


def test_comprobar_rechaza_lo_que_no_encaja_y_guarda_veredictos(archivo):
    _guardados(archivo, [("A", BUENA, "f1"), ("C", MALA, "f1"), ("C", M.GRUPOS["C"][2][1], "buscar_web")])
    pedidas = []

    def consultar(tema, frase):
        pedidas.append((tema, frase))
        return frase == BUENA
    salida = []
    assert M.principal(["--comprobar", "--lanzar"], salida.append, None, archivo, lambda s: None, consultar) == 0
    assert len(pedidas) == 2 * M.REPETICIONES and all(t == M.FUENTES[0]["tema"] for t, _ in pedidas)
    finales = M.resumen_r3(M.leer(archivo), M.leer_r3(archivo.with_name(f"{archivo.stem}_r3.jsonl")))
    assert (finales["bien_rechazadas"], finales["mal_rechazadas"], finales["faltan"]) == (M.REPETICIONES, 0, 0)
    assert M.resumir(finales["finales"])["graves"] == 0
    assert "Decisión con R3" in "\n".join(salida)
    assert M.leer(archivo)[0]["hizo"] == "f1"                                 # lo medido no se reescribe


def test_rechazar_uno_bueno_cuenta_como_no_la_usa(archivo):
    _guardados(archivo, [("A", BUENA, "f1")])
    veredictos = {(BUENA, "f1", v): False for v in range(M.REPETICIONES)}
    h = M.resumen_r3(M.leer(archivo), veredictos)
    r = M.resumir(h["finales"])
    assert h["mal_rechazadas"] == 3 and r["no_la_usa"] == 3 and r["rechazadas"] == 3
    assert M.decision_r3(r) == "r3_rechaza"


def test_criterio_r3():
    base = {"total": 100, "graves": 0, "juego_total": 50, "juego_graves": 0, "debian": 100, "no_la_usa": 10}
    assert M.decision_r3(base) == "r3_si"
    assert M.decision_r3({**base, "no_la_usa": 11}) == "r3_rechaza"
    assert M.decision_r3({**base, "graves": 3}) == "r3_no"
    assert M.decision_r3({**base, "juego_graves": 2}) == "r3_no"


def test_comprobar_cada_vuelta_usa_su_veredicto_y_avisa_de_los_discordantes(archivo):
    _guardados(archivo, [("C", MALA, "f1")])
    h = M.resumen_r3(M.leer(archivo), {(MALA, "f1", 0): True, (MALA, "f1", 1): False, (MALA, "f1", 2): False})
    assert [r["hizo"] for r in h["finales"]] == ["f1", "rechazada", "rechazada"]
    assert h["discordantes"] == [(MALA, "f1")]


def test_comprobar_sigue_donde_quedo_y_para_con_el_cupo(archivo):
    _guardados(archivo, [("A", BUENA, "f1")])
    respuestas = iter([True, PROV.ErrorIA("cuota", 429, "sin cupo")])
    assert M.principal(["--comprobar", "--lanzar"], lambda t: None, None, archivo, lambda s: None, lambda t, f: next(respuestas)) == 3
    pedidas = []
    consultar = lambda t, f: pedidas.append(f) or True                       # noqa: E731
    assert M.principal(["--comprobar", "--lanzar"], lambda t: None, None, archivo, lambda s: None, consultar) == 0
    assert len(pedidas) == M.REPETICIONES - 1


def test_comprobar_sin_lanzar_no_llama(archivo):
    _guardados(archivo, [("A", BUENA, "f1")])
    salida = []
    consultar = MagicMock(side_effect=AssertionError("no debía llamar"))
    assert M.principal(["--comprobar"], salida.append, None, archivo, lambda s: None, consultar) == 0
    assert "0 de 3" in salida[0]


def test_el_prompt_de_comprobar_solo_lleva_tema_y_pregunta():
    assert F.contenido_tema("t", "p") == "<tema>t</tema>\n<pregunta>p</pregunta>"
    assert set(F.ESQUEMA_TEMA["properties"]) == {"decision"}


@pytest.mark.parametrize("texto, esperado", [('{"decision":"encaja"}', True), ('```json\n{"decision":"encaja"}\n```', True), ('{"decision":"no_encaja"}', False), ("ilegible", False)])
def test_la_consulta_de_verdad_usa_la_clave_gratuita_el_modelo_ligero_y_solo_tema_y_pregunta(monkeypatch, texto, esperado):
    from lina.nucleo import claves as CL
    from lina.nucleo import ia as IA
    from lina.nucleo import ia_activa as IAC
    vistos = {}

    def turno(proveedor, clave, modelo, sistema, mensajes, **k):
        vistos.update(clave=clave, modelo=modelo, sistema=sistema, mensajes=mensajes, **k)
        return PROV.Respuesta(texto, [], {}, modelo, None)
    ia = MagicMock()
    ia.nombre = "gemini"
    monkeypatch.setattr(IAC, "actual", lambda *a: ia)
    monkeypatch.setattr(IAC, "modelos", lambda *a: ["ligero", "otro"])
    monkeypatch.setattr(CL, "obtener", lambda nombre, *a: "gratuita" if nombre == "gemini" else None)
    monkeypatch.setattr(IA, "_turno_medido", turno)
    consultar, _ = M._consultar_de_verdad()
    assert consultar("el tema", "la pregunta") is esperado
    assert (vistos["clave"], vistos["modelo"]) == ("gratuita", "ligero") and "herramientas" not in vistos
    assert vistos["sistema"] == F.PROMPT_TEMA and vistos["mensajes"] == [{"rol": "user", "texto": "<tema>el tema</tema>\n<pregunta>la pregunta</pregunta>"}]


# ---------------------------------------------------------------- --tiempos (F3a)
def _t(seg1, res1="ok", seg2=None, res2=None):
    return {"clave": "pago", "seg1": seg1, "res1": res1, "seg2": seg2, "res2": res2}


def test_el_reintento_solo_sale_si_la_primera_tarda():
    assert M.cronometrar(lambda t, f: True, "t", "f", reintento=1)["seg2"] is None
    llamadas = []

    def lenta(t, f):
        llamadas.append(1)
        if len(llamadas) == 1:
            time.sleep(0.05)
        return True
    r = M.cronometrar(lenta, "t", "f", reintento=0.01)
    assert len(llamadas) == 2 and r["res2"] == "ok" and r["seg1"] >= 0.05 > r["seg2"]


@pytest.mark.parametrize("registro, a, c, b", [(_t(1), False, False, False), (_t(3), False, True, False), (_t(3, seg2=1, res2="ok"), False, False, False), (_t(5), True, True, False),
                                               (_t(5, seg2=1, res2="ok"), True, False, False), (_t(12, "red", 12, "red"), True, True, True), (_t(0.5, "servidor"), True, True, True)])
def test_que_habria_hecho_cada_politica(registro, a, c, b):
    assert (M.fallaria(registro, "A"), M.fallaria(registro, "C"), M.fallaria(registro, "B")) == (a, c, b)


def _resumen(fallos_a, fallos_c=None, fallos_b=None, n=100):
    return {"n": n, "fallos": {"A": fallos_a, "C": fallos_a if fallos_c is None else fallos_c, "B": fallos_a if fallos_b is None else fallos_b}}


@pytest.mark.parametrize("gratuita, pago, esperado", [
    (_resumen(.19), _resumen(.01), ("pago_primero", "A")),
    (_resumen(.19), _resumen(.05, .01), ("pago_primero", "C")),
    (_resumen(.01), _resumen(.01), ("sin_rafaga", "A")),
    (_resumen(.19), _resumen(.05), ("pago_justo", "A")),
    (_resumen(.05), _resumen(.19), ("gratuita_justa", "A")),
    (_resumen(.19), _resumen(.19), ("medida_larga", None)),
    (_resumen(.19, n=99), _resumen(.01), None)])
def test_criterio_de_tiempos(gratuita, pago, esperado):
    assert M.decision_tiempos(gratuita, pago) == esperado


def test_tiempos_guarda_solo_numeros_sigue_donde_quedo_y_no_repite(archivo, monkeypatch):
    _guardados(archivo, [("A", BUENA, "f1")])
    monkeypatch.setattr(M, "LLAMADAS_TIEMPOS", 4)
    destino = archivo.with_name("tiempos.jsonl")
    respuestas = iter([True, True, PROV.ErrorIA("cuota", 429, "sin cupo")])
    assert M.principal(["--tiempos", "--clave", "pago", "--lanzar"], lambda t: None, None, destino, lambda s: None, lambda t, f: next(respuestas)) == 3
    assert len(M.leer_tiempos(destino, "pago")) == 2 and BUENA not in destino.read_text(encoding="utf-8")
    pedidas = []
    assert M.principal(["--tiempos", "--clave", "pago", "--lanzar"], lambda t: None, None, destino, lambda s: None, lambda t, f: pedidas.append(f) or True) == 0
    assert len(pedidas) == 2 and len(M.leer_tiempos(destino, "gratuita")) == 0


@pytest.mark.parametrize("args", [["--tiempos"], ["--tiempos", "--clave", "otra"], ["--tiempos", "--clave"], ["--tiempos", "--clave", "pago", "--grupos", "C"]])
def test_tiempos_exige_decir_la_clave(archivo, args):
    salida = []
    assert M.principal(args + ["--lanzar"], salida.append, None, archivo, lambda s: None, MagicMock(side_effect=AssertionError)) == 2
    assert "Uso:" in salida[0]


def test_tiempos_sin_lanzar_no_llama(archivo):
    salida = []
    assert M.principal(["--tiempos", "--clave", "pago"], salida.append, None, archivo, lambda s: None, MagicMock(side_effect=AssertionError)) == 0
    assert "100 llamadas" in salida[0]


def test_la_clave_de_pago_apunta_el_gasto_y_respeta_el_tope(monkeypatch):
    from lina.nucleo import claves as CL
    from lina.nucleo import ia as IA
    from lina.nucleo import ia_activa as IAC
    from lina.nucleo import presupuesto as PRES
    usadas, gasto = [], []
    ia = MagicMock()
    ia.nombre = "gemini"
    monkeypatch.setattr(IAC, "actual", lambda *a: ia)
    monkeypatch.setattr(IAC, "modelos", lambda *a: ["ligero"])
    monkeypatch.setattr(CL, "obtener", lambda nombre, *a: {"gemini": "gratis", "gemini_pago": "de-pago"}.get(nombre))
    monkeypatch.setattr(PRES, "configurar_claves", lambda g, p: None)
    monkeypatch.setattr(PRES, "registrar", lambda *a: gasto.append(a))
    disponible = [True]
    monkeypatch.setattr(PRES, "pago_disponible", lambda: disponible[0])
    monkeypatch.setattr(IA, "_turno_medido", lambda p, clave, *a, **k: usadas.append((clave, k["timeout"])) or PROV.Respuesta('{"decision":"encaja"}', [], {}, "ligero", None))
    consultar, _ = M._consultar_de_verdad("gemini_pago", M.ESPERA_MAX)
    assert consultar("t", "f") is True and usadas == [("de-pago", M.ESPERA_MAX)] and len(gasto) == 1
    disponible[0] = False
    assert consultar("t", "f").tipo == "cuota" and len(usadas) == 1             # con el tope alcanzado no llama
