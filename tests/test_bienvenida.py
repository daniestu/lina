from types import SimpleNamespace

import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import bienvenida as B


class Teclas:
    def __init__(self, *r):
        self.r = list(r)

    def __call__(self, texto=""):
        return self.r.pop(0)


def respuesta(codigo):
    return lambda *a, **k: SimpleNamespace(status_code=codigo)


def sin_red(*a, **k):
    raise requests.ConnectionError("sin red")


def charla(tmp_path, entrada, secretos=(), enviar=None, grabar=None):
    salida = []
    aj = AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)
    c = B.Charla(entrada=entrada, secreto=Teclas(*secretos), salida=salida.append, ajustes=aj, enviar=enviar or respuesta(200), grabar=grabar)
    c.texto = salida
    return c


def claves_falsas(monkeypatch, guardadas=None):
    guardadas = {} if guardadas is None else guardadas
    monkeypatch.setattr(B.CL, "obtener", lambda n, *a: guardadas.get(n))
    monkeypatch.setattr(B.CL, "guardar", lambda n, v, *a: (guardadas.__setitem__(n, v), ("archivo", "un archivo"))[1])
    return guardadas


def test_validar_clave_casos():
    assert B.validar_clave("k", respuesta(200))[0] is True
    assert B.validar_clave("k", respuesta(403))[0] is False
    assert B.validar_clave("k", respuesta(429))[0] is True
    assert B.validar_clave("k", respuesta(503))[0] is None
    assert B.validar_clave("k", sin_red)[0] is None


def test_clave_buena_se_guarda(tmp_path, monkeypatch):
    g = claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas(), ["AIzaBUENA"])
    c.paso_clave()
    assert g == {"gemini": "AIzaBUENA"} and c.resultado["clave"] == "guardada"
    assert any("aistudio.google.com/apikey" in t for t in c.texto)


def test_clave_mala_no_se_guarda_y_reintenta(tmp_path, monkeypatch):
    g = claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas(), ["mala", "mala2", "mala3"], enviar=respuesta(403))
    c.paso_clave()
    assert g == {} and c.resultado["clave"] == "fallida"


def test_clave_sin_red_se_guarda_igual(tmp_path, monkeypatch):
    g = claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas(), ["AIzaX"], enviar=sin_red)
    c.paso_clave()
    assert g == {"gemini": "AIzaX"}


def test_clave_saltada(tmp_path, monkeypatch):
    g = claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas(), [""])
    c.paso_clave()
    assert g == {} and c.resultado["clave"] == "saltado" and any("lina clave gemini" in t for t in c.texto)


def test_la_clave_nunca_sale_por_pantalla(tmp_path, monkeypatch):
    claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas(), ["AIzaSECRETA123"])
    c.paso_clave()
    assert not any("SECRETA123" in t for t in c.texto)


def test_microfono_casos(tmp_path):
    c = charla(tmp_path, Teclas("s"), grabar=lambda s: 0.2)
    c.paso_microfono()
    assert c.resultado["microfono"] == "bien"
    c = charla(tmp_path, Teclas("s"), grabar=lambda s: 0.0)
    c.paso_microfono()
    assert c.resultado["microfono"] == "silencio"
    def roto(s):
        raise OSError("no hay dispositivo")
    c = charla(tmp_path, Teclas("s"), grabar=roto)
    c.paso_microfono()
    assert c.resultado["microfono"] == "fallo" and any("no hay dispositivo" in t for t in c.texto)
    c = charla(tmp_path, Teclas("n"))
    c.paso_microfono()
    assert c.resultado["microfono"] == "saltado"


def test_nombre_y_perfil(tmp_path):
    c = charla(tmp_path, Teclas("Marta", "3"))
    c.paso_nombre()
    c.paso_autonomia()
    assert c.aj.get("asistente", "nombre") == "Marta" and c.aj.get("autonomia", "perfil") == "prudente"


def test_intro_deja_todo_como_estaba(tmp_path):
    c = charla(tmp_path, Teclas("", ""))
    c.paso_nombre()
    c.paso_autonomia()
    assert c.aj.get("asistente", "nombre") == "Lina" and c.aj.get("autonomia", "perfil") == "autonomo"


def test_privacidad_en_la_bienvenida_pregunta_y_respeta_el_no(tmp_path):
    c = charla(tmp_path, Teclas("n"))
    c.paso_privacidad()
    assert c.aj.get("privacidad", "capturas") == "no"


def test_recorrido_completo_y_marca(tmp_path, monkeypatch):
    claves_falsas(monkeypatch)
    c = charla(tmp_path, Teclas("s", "", "2", "s"), ["AIzaOK"], grabar=lambda s: 0.3)
    marca = tmp_path / "marca.json"
    assert B.principal([], c, marca) == 0 and B.ya_hecha(marca)
    assert c.aj.get("autonomia", "perfil") == "equilibrado" and c.aj.get("privacidad", "capturas") == "si"


def test_sin_terminal_no_hace_nada(tmp_path):
    c = charla(tmp_path, Teclas())
    c.terminal = False
    assert B.principal([], c, tmp_path / "m.json") == 2 and not B.ya_hecha(tmp_path / "m.json")


def test_ctrl_c_a_medias_no_marca_como_hecha(tmp_path, monkeypatch):
    claves_falsas(monkeypatch)
    def corta(_=""):
        raise EOFError
    c = charla(tmp_path, corta, ["AIzaOK"])
    marca = tmp_path / "m.json"
    assert B.principal([], c, marca) == 1 and not B.ya_hecha(marca)


def test_aviso_sin_clave_una_vez_al_dia(tmp_path):
    r = tmp_path / "aviso"
    assert B.toca_avisar(r, ahora=1000)
    assert not B.toca_avisar(r, ahora=1000 + 3600)
    assert B.toca_avisar(r, ahora=1000 + 25 * 3600)
