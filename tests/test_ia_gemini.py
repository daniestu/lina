# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El bucle de Gemini y las mini-consultas, contra un servidor simulado (sin red). Fijan el comportamiento de cara a la fase 7."""
import json

import pytest
import requests

from lina.nucleo import ia as IA


class R:
    def __init__(self, estado=200, datos=None, texto=""):
        self.status_code, self.ok, self._d = estado, estado < 400, datos
        self.text = texto or json.dumps(datos or {})

    def json(self):
        if self._d is None:
            raise ValueError("sin json")
        return self._d


def texto(t, uso=None, partes_extra=()):
    return R(200, {"candidates": [{"content": {"role": "model", "parts": [*partes_extra, {"text": t}]}}], "modelVersion": "real-1",
                   "usageMetadata": uso or {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 2}})


def llamada(nombre, args=None, firma="firma-1"):
    return R(200, {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": nombre, "args": args or {}}, "thoughtSignature": firma}]}}]})


def error(estado, mensaje="fallo", detalles=()):
    return R(estado, {"error": {"code": estado, "status": "X", "message": mensaje, "details": list(detalles)}})


class Servidor:
    def __init__(self, *cola):
        self.cola, self.peticiones = list(cola), []

    def post(self, url, **kw):
        self.peticiones.append({"url": url, "headers": kw.get("headers"), "json": json.loads(json.dumps(kw.get("json"))), "timeout": kw.get("timeout")})
        elemento = self.cola.pop(0)
        if isinstance(elemento, Exception):
            raise elemento
        return elemento


class PresFalso:
    def __init__(self):
        self.apuntes = []

    def registrar(self, clave, modelo, uso, modelo_real=None):
        self.apuntes.append((clave, modelo, uso, modelo_real))

    def una_sola_clave(self):
        return True

    def nombre_de(self, clave):
        return "gratis"


@pytest.fixture
def ia(monkeypatch):
    pres = PresFalso()
    esperas = []
    monkeypatch.setattr(IA, "PRES", pres)
    monkeypatch.setattr(IA, "_dormir", lambda s: esperas.append(s))
    monkeypatch.setattr(IA, "log", lambda m: None)
    monkeypatch.setattr(IA, "BUSQUEDA", "tavily")
    IA._pausa_modelo.clear()
    IA._abortar.clear()

    def servir(*cola):
        s = Servidor(*cola)
        monkeypatch.setattr(requests, "post", s.post)
        return s
    servir.pres, servir.esperas = pres, esperas
    return servir


def preguntar(**k):
    return IA.preguntar_gemini("CLAVE", "m1", k.pop("pregunta", "hola"), k.pop("imagen", None), **k)


def test_respuesta_de_texto_y_forma_de_la_peticion(ia):
    s = ia(texto("Hola, Dani"))
    assert preguntar(sistema="SISTEMA") == "Hola, Dani"
    p = s.peticiones[0]
    assert p["url"].endswith("/models/m1:generateContent") and p["headers"] == {"x-goog-api-key": "CLAVE"}
    assert p["json"]["system_instruction"] == {"parts": [{"text": "SISTEMA"}]}
    assert p["json"]["contents"] == [{"role": "user", "parts": [{"text": "hola"}]}]
    assert "tools" not in p["json"] and "generationConfig" not in p["json"]
    assert ia.pres.apuntes == [("CLAVE", "m1", {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 2}, "real-1")]


def test_imagen_historial_y_nivel(ia):
    s = ia(texto("ok"))
    historial = [{"rol": "user", "texto": "antes"}, {"rol": "model", "texto": "respuesta"}]
    preguntar(pregunta="mira", imagen="AAAA", historial=historial, nivel="low")
    c = s.peticiones[0]["json"]
    assert [x["role"] for x in c["contents"]] == ["user", "model", "user"]
    assert c["contents"][-1]["parts"][0] == {"inline_data": {"mime_type": "image/jpeg", "data": "AAAA"}}
    assert c["generationConfig"] == {"thinkingConfig": {"thinkingLevel": "low"}}


def test_las_partes_de_razonamiento_no_se_devuelven(ia):
    ia(texto("final", partes_extra=({"text": "pensando…", "thought": True},)))
    assert preguntar() == "final"


def test_herramientas_se_ejecutan_y_el_turno_vuelve_tal_cual(ia):
    s = ia(llamada("hora", {"zona": "x"}), texto("Son las tres"))
    llamadas = []
    decl = [{"name": "hora", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    r = preguntar(herramientas=decl, ejecutar_herramienta=lambda n, a: llamadas.append((n, a)) or "15:00")
    assert r == "Son las tres" and llamadas == [("hora", {"zona": "x"})]
    assert s.peticiones[0]["json"]["tools"] == [{"functionDeclarations": decl}]
    c2 = s.peticiones[1]["json"]["contents"]
    assert c2[-2]["role"] == "model" and c2[-2]["parts"][0]["thoughtSignature"] == "firma-1"       # el turno de Gemini 3 vuelve con su firma
    assert c2[-1] == {"role": "user", "parts": [{"functionResponse": {"name": "hora", "response": {"resultado": "15:00"}}}]}


def test_una_herramienta_que_falla_no_tumba_la_respuesta(ia):
    s = ia(llamada("rota"), texto("vale"))

    def rota(n, a):
        raise RuntimeError("boom")
    assert preguntar(herramientas=[{"name": "rota"}], ejecutar_herramienta=rota) == "vale"
    assert "ha fallado" in s.peticiones[1]["json"]["contents"][-1]["parts"][0]["functionResponse"]["response"]["resultado"]


def test_limite_de_pasos(ia):
    doble = R(200, {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "a", "args": {}}}, {"functionCall": {"name": "a", "args": {}}}]}}]})
    s = ia(doble, texto("fin"))
    hechas = []
    preguntar(herramientas=[{"name": "a"}], ejecutar_herramienta=lambda n, a: hechas.append(n) or "ok", max_pasos=1)
    assert len(hechas) == 1
    resultados = [p["functionResponse"]["response"]["resultado"] for p in s.peticiones[1]["json"]["contents"][-1]["parts"]]
    assert resultados[1].startswith("Límite de pasos")


