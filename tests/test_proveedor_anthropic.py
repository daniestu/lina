# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Proveedor «anthropic» (API de mensajes) contra un servidor simulado con el formato publicado de esa API."""
import json

import pytest
import requests

from lina.nucleo import ia as IA
from lina.nucleo import proveedor_anthropic as PA
from lina.nucleo import proveedores as PROV


class R:
    def __init__(self, estado=200, datos=None, texto="", cabeceras=None):
        self.status_code, self.ok, self._d, self.headers = estado, estado < 400, datos, cabeceras or {}
        self.text = texto or json.dumps(datos or {})

    def json(self):
        if self._d is None:
            raise ValueError("sin json")
        return self._d


def contenido(*bloques, uso=None):
    return R(200, {"model": "claude-real", "content": list(bloques), "stop_reason": "end_turn",
                   "usage": uso or {"input_tokens": 15, "output_tokens": 9, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 2}})


def texto_(t):
    return {"type": "text", "text": t}


def usa(nombre, entrada, id="toolu_1"):
    return {"type": "tool_use", "id": id, "name": nombre, "input": entrada}


def fallo(estado, tipo="api_error", mensaje="x", cabeceras=None):
    return R(estado, {"type": "error", "error": {"type": tipo, "message": mensaje}}, cabeceras=cabeceras)


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


def turno(**k):
    return PA.ANTHROPIC.turno(k.pop("clave", "SK"), "claude-m", k.pop("sistema", "SISTEMA"), k.pop("mensajes", [{"rol": "user", "texto": "hola"}]), **k)


def test_forma_de_la_peticion_y_de_la_respuesta(servir):
    s = servir(contenido(texto_("Hola"), texto_("Dani")))
    r = turno(temperatura=0)
    p = s.peticiones[0]
    assert p["url"] == "https://api.anthropic.com/v1/messages"
    assert p["headers"] == {"x-api-key": "SK", "anthropic-version": "2023-06-01", "content-type": "application/json"}
    assert p["json"]["system"] == "SISTEMA" and p["json"]["max_tokens"] == 4096 and p["json"]["temperature"] == 0 and "tools" not in p["json"]
    assert p["json"]["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hola"}]}]
    assert r.texto == "Hola Dani" and r.modelo_real == "claude-real"
    assert r.uso == {"promptTokenCount": 22, "candidatesTokenCount": 9, "thoughtsTokenCount": 0, "cachedContentTokenCount": 5}


def test_imagen_roles_y_sin_bloques_vacios(servir):
    s = servir(contenido(texto_("ok")))
    turno(max_salida=100, mensajes=[{"rol": "user", "texto": "antes"}, {"rol": "model", "texto": ""}, {"rol": "user", "texto": "mira", "imagen": "AAAA"}])
    j = s.peticiones[0]["json"]
    assert j["max_tokens"] == 100 and [m["role"] for m in j["messages"]] == ["user", "user"]
    assert j["messages"][1]["content"] == [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}},
                                           {"type": "text", "text": "mira"}]


def test_herramientas_y_esquemas(servir):
    s = servir(contenido(texto_("{}")))
    decl = [{"name": "hora", "description": "da la hora", "parameters": {"type": "object", "properties": {"zona": {"type": "string"}}}}]
    turno(herramientas=decl, json_esquema={"type": "OBJECT", "properties": {"decision": {"type": "STRING"}}})
    j = s.peticiones[0]["json"]
    assert j["tools"] == [{"name": "hora", "description": "da la hora", "input_schema": decl[0]["parameters"]}]
    assert "SOLO con un objeto JSON" in j["system"] and '"type": "object"' in j["system"] and j["system"].startswith("SISTEMA")


def test_llamadas_a_herramientas(servir):
    servir(contenido(texto_("voy"), usa("hora", {"zona": "x"}, "tu1")))
    r = turno()
    assert r.texto == "voy" and [(c.nombre, c.args, c.id) for c in r.llamadas] == [("hora", {"zona": "x"}, "tu1")]
    assert r.turno == {"role": "assistant", "content": [texto_("voy"), usa("hora", {"zona": "x"}, "tu1")]}


def test_el_bucle_de_herramientas_con_este_proveedor(servir):
    s = servir(contenido(usa("hora", {"zona": "x"})), contenido(texto_("Son las tres")))
    hechas = []
    r = IA.preguntar_ia(PA.ANTHROPIC, "SK", "claude-m", "¿qué hora es?", None, herramientas=[{"name": "hora"}],
                        ejecutar_herramienta=lambda n, a: hechas.append((n, a)) or "15:00")
    assert r == "Son las tres" and hechas == [("hora", {"zona": "x"})]
    m = s.peticiones[1]["json"]["messages"]
    assert m[-2] == {"role": "assistant", "content": [usa("hora", {"zona": "x"})]}
    assert m[-1] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "15:00"}]}


def test_errores_con_tipo_comun(servir):
    servir(fallo(401, "authentication_error"), fallo(429, "rate_limit_error", cabeceras={"retry-after": "12"}), fallo(529, "overloaded_error"),
           fallo(500), fallo(400, "invalid_request_error", "mal"), R(200, {"content": []}), R(200, {}))
    e = [turno() for _ in range(7)]
    assert [x.tipo for x in e] == ["auth", "cuota", "servidor", "servidor", "peticion", "vacia", "vacia"]
    assert e[1].espera == 12.0 and "authentication_error" in e[0].resumen


def test_529_se_reintenta_como_un_servidor_ocupado(servir):
    s = servir(fallo(529, "overloaded_error"), contenido(texto_("ya")))
    assert IA.preguntar_ia(PA.ANTHROPIC, "SK", "claude-m", "hola", None) == "ya" and len(s.peticiones) == 2


def test_sin_conexion(servir):
    servir(requests.ConnectionError("sin red"))
    assert turno().tipo == "red"


def test_las_mini_consultas_funcionan_con_este_proveedor(servir):
    servir(contenido(texto_('```json\n{"decision": "confirma", "menciona_cantidad": false}\n```')))
    r = IA._mini_consulta_json("SK", "PROMPT", IA.ESQUEMA_CONFIRMACION, "dato", "x", lambda o: o["decision"], proveedor=PA.ANTHROPIC)
    assert r[0]["decision"] == "confirma"


def test_esta_registrado():
    assert PROV.obtener("anthropic") is PA.ANTHROPIC and PROV.nombres() == ["anthropic", "gemini", "openai"]
