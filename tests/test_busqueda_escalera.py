# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La escalera de ia.busqueda = auto (busqueda.py): Gemini de pago en consulta aparte, Tavily, DuckDuckGo solo si lo enciendes, Wikipedia y wikis de juegos,
y el motivo de verdad si nada da resultados. Ni red ni llavero: todo con respuestas falsas y el estado en carpetas temporales (conftest)."""
import time
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import busqueda as BUS
from lina.nucleo import claves as CL
from lina.nucleo import ia as IA
from lina.nucleo import presupuesto as PRES
from lina.nucleo import rutas as RUT

GROUNDING = {"candidates": [{"content": {"parts": [{"text": "La poción se hace con ectoplasma. Lleva también azulejo."}]},
                             "groundingMetadata": {"webSearchQueries": ["pocion invisibilidad skyrim"],
                                                   "groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/a", "title": "uesp.net"}},
                                                                       {"web": {"uri": "https://vertexaisearch.cloud.google.com/b", "title": "elderscrolls.fandom.com"}}],
                                                   "groundingSupports": [{"segment": {"text": "La poción se hace con ectoplasma."}, "groundingChunkIndices": [0, 1]},
                                                                         {"segment": {"text": "Lleva también azulejo."}, "groundingChunkIndices": [1]}]}}],
             "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}, "modelVersion": "gemini-3.5-flash-lite"}


def respuesta(codigo=200, cuerpo=None):
    r = MagicMock(ok=codigo < 400, status_code=codigo)
    r.json.return_value = cuerpo if cuerpo is not None else {}
    return r


ERROR_SIN_DETALLE = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"@type": "type.googleapis.com/google.rpc.Help"}]}}
ERROR_DE_RITMO = {"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "PerMinute"}]},
                                                     {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "9s"}]}}


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """entorno(pago=, gratis=, tavily=, reserva=): las claves y el ajuste de DuckDuckGo; la red, prohibida salvo lo que cada prueba ponga."""
    monkeypatch.setattr(RUT, "ESTADO", tmp_path / "estado")             # los bloqueos de Google y los avisos van a un archivo: cada prueba el suyo
    BUS._cache.clear()
    BUS._pausa_google.clear()
    BUS._ultima_duckduckgo[0] = 0.0
    AVB.descartar()
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(IA, "modo_busqueda", lambda: "auto")
    monkeypatch.setattr(PRES, "registrar", MagicMock())
    monkeypatch.setattr(PRES, "registrar_busquedas_google", MagicMock())

    def poner(pago="", gratis="", tavily="", reserva=False):
        monkeypatch.setattr(PRES, "clave_de_pago_con_saldo", lambda: pago)
        monkeypatch.setattr(CL, "obtener", lambda n: {"tavily": tavily, "gemini": gratis, "gemini_pago": pago}.get(n, ""))
        monkeypatch.setattr(IA, "hay_reserva", lambda: reserva)
    poner()
    return poner


# ---------------------------------------------------------------- Gemini: consulta aparte, forzada, y el 429 sin detalle
def test_google_va_aparte_forzado_y_cuenta_el_gasto(entorno):
    entorno(pago="CLAVE-PAGO")
    post = MagicMock(return_value=respuesta(200, GROUNDING))
    resultados, motivo = BUS.resultados_google("poción de invisibilidad Skyrim", post=post)
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["tools"] == [{"google_search": {}}]                       # solo la búsqueda: con nuestras funciones daba 400
    assert cuerpo["contents"][0]["parts"][0]["text"].startswith("Busca en internet: poción")     # sin esto contestaba de memoria
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "CLAVE-PAGO" and motivo == ""
    assert [r["dominio"] for r in resultados] == ["uesp.net", "elderscrolls.fandom.com"]
    assert resultados[1]["content"] == "La poción se hace con ectoplasma. Lleva también azulejo."
    PRES.registrar.assert_called_once()
    PRES.registrar_busquedas_google.assert_called_once_with("CLAVE-PAGO", 1)


def test_el_texto_para_la_ia_dice_el_dominio_de_verdad_y_no_el_enlace_de_paso(entorno):
    texto = IA._resultados_como_texto(BUS.resultados_de_google(GROUNDING))
    assert "(uesp.net)" in texto and "(vertexaisearch" not in texto


def test_con_dominio_solo_quedan_las_fuentes_de_esa_web(entorno):
    assert [r["dominio"] for r in BUS.resultados_de_google(GROUNDING, "uesp.net")] == ["uesp.net"]


def test_429_sin_detalle_con_la_gratuita_no_se_vuelve_a_probar_hasta_cambiar_la_clave(entorno):
    entorno(gratis="GRATIS-1")
    post = MagicMock(return_value=respuesta(429, ERROR_SIN_DETALLE))
    assert BUS.resultados_google("x", post=post) == ([], BUS.T(BUS.M_GOOGLE_GRATIS))
    assert BUS.resultados_google("y", post=post)[0] == [] and post.call_count == 1       # ni un intento más, aunque Lina se reinicie (va a un archivo)
    b = BUS.bloqueo("GRATIS-1")
    assert b["tipo"] == "gratis" and b["hasta"] is None
    entorno(gratis="GRATIS-NUEVA")                                          # cambiar la clave de Gemini lo levanta
    post2 = MagicMock(return_value=respuesta(200, GROUNDING))
    assert BUS.resultados_google("z", post=post2)[0] and post2.call_count == 1


def test_429_sin_detalle_con_la_de_pago_se_dice_tal_cual_y_vuelve_manana(entorno):
    entorno(pago="PAGO-1")
    post = MagicMock(return_value=respuesta(429, ERROR_SIN_DETALLE))
    resultados, motivo = BUS.resultados_google("x", post=post)
    assert resultados == [] and "tope de gasto" in motivo and "429 sin detalle" in motivo
    b = BUS.bloqueo("PAGO-1")
    assert b["tipo"] == "pago" and b["hasta"] == IA._manana()
    assert BUS.bloqueo("PAGO-1", ahora=IA._manana() + 1) is None
    assert BUS.estado_google() == [("pago", b["desde"], b["hasta"])]


def test_un_429_de_ritmo_no_bloquea_solo_pausa_lo_que_pide_google(entorno):
    entorno(gratis="GRATIS-1")
    ahora = 1_900_000_000.0
    assert BUS.resultados_google("x", post=MagicMock(return_value=respuesta(429, ERROR_DE_RITMO)), ahora=ahora)[0] == []
    assert BUS.bloqueo("GRATIS-1") is None
    assert BUS._pausa_google[BUS.huella("GRATIS-1")] == ahora + 9


def test_con_la_de_pago_bloqueada_se_prueba_la_gratuita(entorno):
    entorno(pago="PAGO-1", gratis="GRATIS-1")
    BUS._bloquear("PAGO-1", "pago")
    post = MagicMock(return_value=respuesta(200, GROUNDING))
    assert BUS.resultados_google("x", post=post)[0]
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "GRATIS-1"


def test_sin_claves_de_gemini_ni_lo_intenta(entorno):
    assert BUS.resultados_google("x", post=MagicMock(side_effect=AssertionError)) == ([], "")


def test_las_busquedas_de_google_de_pago_cuestan_pasadas_las_gratuitas(monkeypatch, tmp_path):
    monkeypatch.setattr(PRES, "ARCHIVO_GASTO", tmp_path / "gasto.json")
    PRES.configurar_claves("GRATIS", "PAGO")
    datos = PRES._nuevo(time.strftime("%Y-%m"))
    datos["busquedas_google_pago"] = PRES.BUSQUEDAS_GOOGLE_GRATIS_MES - 1
    PRES._guardar(datos)
    PRES.registrar_busquedas_google("PAGO", 3)                              # 1 gratis y 2 cobradas
    d = PRES._cargar()
    assert d["busquedas_google_pago"] == PRES.BUSQUEDAS_GOOGLE_GRATIS_MES + 2
    assert d["usd"] == pytest.approx(2 * PRES.USD_POR_BUSQUEDA_GOOGLE) and "google_search" in d["por_modelo"]
    PRES.registrar_busquedas_google("GRATIS", 5)
    assert PRES._cargar()["busquedas_google_gratis"] == 5 and PRES._cargar()["usd"] == pytest.approx(2 * PRES.USD_POR_BUSQUEDA_GOOGLE)
    PRES.configurar_claves("", "")


# ---------------------------------------------------------------- la escalera
def test_orden_google_y_luego_tavily(entorno, monkeypatch):
    entorno(gratis="GRATIS-1", tavily="tvly-x")
    BUS._bloquear("GRATIS-1", "gratis")
    monkeypatch.setattr(IA, "resultados_tavily", MagicMock(return_value=[{"title": "T", "url": "https://t.es/a", "content": "c"}]))
    res = BUS.buscar("precio steam deck")
    assert res.escalon == "tavily" and res.resultados[0]["url"] == "https://t.es/a"
    IA.resultados_tavily.assert_called_once_with("precio steam deck", None, reserva=False, comprobar_modo=False)


def test_sin_tavily_ni_pago_acaba_en_las_wikis_y_lo_apunta_la_primera_vez(entorno, monkeypatch):
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: ([{"title": "Poción", "url": "https://elderscrolls.fandom.com/es/wiki/P", "dominio": "elderscrolls.fandom.com",
                                                                  "content": "x"}], ""))
    res = BUS.buscar("poción de invisibilidad Skyrim")
    assert res.escalon == "wiki" and res.sin_tavily and AVB.PRIMERA_WIKI in AVB._pendientes
    assert BUS.T(BUS.M_SIN_TAVILY) in res.motivos


def test_duckduckgo_apagado_de_fabrica_ni_se_llama(entorno, monkeypatch):
    monkeypatch.setattr(IA, "resultados_reserva", MagicMock(side_effect=AssertionError("apagado: no se llama")))
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: ([], BUS.T(BUS.M_WIKI_NADA)))
    res = BUS.buscar("noticias de hoy")
    assert res.resultados == [] and not any("DuckDuckGo" in m for m in res.motivos)


def test_duckduckgo_encendido_como_mucho_una_vez_cada_intervalo_y_sin_esperar(entorno, monkeypatch):
    entorno(reserva=True)
    ddg = MagicMock(return_value="La búsqueda web no está disponible ahora mismo.")
    monkeypatch.setattr(IA, "resultados_reserva", ddg)
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: ([], BUS.T(BUS.M_WIKI_NADA)))
    ahora = 1_900_000_000.0
    primera = BUS.buscar("uno", ahora=ahora)
    segunda = BUS.buscar("dos", ahora=ahora + 5)
    assert ddg.call_count == 1 and BUS.T(BUS.M_DUCKDUCKGO) in primera.motivos and BUS.T(BUS.M_DUCKDUCKGO_PRONTO) in segunda.motivos
    BUS.buscar("tres", ahora=ahora + BUS.INTERVALO_DUCKDUCKGO_SEG)
    assert ddg.call_count == 2


def test_lo_encontrado_se_guarda_poco_rato(entorno, monkeypatch):
    llamadas = []
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: (llamadas.append(consulta), ([{"title": "A", "url": "https://es.wikipedia.org/wiki/A", "content": ""}], ""))[1])
    ahora = 1_900_000_000.0
    BUS.buscar("Capital de Australia", ahora=ahora)
    BUS.buscar("capital de  australia", ahora=ahora + 60)
    assert len(llamadas) == 1
    assert 10 * 60 <= BUS.CACHE_SEG <= 15 * 60                              # partidos, precios y noticias: 10–15 min, no una hora
    BUS.buscar("capital de australia", ahora=ahora + BUS.CACHE_SEG + 1)
    assert len(llamadas) == 2


def test_si_nada_encuentra_no_se_guarda(entorno, monkeypatch):
    llamadas = []
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: (llamadas.append(1), ([], BUS.T(BUS.M_WIKI_NADA)))[1])
    BUS.buscar("x")
    BUS.buscar("x")
    assert len(llamadas) == 2


def test_con_google_solo_gemini_y_duckduckgo(entorno, monkeypatch):
    monkeypatch.setattr(IA, "resultados_tavily", MagicMock(side_effect=AssertionError("con google no se usa Tavily")))
    monkeypatch.setattr(BUS, "resultados_wiki", MagicMock(side_effect=AssertionError("con google no se usan las wikis")))
    res = BUS.buscar("x", modo="google")
    assert res.resultados == [] and res.motivos == [BUS.T(BUS.M_SIN_PAGO)]


# ---------------------------------------------------------------- lo que se dice si nada da resultados
def test_sin_resultados_la_ia_recibe_el_motivo_y_la_prohibicion(entorno, monkeypatch):
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: ([], BUS.T(BUS.M_WIKI_NADA)))
    texto = BUS.como_texto(BUS.buscar("calendario de LoL"))
    assert texto.startswith("NO SE HA PODIDO BUSCAR") and "no tienes clave de Tavily" in texto
    assert "NUNCA digas que no tienes acceso a internet" in texto and "clave gratuita de Tavily" in texto


def test_la_frase_del_codigo_da_el_motivo_y_sugiere_tavily(entorno, monkeypatch):
    entorno(gratis="GRATIS-1")
    BUS._bloquear("GRATIS-1", "gratis")
    monkeypatch.setattr(BUS, "resultados_wiki", lambda consulta: ([], BUS.T(BUS.M_WIKI_NADA)))
    frase = BUS.frase_de_fallo([BUS.buscar("x")])
    assert frase.startswith("No he podido buscarlo: no tienes clave de Tavily y Wikipedia") and "lina bienvenida" in frase
    assert "acceso a internet" not in frase and "Google" not in frase       # lo de la gratuita no se dice en voz: solo lo que el usuario puede arreglar


# ---------------------------------------------------------------- las wikis
@pytest.mark.parametrize("consulta, primera", [
    ("cómo se hace la poción de invisibilidad en Skyrim", "elderscrolls.fandom.com/es"),
    ("qué partidos de LoL hay esta semana", "lol.fandom.com"),
    ("Ahri build League of Legends", "leagueoflegends.fandom.com/es"),
    ("qué es un creeper en Minecraft", "es.minecraft.wiki"),
    ("capital de Australia", "es.wikipedia.org/w"),
])
def test_cada_juego_va_a_su_wiki_y_si_no_a_wikipedia(consulta, primera):
    orden = [w["api"] for w in BUS.wikis_para(consulta, "es")]
    assert orden[0] == primera and orden[-2:] == ["es.wikipedia.org/w", "en.wikipedia.org/w"]


def test_el_nombre_del_juego_va_entero():
    assert [w["api"] for w in BUS.wikis_para("lolita", "es")] == ["es.wikipedia.org/w", "en.wikipedia.org/w"]


def test_la_tabla_de_wikis_esta_bien_escrita():
    for w in BUS.wikis():
        assert w["nombres"] and any(i in w for i in ("es", "en"))
        for i in ("es", "en"):
            if i in w:
                assert w[i]["pagina"].startswith("https://" + w[i]["api"].split("/")[0]) and "/api.php" not in w[i]["api"]


def test_la_wiki_busca_sin_clave_con_un_agente_honesto_y_arma_el_enlace(entorno):
    pedidas = []

    def get(url, params, headers, timeout):
        pedidas.append((url, headers["User-Agent"]))
        encontrados = [] if "fandom.com/es" in url else [{"title": "Invisibility Potion", "snippet": "<span class=\"searchmatch\">Invisibility</span> potion"}]
        return respuesta(200, {"query": {"search": encontrados}})
    resultados, motivo = BUS.resultados_wiki("Skyrim invisibility potion", "es", get=get)
    assert [u for u, _ in pedidas] == ["https://elderscrolls.fandom.com/es/api.php", "https://elderscrolls.fandom.com/api.php"]
    assert all(a.startswith("Lina/") and "Mozilla" not in a for _, a in pedidas)
    assert resultados[0]["url"] == "https://elderscrolls.fandom.com/wiki/Invisibility_Potion" and resultados[0]["content"] == "Invisibility potion"
    assert resultados[0]["dominio"] == "elderscrolls.fandom.com" and motivo == ""


def test_sin_red_las_wikis_lo_dicen(entorno):
    def get(*a, **k):
        raise requests.ConnectionError("sin red")
    assert BUS.resultados_wiki("x", "es", get=get) == ([], BUS.T(BUS.M_WIKI_RED))


# ---------------------------------------------------------------- «búscalo igualmente»
@pytest.mark.parametrize("frase, si", [("búscalo igualmente", True), ("vale, búscalo en internet de todas formas", True), ("búscalo aunque sea", True),
                                       ("busca el archivo de ayer", False), ("búscalo", False), ("igualmente gracias", False)])
def test_buscar_igualmente(frase, si):
    assert BUS.pide_buscar_igualmente(frase) is si


def test_con_otro_proveedor_no_se_manda_su_clave_a_google(entorno, monkeypatch):
    """Con OpenAI o Anthropic, la clave «gratuita» del presupuesto es la de ese proveedor: a Google solo va la clave de Gemini guardada."""
    entorno()
    monkeypatch.setattr(PRES, "_claves", {"gratis": "sk-de-openai", "pago": ""})
    assert BUS._claves_google() == []
    entorno(gratis="GEMINI-1")
    assert BUS._claves_google() == [("GEMINI-1", "gratis")]


# ---------------------------------------------------------------- lo que se le pide a la wiki y en qué orden
@pytest.mark.parametrize("consulta, nombres, queda", [
    ("qué es un creeper en Minecraft", ["minecraft"], "creeper"),
    ("cuánto mide la torre Eiffel", [], "mide torre Eiffel"),
    ("de la", [], "de la"),                                                 # si no queda nada, la frase tal cual
])
def test_la_consulta_a_la_wiki_va_sin_palabras_vacias_ni_el_nombre_del_juego(consulta, nombres, queda):
    assert BUS.consulta_wiki(consulta, nombres) == queda


def test_los_titulos_que_dice_la_pregunta_van_primero(entorno):
    def get(url, params, headers, timeout):
        return respuesta(200, {"query": {"search": [{"title": "Biblioteca Nacional de Australia", "snippet": ""}, {"title": "Australia", "snippet": ""}]}})
    assert [r["title"] for r in BUS.resultados_wiki("capital de Australia", "es", get=get)[0]] == ["Australia", "Biblioteca Nacional de Australia"]


def test_la_pagina_de_la_wiki_se_pide_a_su_api(entorno):
    """Fandom da 403 a los programas que piden la página, no a su API."""
    pedidas = []

    def get(url, params, headers, timeout):
        pedidas.append((url, params["action"], params["page"]))
        return respuesta(200, {"parse": {"text": "<style>.x{}</style><p>Se hace con <b>ectoplasma</b>.</p><script>malo()</script>"}})
    p = BUS.pagina_wiki({"title": "Invisibilidad (Skyrim)", "url": "https://elderscrolls.fandom.com/es/wiki/I", "api": "elderscrolls.fandom.com/es"}, get=get)
    assert pedidas == [("https://elderscrolls.fandom.com/es/api.php", "parse", "Invisibilidad (Skyrim)")]
    assert p == {"url": "https://elderscrolls.fandom.com/es/wiki/I", "titulo": "Invisibilidad (Skyrim)", "texto": "Se hace con ectoplasma ."}


def test_sin_api_o_sin_red_no_hay_pagina(entorno):
    assert BUS.pagina_wiki({"title": "x", "url": "https://a.es/x"}) is None

    def get(*a, **k):
        raise requests.ConnectionError("sin red")
    assert BUS.pagina_wiki({"title": "x", "url": "https://a.es/x", "api": "a.es"}, get=get) is None