def test_400_con_nivel_reintenta_sin_el(ia):
    s = ia(error(400), texto("ok"))
    assert preguntar(nivel="minimal") == "ok"
    assert "generationConfig" in s.peticiones[0]["json"] and "generationConfig" not in s.peticiones[1]["json"]


@pytest.mark.parametrize("estado", [400, 429])
def test_error_con_herramientas_reintenta_sin_ellas(ia, estado):
    s = ia(error(estado), texto("ok"))
    assert preguntar(herramientas=[{"name": "a"}], ejecutar_herramienta=lambda n, a: "x") == "ok"
    assert "tools" in s.peticiones[0]["json"] and "tools" not in s.peticiones[1]["json"]


def test_sin_herramientas_se_avisa_a_la_ia_de_que_no_puede_actuar(ia):
    """Un modelo sin herramientas que no lo sabe contesta «hecho» sin haber hecho nada (pasó con un modelo local)."""
    s = ia(error(400), texto("ok"))
    preguntar(sistema="SISTEMA", herramientas=[{"name": "a"}], ejecutar_herramienta=lambda n, a: "x")
    antes = s.peticiones[0]["json"]["system_instruction"]["parts"][0]["text"]
    despues = s.peticiones[1]["json"]["system_instruction"]["parts"][0]["text"]
    assert antes == "SISTEMA" and despues.startswith("SISTEMA") and "NO tienes herramientas" in despues and "NUNCA digas que lo has hecho" in despues


def test_si_no_cabe_en_el_contexto_no_se_reintenta_sin_herramientas(ia):
    mensaje = "request (9839 tokens) exceeds the available context size (8192 tokens), try increasing it"
    s = ia(error(400, mensaje), texto("Subiendo el volumen"))
    assert preguntar(nivel="low", herramientas=[{"name": "a"}], ejecutar_herramienta=lambda n, a: "x") is None
    assert len(s.peticiones) == 1                                   # ni sin nivel, ni sin herramientas: falla y lo dice el registro


def test_servidor_ocupado_se_reintenta_con_espera_creciente(ia):
    s = ia(error(503), error(500), texto("ya"))
    assert preguntar() == "ya" and ia.esperas == [1.5, 3.0] and len(s.peticiones) == 3


