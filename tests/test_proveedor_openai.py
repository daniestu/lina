# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Proveedor «openai» (API de chat de OpenAI y compatibles) contra un servidor simulado con el formato publicado de esa API."""
import json

import pytest
import requests

from lina.nucleo import ia as IA
from lina.nucleo import proveedor_openai as PO
from lina.nucleo import proveedores as PROV


class R:
    def __init__(self, estado=200, datos=None, texto="", cabeceras=None):
        self.status_code, self.ok, self._d, self.headers = estado, estado < 400, datos, cabeceras or {}
        self.text = texto or json.dumps(datos or {})

    def json(self):
        if self._d is None:
            raise ValueError("sin json")
        return self._d


def mensaje(contenido=None, llamadas=None, uso=None):
    m = {"role": "assistant", "content": contenido}
    if llamadas:
        m["tool_calls"] = llamadas
    return R(200, {"model": "gpt-real", "choices": [{"message": m}],
                   "usage": uso or {"prompt_tokens": 20, "completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": 4},
                                    "prompt_tokens_details": {"cached_tokens": 8}}})


def pide(nombre, args, id="call_1"):
    return {"id": id, "type": "function", "function": {"name": nombre, "arguments": json.dumps(args)}}


def fallo(estado, mensaje_="x", codigo="", cabeceras=None):
    return R(estado, {"error": {"message": mensaje_, "type": "api_error", "code": codigo}}, cabeceras=cabeceras)


class Servidor:
    def __init__(self, *cola):
        self.cola, self.peticiones = list(cola), []

    def post(self, url, **kw):
        self.peticiones.append({"url": url, "headers": kw.get("headers"), "json": json.loads(json.dumps(kw.get("json")))})
        e = self.cola.pop(0)
        if isinstance(e, Exception):
            raise e
        return e


@pytest.fixture
def servir(monkeypatch):
    monkeypatch.setattr(IA, "log", lambda m: None)
    monkeypatch.setattr(IA, "_dormir", lambda s: None)
    IA._pausa_modelo.clear()

    class PresFalso:
        def registrar(self, *a, **k): pass
        def una_sola_clave(self): return True
        def nombre_de(self, clave): return "gratis"
    monkeypatch.setattr(IA, "PRES", PresFalso())

    def f(*cola):
        s = Servidor(*cola)
        monkeypatch.setattr(requests, "post", s.post)
        return s
    return f


def turno(prov=None, **k):
    prov = prov or PO.OPENAI
    return prov.turno(k.pop("clave", "SK"), "m", k.pop("sistema", "SISTEMA"), k.pop("mensajes", [{"rol": "user", "texto": "hola"}]), **k)


def test_forma_de_la_peticion_y_de_la_respuesta(servir):
    s = servir(mensaje("Hola"))
    r = turno(temperatura=0, max_salida=50)
    p = s.peticiones[0]
    assert p["url"] == "https://api.openai.com/v1/chat/completions" and p["headers"] == {"Authorization": "Bearer SK"}
    assert p["json"]["messages"] == [{"role": "system", "content": "SISTEMA"}, {"role": "user", "content": "hola"}]
    assert p["json"]["temperature"] == 0 and p["json"]["max_tokens"] == 50 and "tools" not in p["json"]
    assert r.texto == "Hola" and r.modelo_real == "gpt-real"
    assert r.uso == {"promptTokenCount": 20, "candidatesTokenCount": 8, "thoughtsTokenCount": 4, "cachedContentTokenCount": 8}


def test_servidor_propio_o_local_sin_clave(servir):
    s = servir(mensaje("ok"))
    turno(PO.OpenAI("http://localhost:11434/v1/"), clave="")
    assert s.peticiones[0]["url"] == "http://localhost:11434/v1/chat/completions" and s.peticiones[0]["headers"] == {}


def test_imagen_y_roles(servir):
    s = servir(mensaje("ok"))
    turno(mensajes=[{"rol": "user", "texto": "antes"}, {"rol": "model", "texto": "vale"}, {"rol": "user", "texto": "mira", "imagen": "AAAA"}])
    m = s.peticiones[0]["json"]["messages"]
    assert [x["role"] for x in m] == ["system", "user", "assistant", "user"]
    assert m[3]["content"] == [{"type": "text", "text": "mira"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}]


