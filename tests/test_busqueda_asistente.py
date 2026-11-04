# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El bloque C en el asistente: buscar_web pasa por la escalera de «auto» (y quien eligió tavily lo conserva), «búscalo igualmente» salta «ninguna» una vez,
Lina nunca dice «no tengo acceso a internet», buscar o leer la web con un comando se manda a sus herramientas, y los avisos de la primera vez. Sin red."""
import sys
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import aviso_busqueda as AVB
from lina.nucleo import busqueda as BUS
from lina.nucleo import herramientas as H
from lina.nucleo import ia as IA
from lina.nucleo import rutas as RUT

WIKI = BUS.Resultado(resultados=[{"title": "Poción", "url": "https://elderscrolls.fandom.com/es/wiki/P", "dominio": "elderscrolls.fandom.com", "content": "x"}],
                     escalon="wiki", motivos=["no tienes clave de Tavily"], sin_tavily=True)
NADA = BUS.Resultado(motivos=["no tienes clave de Tavily", "Wikipedia y las wikis de juegos no tienen nada sobre esto"], sin_tavily=True)


@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], duda=None, efecto_sin_comprobar=False)
    a.busquedas_turno, a.max_busquedas, a.busquedas_hechas, a.forzar_busqueda = 0, 2, [], False
    a.acciones_turno, a.pregunta_pura = [], "cómo se hace la poción de invisibilidad en Skyrim"
    a.leer_web = MagicMock(return_value="CONTENIDO DE LA PÁGINA (de fuera): ectoplasma y azulejo")
    monkeypatch.setattr(A, "modo_busqueda", lambda: "auto")
    monkeypatch.setattr(A, "buscar_tavily", MagicMock(side_effect=AssertionError("con auto no va por aquí")))
    a.A = A
    return a


def test_auto_pasa_por_la_escalera_y_lee_la_primera_pagina_de_la_wiki(lina, monkeypatch):
    buscar = MagicMock(return_value=WIKI)
    monkeypatch.setattr(BUS, "buscar", buscar)
    monkeypatch.setattr(BUS, "pagina_wiki", lambda r: {"url": r["url"], "titulo": "P", "texto": "ectoplasma"})
    r = lina._ejecutar_herramienta("buscar_web", {"consulta": "Skyrim invisibility potion"})
    buscar.assert_called_once_with("Skyrim invisibility potion", None, modo="auto", peticion="cómo se hace la poción de invisibilidad en Skyrim")
    lina.leer_web.assert_called_once_with({"url": "https://elderscrolls.fandom.com/es/wiki/P", "foco": "Skyrim invisibility potion"}, obstaculo=False,
                                          pagina={"url": "https://elderscrolls.fandom.com/es/wiki/P", "titulo": "P", "texto": "ectoplasma"})
    assert r.startswith("RESULTADOS DE BÚSQUEDA") and "ectoplasma" in r and lina.busquedas_hechas == [WIKI]
    lina.ejecutor.contaminar.assert_called_once_with("búsqueda web")


def test_quien_eligio_tavily_lo_conserva_tal_cual(lina, monkeypatch):
    monkeypatch.setattr(lina.A, "modo_busqueda", lambda: "tavily")
    monkeypatch.setattr(lina.A, "buscar_tavily", MagicMock(return_value="ok"))
    monkeypatch.setattr(BUS, "buscar", MagicMock(side_effect=AssertionError("con tavily no hay escalera")))
    assert lina._ejecutar_herramienta("buscar_web", {"consulta": "x", "dominio": "movistarplus.es"}) == "ok"
    lina.A.buscar_tavily.assert_called_once_with("x", "movistarplus.es")


def test_buscalo_igualmente_salta_ninguna_solo_en_esa_peticion(lina, monkeypatch):
    monkeypatch.setattr(lina.A, "modo_busqueda", lambda: "ninguna")
    buscar = MagicMock(return_value=NADA)
    monkeypatch.setattr(BUS, "buscar", buscar)
    lina.forzar_busqueda = True
    lina._ejecutar_herramienta("buscar_web", {"consulta": "x"})
    assert buscar.call_args.kwargs["modo"] == "auto"
    assert [d["name"] for d in IA.declaraciones_de_busqueda(forzar=True)] == ["buscar_web"]


@pytest.mark.parametrize("modo, frase, fuerza", [("ninguna", "búscalo igualmente", True), ("ninguna", "qué tiempo hace", False), ("auto", "búscalo igualmente", False)])
def test_solo_buscalo_igualmente_con_ninguna_fuerza_la_busqueda(lina, monkeypatch, modo, frase, fuerza):
    monkeypatch.setattr(lina.A, "modo_busqueda", lambda: modo)
    assert lina._buscar_igualmente(frase) is fuerza


# ---------------------------------------------------------------- nunca «no tengo acceso a internet»
def test_si_se_busco_con_exito_se_corrige(lina):
    lina.acciones_turno = [("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…)\n[1] …")]
    r = lina._sin_negar_internet("Es Canberra. No tengo acceso a internet, así que puede haber cambiado.")
    assert "acceso a internet" not in r and r.startswith("Es Canberra.") and "he buscado o leído ahora en internet" in r


def test_si_nada_dio_resultados_se_dice_el_motivo_de_verdad(lina):
    lina.busquedas_hechas = [NADA]
    r = lina._sin_negar_internet("Lo siento, no puedo acceder a internet.")
    assert r.startswith("No he podido buscarlo: no tienes clave de Tavily y Wikipedia") and "lina bienvenida" in r


def test_con_ninguna_se_dice_que_esta_apagado_y_como_saltarlo(lina, monkeypatch):
    monkeypatch.setattr(lina.A, "modo_busqueda", lambda: "ninguna")
    r = lina._sin_negar_internet("No tengo acceso a información en tiempo real.")
    assert "ia.busqueda = ninguna" in r and "búscalo igualmente" in r


def test_lo_demas_no_se_toca(lina):
    assert lina._sin_negar_internet("Es Canberra, según Wikipedia.") == "Es Canberra, según Wikipedia."
    assert lina._sin_negar_internet("No tengo acceso a tu calendario.") == "No tengo acceso a tu calendario."


def test_va_en_la_ultima_red(lina):
    lina._honestidad_de_lo_hecho = lambda t: t
    lina._aclarar_fuente = lambda t: t
    lina._avisar_fuente_sin_anadir = lambda t: t
    lina.busquedas_hechas = [NADA]
    assert "acceso a internet" not in lina.asegurar_honestidad_final("No tengo acceso a internet.")


# ---------------------------------------------------------------- la atribución, corregida en código antes de contestar
GOOGLE_SKYRIM = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…):\n\n[1] a (gamespot.com) https://vertexaisearch.cloud.google.com/a\nx\n"
                 "[2] b (skyrimalchemy.com) https://vertexaisearch.cloud.google.com/b\ny\n[3] c (scribd.com) https://vertexaisearch.cloud.google.com/c\nz")
GOOGLE_NOTICIA = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…):\n\n[1] a (emergent.sh) https://vertexaisearch.cloud.google.com/a\nx")


@pytest.mark.parametrize("accion, dice, queda", [
    (GOOGLE_SKYRIM, "Según la wiki UESP, la poción lleva ectoplasma y pie de nirn.", "Según gamespot.com, la poción lleva ectoplasma y pie de nirn."),
    (GOOGLE_NOTICIA, "Según Google News, lo más importante hoy es el chip nuevo.", "Según emergent.sh, lo más importante hoy es el chip nuevo."),
])
def test_los_dos_casos_reales_de_atribucion_inventada(lina, accion, dice, queda):
    lina._honestidad_de_lo_hecho = lambda t: t
    lina._aclarar_fuente = lambda t: t
    lina._avisar_fuente_sin_anadir = lambda t: t
    lina.acciones_turno = [accion]
    assert lina.asegurar_honestidad_final(dice) == queda


def test_la_atribucion_buena_o_sin_busqueda_no_se_toca(lina):
    lina.acciones_turno = [GOOGLE_SKYRIM]
    assert lina._atribucion_real("Según gamespot.com, lleva ectoplasma.") == "Según gamespot.com, lleva ectoplasma."
    lina.acciones_turno = []
    assert lina._atribucion_real("Según la wiki UESP, lleva ectoplasma.") == "Según la wiki UESP, lleva ectoplasma."


def test_con_una_fuente_tuya_la_atribucion_la_cuida_aclarar_fuente(lina):
    lina.acciones_turno = [GOOGLE_SKYRIM, ("usar_fuente", {"dominio": "uesp.net"}, "Es la fuente que eligió el usuario…")]
    assert lina._atribucion_real("Según la UESP, lleva ectoplasma.") == "Según la UESP, lleva ectoplasma."


# ---------------------------------------------------------------- leer una wiki: su extracto, sin resumir por trozos
def test_leer_una_wiki_conocida_va_por_su_api(lina, monkeypatch):
    monkeypatch.setattr(BUS, "pagina_wiki", lambda w: {"url": w["url"], "titulo": w["title"], "texto": "extracto"})
    lina._h_leer_web("leer_web", {"url": "https://minecraft.wiki/w/Creeper"})
    lina.leer_web.assert_called_once_with({"url": "https://minecraft.wiki/w/Creeper"}, pagina={"url": "https://minecraft.wiki/w/Creeper", "titulo": "Creeper", "texto": "extracto"})


def test_leer_otra_web_va_como_siempre(lina, monkeypatch):
    monkeypatch.setattr(BUS, "pagina_wiki", MagicMock(side_effect=AssertionError("no es una wiki")))
    lina._h_leer_web("leer_web", {"url": "https://www.gamespot.com/x"})
    lina.leer_web.assert_called_once_with({"url": "https://www.gamespot.com/x"}, pagina=None)


# ---------------------------------------------------------------- por qué no responde Gemini, dicho tal cual
DIARIO = "error 429 RESOURCE_EXHAUSTED | cuota=GenerateRequestsPerDayPerProjectPerModel-FreeTier límite=20"


@pytest.mark.parametrize("error, clase", [
    (IA.PROV.ErrorIA("cuota", 429, DIARIO), "diario"),
    (IA.PROV.ErrorIA("cuota", 429, "error 429 | cuota=GenerateRequestsPerMinutePerProjectPerModel-FreeTier límite=15", 9.0), "cuota"),
    (IA.PROV.ErrorIA("servidor", 503, "error 503 UNAVAILABLE | The model is overloaded"), "saturado"),
    (IA.PROV.ErrorIA("red", None, "HTTPSConnectionPool(...): Read timed out. (read timeout=8)"), "saturado"),
    (IA.PROV.ErrorIA("red", None, "Failed to resolve 'generativelanguage.googleapis.com'"), "red"),
])
def test_la_clase_de_cada_fallo(error, clase):
    assert IA.clase_de_fallo(error) == clase


def test_el_cupo_diario_se_renueva_a_medianoche_del_pacifico():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    a_las_22 = datetime(2026, 11, 4, 22, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    assert IA.horas_hasta_renovar_cupo(a_las_22) == 2
    assert IA.horas_hasta_renovar_cupo(a_las_22 + 2 * 3600 - 60) == 1
    assert IA.horas_hasta_renovar_cupo(a_las_22 + 2 * 3600 + 60) == 24


def _sin_gemini(lina, monkeypatch, fallos):
    monkeypatch.setattr(lina.A, "fallos_de_la_peticion", lambda: fallos)
    monkeypatch.setattr(lina.A, "horas_hasta_renovar_cupo", lambda: 7)
    return lina._por_que_no_responde_gemini()


def test_con_el_cupo_diario_agotado_lo_dice_y_cuando_vuelve(lina, monkeypatch):
    t = _sin_gemini(lina, monkeypatch, [("diario", "gratis"), ("diario", "gratis")])
    assert t == "Has agotado el límite diario de la clave gratuita de Gemini; se renueva en unas 7 horas. Con una clave de pago o con otro modelo funciona ya."


def test_con_503_o_tiempo_agotado_dice_que_esta_saturado(lina, monkeypatch):
    assert _sin_gemini(lina, monkeypatch, [("saturado", "gratis"), ("diario", "gratis")]) == "Gemini gratuito está saturado ahora. Inténtalo dentro de un rato."
    assert _sin_gemini(lina, monkeypatch, [("diario", "gratis"), ("saturado", "pago")]) == "Gemini está saturado ahora. Inténtalo dentro de un rato."


@pytest.mark.parametrize("fallos", [[], [("auth", "gratis")], [("diario", "gratis"), ("auth", "pago")], [("diario", "pago")]])
def test_si_no_esta_claro_la_frase_de_siempre(lina, monkeypatch, fallos):
    assert _sin_gemini(lina, monkeypatch, fallos) is None


def test_preguntar_ia_apunta_el_fallo_y_lo_recuerda_al_saltar_el_modelo_en_pausa(monkeypatch):
    monkeypatch.setattr(IA, "_pausa_modelo", {})
    monkeypatch.setattr(IA, "_clase_pausa", {})
    monkeypatch.setattr(IA.PRES, "una_sola_clave", lambda: True)
    monkeypatch.setattr(IA, "_turno_medido", lambda *a, **k: IA.PROV.ErrorIA("cuota", 429, DIARIO))
    IA.empezar_peticion()
    assert IA.preguntar_ia(MagicMock(), "clave", "modelo-x", "hola", None) is None
    assert IA.preguntar_ia(MagicMock(), "clave", "modelo-x", "hola", None) is None       # ahora en pausa: no llama, pero sabe por qué
    assert IA.fallos_de_la_peticion() == [("diario", "gratis"), ("diario", "gratis")]
    IA.empezar_peticion()
    assert IA.fallos_de_la_peticion() == []


@pytest.mark.parametrize("comando, empieza", [
    ("curl -s 'https://lite.duckduckgo.com/lite/?q=lol'", "BLOQUEADO"),
    ("python3 -c \"import requests; print(requests.post('https://html.duckduckgo.com/html', data={'q': 'x'}).text)\"", "BLOQUEADO"),
    ("curl https://www.google.com/search?q=precio", "BLOQUEADO"),
    ("curl -s 'https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=es-ES' -H 'x-api-key: abc' | jq .", "No se ha ejecutado"),
    ("wget -qO- https://ejemplo.com/pagina", "No se ha ejecutado"),
    ("curl wttr.in/Sevilla", "No se ha ejecutado"),
])
def test_buscar_o_leer_la_web_con_un_comando_va_a_sus_herramientas(comando, empieza):
    r = H.lectura_web_por_comando(comando)
    assert r.startswith(empieza) and ("buscar_web" if empieza == "BLOQUEADO" else "leer_web") in r


@pytest.mark.parametrize("comando", ["curl -sLo /tmp/a.zip https://ejemplo.com/a.zip", "curl -I https://ejemplo.com", "wget https://ejemplo.com/a.iso",
                                     "curl http://localhost:8080/api", "curl -s http://192.168.1.10/estado", "curl -s https://ejemplo.com > pagina.html",
                                     "xdg-open 'https://www.google.com/search?q=hola'", "git clone https://github.com/a/b", "ls -la",
                                     "curl -s https://dl.google.com/linux/x.deb -o x.deb", "python3 -c 'print(1 + 1)'"])
def test_descargas_cabeceras_la_red_de_casa_y_lo_demas_siguen_libres(comando):
    assert H.lectura_web_por_comando(comando) is None


def test_el_ejecutor_no_lo_ejecuta(monkeypatch):
    e = H.Ejecutor(confirmar=False)
    monkeypatch.setattr(e, "ejecutar", MagicMock(side_effect=AssertionError("no debía ejecutarse")))
    monkeypatch.setattr(H, "anotar", lambda *a: None)
    r = e.herramienta({"comando": "curl -s https://lite.duckduckgo.com/lite/?q=x", "motivo": "buscar"})
    assert r.startswith("BLOQUEADO") and "buscar_web" in r


# ---------------------------------------------------------------- DuckDuckGo: honesto, apagado de fábrica, y el bloqueo apuntado para lina doctor
def test_duckduckgo_dice_quien_es_y_apunta_el_bloqueo(monkeypatch, tmp_path):
    monkeypatch.setattr(RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(IA, "_pausa_reserva", [0.0])
    vistos = []

    def post(url, data, timeout, headers):
        vistos.append(headers["User-Agent"])
        return MagicMock(status_code=202, ok=True, text="")
    assert IA.resultados_reserva("x", post=post) == "La búsqueda web no está disponible ahora mismo."
    assert vistos[0].startswith("Lina/") and "Mozilla" not in vistos[0]            # no nos hacemos pasar por un navegador para esquivarlo
    assert IA.ultimo_robot() is not None


def test_sin_bloqueo_apuntado_no_hay_fecha(monkeypatch, tmp_path):
    monkeypatch.setattr(RUT, "ESTADO", tmp_path)
    assert IA.ultimo_robot() is None


# ---------------------------------------------------------------- los avisos de la primera vez
def test_la_primera_vez_con_duckduckgo_se_dice_y_se_notifica_una_sola_vez(monkeypatch, tmp_path):
    monkeypatch.setattr(RUT, "ESTADO", tmp_path)
    AVB.descartar()
    AVB.apuntar(AVB.PRIMERA_DUCKDUCKGO)
    (hablado, titulo, texto), = AVB.pendientes("auto")
    assert "DuckDuckGo" in hablado and "poco fiable" in texto and "dirección IP" in texto and "ia.busqueda_reserva false" in texto
    AVB.apuntar(AVB.PRIMERA_DUCKDUCKGO)
    assert AVB.pendientes("auto") == []
    AVB.olvidar()                                                       # guardar otra clave de Tavily no vuelve a avisar de esto
    AVB.apuntar(AVB.PRIMERA_DUCKDUCKGO)
    assert AVB.pendientes("auto") == []


def test_la_primera_vez_con_las_wikis_solo_se_notifica(monkeypatch, tmp_path):
    monkeypatch.setattr(RUT, "ESTADO", tmp_path)
    AVB.descartar()
    AVB.apuntar(AVB.PRIMERA_WIKI)
    (hablado, titulo, texto), = AVB.pendientes("auto")
    assert hablado == "" and "Wikipedia" in texto and "Tavily" in texto and "dirección IP" in texto


# ---------------------------------------------------------------- la de Google ya no quita nuestras herramientas
def test_preguntar_ia_nunca_pide_la_busqueda_nativa(monkeypatch):
    monkeypatch.setattr(IA, "modo_busqueda", lambda: "google")
    proveedor = MagicMock(busqueda_nativa=True)
    proveedor.turno.return_value = MagicMock(spec=["texto", "llamadas", "uso", "modelo_real", "turno"], texto="hola", llamadas=[], uso={}, modelo_real="m", turno={})
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("sin red")))
    IA.preguntar_ia(proveedor, "CLAVE", "modelo-x", "hola", None, herramientas=[{"name": "abrir_app"}], ejecutar_herramienta=lambda n, a: "")
    k = proveedor.turno.call_args.kwargs
    assert "busqueda_nativa" not in k and k["herramientas"] == [{"name": "abrir_app"}]