def test_servidor_siempre_ocupado_deja_el_modelo_en_pausa(ia):
    s = ia(error(503), error(503), error(503))
    assert preguntar() is None
    assert preguntar() is None and len(s.peticiones) == 3            # la segunda llamada ni lo intenta


def test_cuota_por_minuto_se_espera_si_se_pide(ia):
    detalles = [{"@type": "x.QuotaFailure", "violations": [{"quotaId": "RequestsPerMinutePerProject"}]}, {"@type": "x.RetryInfo", "retryDelay": "5s"}]
    s = ia(error(429, detalles=detalles), texto("tras esperar"))
    avisos = []
    assert preguntar(esperar_cuota=True, al_esperar=lambda: avisos.append(1)) == "tras esperar"
    assert ia.esperas == [6.0] and avisos == [1] and len(s.peticiones) == 2


def test_cuota_diaria_no_se_espera(ia):
    detalles = [{"@type": "x.QuotaFailure", "violations": [{"quotaId": "RequestsPerDayPerProject"}]}]
    ia(error(429, detalles=detalles))
    assert preguntar(esperar_cuota=True) is None and ia.esperas == []


def test_sin_conexion_devuelve_none_y_pausa(ia):
    s = ia(requests.ConnectionError("sin red"))
    assert preguntar() is None and preguntar() is None and len(s.peticiones) == 1


@pytest.mark.parametrize("cuerpo", [R(200, {"candidates": []}), R(200, {}), R(200, None, "no json")])
def test_respuesta_vacia_o_bloqueada(ia, cuerpo):
    ia(cuerpo)
    assert preguntar() is None


def test_el_revisor_corrige_una_sola_vez(ia):
    s = ia(texto("¿confirmas?"), texto("hecho"))
    llamadas = []
    r = preguntar(herramientas=[{"name": "a"}], ejecutar_herramienta=lambda n, a: "x", revisor=lambda t: llamadas.append(t) or "no preguntes, hazlo")
    assert r == "hecho" and llamadas == ["¿confirmas?"]
    ultimo = s.peticiones[1]["json"]["contents"]
    assert ultimo[-2]["role"] == "model" and ultimo[-1]["parts"] == [{"text": "no preguntes, hazlo"}]


def test_cancelar_corta_la_peticion(ia):
    ia(texto("no debería llegar"))
    IA._abortar.set()
    try:
        with pytest.raises(IA.Cancelado):
            preguntar()
    finally:
        IA._abortar.clear()


def test_plazo_agotado(ia):
    s = ia(texto("x"))
    assert preguntar(plazo=0) is None and s.peticiones == []


# ------------------------------------------------------------- mini-consultas
ESQUEMA = {"type": "OBJECT", "properties": {"decision": {"type": "STRING"}}, "required": ["decision"]}