def test_las_herramientas_y_los_esquemas_se_traducen(servir):
    s = servir(mensaje("ok"))
    decl = [{"name": "hora", "description": "da la hora", "parameters": {"type": "object", "properties": {"zona": {"type": "string"}}}}]
    turno(herramientas=decl, json_esquema={"type": "OBJECT", "properties": {"decision": {"type": "STRING", "enum": ["si", "no"]}}, "required": ["decision"]})
    c = s.peticiones[0]["json"]
    assert c["tools"] == [{"type": "function", "function": {"name": "hora", "description": "da la hora", "parameters": decl[0]["parameters"]}}]
    assert c["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert c["response_format"]["json_schema"]["schema"]["properties"]["decision"]["type"] == "string"


def test_json_sin_esquema_y_nivel_solo_si_se_activa(servir):
    s = servir(mensaje("{}"), mensaje("{}"))
    turno(json_esquema=True, nivel="low")
    turno(PO.OpenAI(razonamiento=True), nivel="low")
    assert s.peticiones[0]["json"]["response_format"] == {"type": "json_object"} and "reasoning_effort" not in s.peticiones[0]["json"]
    assert s.peticiones[1]["json"]["reasoning_effort"] == "low"


def test_llamadas_a_herramientas(servir):
    servir(mensaje(None, [pide("hora", {"zona": "x"}, "c9"), {"id": "c10", "type": "function", "function": {"name": "rota", "arguments": "no es json"}}]))
    r = turno()
    assert [(c.nombre, c.args, c.id) for c in r.llamadas] == [("hora", {"zona": "x"}, "c9"), ("rota", {}, "c10")]
    assert r.turno["tool_calls"][0] == {"id": "c9", "type": "function", "function": {"name": "hora", "arguments": '{"zona": "x"}'}}


def test_el_bucle_de_herramientas_con_este_proveedor(servir):
    s = servir(mensaje(None, [pide("hora", {"zona": "x"})]), mensaje("Son las tres"))
    hechas = []
    r = IA.preguntar_ia(PO.OPENAI, "SK", "m", "¿qué hora es?", None, herramientas=[{"name": "hora"}],
                        ejecutar_herramienta=lambda n, a: hechas.append((n, a)) or "15:00")
    assert r == "Son las tres" and hechas == [("hora", {"zona": "x"})]
    m = s.peticiones[1]["json"]["messages"]
    assert m[-2]["role"] == "assistant" and m[-2]["tool_calls"][0]["id"] == "call_1"
    assert m[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "15:00"}


def test_errores_con_tipo_comun(servir):
    servir(fallo(401, "clave", "invalid_api_key"), fallo(429, "despacio", cabeceras={"retry-after": "7"}), fallo(429, "sin saldo", "insufficient_quota"),
           fallo(503), fallo(400, "mal"), R(200, {"choices": []}), mensaje(""))
    e = [turno() for _ in range(7)]
    assert [x.tipo for x in e] == ["auth", "cuota", "cuota", "servidor", "peticion", "vacia", "vacia"]
    assert e[1].espera == 7.0 and e[2].espera is None and "clave" in e[0].resumen


def test_sin_conexion(servir):
    servir(requests.ConnectionError("sin red"))
    assert turno().tipo == "red"


def test_los_modelos_nuevos_piden_max_completion_tokens(servir):
    s = servir(R(400, {"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."}}), mensaje("ok"))
    assert turno(max_salida=30).texto == "ok"
    assert "max_tokens" in s.peticiones[0]["json"] and s.peticiones[1]["json"]["max_completion_tokens"] == 30 and "max_tokens" not in s.peticiones[1]["json"]


def test_las_mini_consultas_funcionan_con_este_proveedor(servir):
    s = servir(mensaje('{"decision": "confirma", "menciona_cantidad": false}'))
    r = IA._mini_consulta_json("SK", "PROMPT", IA.ESQUEMA_CONFIRMACION, "dato", "x", lambda o: o["decision"], proveedor=PO.OPENAI)
    assert r[0]["decision"] == "confirma"
    assert s.peticiones[0]["json"]["response_format"]["json_schema"]["schema"]["type"] == "object"


def test_esta_registrado():
    assert PROV.obtener("openai") is PO.OPENAI and "openai" in PROV.nombres()