def test_mini_consulta_devuelve_la_decision_y_pide_json(ia):
    s = ia(texto('```json\n{"decision": "si"}\n```'))
    r = IA._mini_consulta_ia("K", "PROMPT", ESQUEMA, "dato", ("si", "no"), "prueba")
    assert r == {"decision": "si", "modelo": IA.IAC.modelos("mini")[0]}
    cfg = s.peticiones[0]["json"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and cfg["responseSchema"] == ESQUEMA and cfg["temperature"] == 0
    assert s.peticiones[0]["json"]["system_instruction"] == {"parts": [{"text": "PROMPT"}]}
    assert ia.pres.apuntes


def test_mini_consulta_quita_ajustes_de_uno_en_uno_al_dar_400(ia):
    s = ia(error(400), error(400), texto('{"decision": "no"}'))
    assert IA._mini_consulta_ia("K", "P", ESQUEMA, "d", ("si", "no"), "x")["decision"] == "no"
    cfgs = [p["json"]["generationConfig"] for p in s.peticiones]
    assert "thinkingConfig" in cfgs[0] and "thinkingConfig" not in cfgs[1] and "responseSchema" in cfgs[1] and "responseSchema" not in cfgs[2]


def test_mini_consulta_con_decision_desconocida_prueba_el_siguiente_modelo(ia):
    s = ia(texto('{"decision": "quizá"}'), texto('{"decision": "si"}'))
    r = IA._mini_consulta_ia("K", "P", ESQUEMA, "d", ("si", "no"), "x")
    assert r["modelo"] == IA.IAC.modelos("mini")[1] and len(s.peticiones) == 2
    ia2 = ia(texto("no es json"), texto("tampoco"))
    assert IA._mini_consulta_ia("K", "P", ESQUEMA, "d", ("si", "no"), "x") is None and len(ia2.peticiones) == 2


def test_confirmacion_devuelve_cantidad_y_modelo(ia):
    s = ia(texto('{"decision": "confirma", "menciona_cantidad": true}'))
    r = IA.clasificar_confirmacion_ia("K", "sí, hazlo", "instalar vlc")
    assert r == {"decision": "confirma", "menciona_cantidad": True, "modelo": IA.IAC.modelos("mini")[0]}
    contenido = s.peticiones[0]["json"]["contents"][0]["parts"][0]["text"]
    assert "instalar vlc" in contenido and "sí, hazlo" in contenido
    assert s.peticiones[0]["json"]["generationConfig"]["maxOutputTokens"] == 300


def test_resumir_trozo(ia):
    s = ia(error(400), texto("resumen corto"))
    assert IA._resumir_trozo("K", "texto largo", "foco", "el trozo 1") == "resumen corto"
    assert "thinkingConfig" in s.peticiones[0]["json"]["generationConfig"] and "thinkingConfig" not in s.peticiones[1]["json"]["generationConfig"]
    assert "<foco>foco</foco>" in s.peticiones[0]["json"]["contents"][0]["parts"][0]["text"]


def test_ver_imagen(ia):
    s = ia(error(400), texto("una ventana de Dolphin"))
    assert IA.ver_imagen("K", "AAAA", "¿qué ves?", "SISTEMA", json_salida=True, modelos=["m1"]) == ("una ventana de Dolphin", None)
    primera, segunda = s.peticiones[0]["json"], s.peticiones[1]["json"]
    assert primera["contents"][0]["parts"][0]["inline_data"]["data"] == "AAAA"
    assert primera["generationConfig"]["responseMimeType"] == "application/json" and "generationConfig" not in segunda
    ia([error(503)][0])
    assert IA.ver_imagen("K", "AAAA", "x", "S", modelos=["m2"])[0] is None


# ------------------------------------------------------------- el bucle no depende del proveedor
class ProveedorFalso(IA.PROV.Proveedor):
    nombre = "falso"

    def __init__(self, *respuestas):
        self.respuestas, self.vistos = list(respuestas), []

    def turno(self, clave, modelo, sistema, mensajes, **k):
        self.vistos.append((sistema, [dict(m) for m in mensajes], k))
        return self.respuestas.pop(0)


def test_el_bucle_de_herramientas_vale_para_cualquier_proveedor(ia):
    P = IA.PROV
    falso = ProveedorFalso(P.Respuesta("", [P.Llamada("hora", {"a": 1}, id="c1")], {}, None, {"cualquier": "cosa"}), P.Respuesta("Son las tres"))
    llamadas = []
    r = IA.preguntar_ia(falso, "K", "m", "¿qué hora es?", None, herramientas=[{"name": "hora"}],
                        ejecutar_herramienta=lambda n, a: llamadas.append((n, a)) or "15:00")
    assert r == "Son las tres" and llamadas == [("hora", {"a": 1})]
    segundo = falso.vistos[1][1]
    assert segundo[-2] == {"rol": "model", "turno": {"cualquier": "cosa"}}
    assert segundo[-1] == {"rol": "herramienta", "resultados": [{"nombre": "hora", "id": "c1", "texto": "15:00"}]}


def test_los_errores_de_un_proveedor_se_tratan_igual(ia):
    P = IA.PROV
    falso = ProveedorFalso(P.ErrorIA("servidor", 503, "ocupado"), P.Respuesta("ya"))
    assert IA.preguntar_ia(falso, "K", "m", "hola", None) == "ya" and ia.esperas == [1.5]
    falso = ProveedorFalso(P.ErrorIA("auth", 401, "clave mala"))
    assert IA.preguntar_ia(falso, "K", "m2", "hola", None) is None and "m2" not in IA._pausa_modelo
