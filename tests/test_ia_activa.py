"""Qué IA está activa (sección [ia]), `lina ia` y la elección de proveedor, sin red ni llavero."""
import json

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import ia_activa as IAC
from lina.nucleo import ia_cli as CLI
from lina.nucleo import proveedor_openai as POA
from lina.nucleo import proveedores as P


@pytest.fixture
def aj(tmp_path, monkeypatch):
    ajustes = AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)
    monkeypatch.setattr(IAC, "LECTOR", lambda: ajustes)
    claves = {}
    monkeypatch.setattr(CL, "obtener", lambda nombre, **k: claves.get(nombre))
    ajustes.claves = claves
    return ajustes


def poner(aj, **valores):
    for k, v in valores.items():
        aj.establecer("ia", k, v)


def test_por_defecto_es_gemini_con_los_modelos_de_siempre(aj):
    a = IAC.actual()
    assert a.nombre == "gemini" and a.proveedor is P.obtener("gemini")
    assert IAC.modelos("rapido") == ["gemini-flash-lite-latest", "gemini-flash-latest"]
    assert IAC.modelos("profundo")[0] == "gemini-flash-latest" and IAC.modelos("mini") == IAC.modelos("rapido")


def test_gemini_con_modelo_propio(aj):
    poner(aj, modelo_rapido="gemini-x", modelo_profundo="gemini-y")
    assert IAC.modelos("rapido") == ["gemini-x"] and IAC.modelos("mini") == ["gemini-x"] and IAC.modelos("profundo") == ["gemini-y"]


def test_anthropic_trae_modelos_recomendados_y_pide_clave(aj):
    poner(aj, proveedor="anthropic")
    a = IAC.actual()
    assert a.rapido == ["claude-haiku-5-5"] and a.profundo == ["claude-sonnet-5-5"] and a.mini == a.rapido
    assert a.listo() == (False, "falta la clave: `lina clave anthropic`")
    aj.claves["anthropic"] = "sk-x"
    assert a.listo() == (True, "") and a.clave() == "sk-x"


def test_openai_exige_indicar_el_modelo(aj):
    poner(aj, proveedor="openai")
    a = IAC.actual()
    assert a.rapido == [] and "falta indicar el modelo" in a.listo()[1]
    poner(aj, modelo_rapido="un-modelo")
    aj.claves["openai"] = "sk-y"
    a = IAC.actual()
    assert a.listo() == (True, "") and a.profundo == ["un-modelo"] and isinstance(a.proveedor, POA.OpenAI) and a.proveedor.url_base == POA.URL_OPENAI


def test_servidor_local_no_necesita_clave(aj):
    poner(aj, proveedor="openai", modelo_rapido="llama3", url_base="http://localhost:11434/v1", razonamiento=True)
    a = IAC.actual()
    assert a.local and a.clave() == P.SIN_CLAVE and a.listo() == (True, "")
    assert a.proveedor.url_base == "http://localhost:11434/v1" and a.proveedor.razonamiento is True


def test_la_direccion_de_openai_no_cuenta_como_local(aj):
    poner(aj, proveedor="openai", modelo_rapido="m", url_base="https://api.openai.com/v1")
    assert not IAC.actual().local and IAC.actual().listo()[0] is False


def test_un_proveedor_desconocido_vuelve_a_gemini(aj):
    class Falso:
        def get(self, seccion, clave):
            return "inventado" if clave == "proveedor" else ""
    assert IAC.actual(lambda: Falso()).nombre == "gemini"


def test_cambiar_de_proveedor_es_un_cambio_sensible(aj):
    assert AJ.cambio_sensible("ia", "proveedor", "openai", aj) is True
    assert AJ.cambio_sensible("ia", "proveedor", "gemini", aj) is False        # no cambia nada
    assert AJ.cambio_sensible("ia", "url_base", "http://x", aj) is True
    assert AJ.cambio_sensible("ia", "modelo_rapido", "otro", aj) is False


def test_las_claves_nuevas_son_conocidas():
    assert "openai" in CL.CONOCIDAS and "anthropic" in CL.CONOCIDAS


# ------------------------------------------------------------------ lina ia
def salida():
    lineas = []
    return lineas, lineas.append


def test_estado_dice_que_falta(aj):
    lineas, s = salida()
    poner(aj, proveedor="anthropic")
    assert CLI.estado(salida=s) == 1
    texto = "\n".join(lineas)
    assert "Proveedor: anthropic" in texto and "falta la clave" in texto and "no controla el gasto en euros" in texto


def test_usar_cambia_los_ajustes_y_parte_de_cero(aj):
    lineas, s = salida()
    poner(aj, proveedor="anthropic", modelo_rapido="viejo")
    CLI.usar(["openai", "--modelo", "mi-modelo", "--url", "http://localhost:1234/v1", "--razonamiento"], ajustes=aj, salida=s)
    assert (aj.get("ia", "proveedor"), aj.get("ia", "modelo_rapido"), aj.get("ia", "url_base"), aj.get("ia", "razonamiento")) == \
        ("openai", "mi-modelo", "http://localhost:1234/v1", True)
    CLI.usar(["gemini"], ajustes=aj, salida=s)
    assert (aj.get("ia", "proveedor"), aj.get("ia", "modelo_rapido"), aj.get("ia", "url_base")) == ("gemini", "", "")      # nada del anterior se arrastra


def test_usar_rechaza_lo_que_no_entiende(aj):
    lineas, s = salida()
    assert CLI.usar(["nada"], ajustes=aj, salida=s) == 2
    assert CLI.usar(["anthropic", "--url", "http://x"], ajustes=aj, salida=s) == 2
    assert CLI.usar(["openai", "--raro"], ajustes=aj, salida=s) == 2


class R:
    def __init__(self, estado, datos):
        self.status_code, self.ok, self._d, self.text, self.headers = estado, estado < 400, datos, json.dumps(datos), {}

    def json(self):
        return self._d


def test_probar_informa_de_cada_capacidad(aj):
    poner(aj, proveedor="openai", modelo_rapido="m", url_base="http://localhost:1/v1")
    lineas, s = salida()
    respuestas = [
        R(200, {"choices": [{"message": {"content": "ok"}}]}),
        R(200, {"choices": [{"message": {"content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "anotar", "arguments": '{"numero": 7}'}}]}}]}),
        R(400, {"error": {"message": "este modelo no admite imágenes"}}),
    ]
    assert CLI.probar(salida=s, post=lambda *a, **k: respuestas.pop(0)) == 0
    texto = "\n".join(lineas)
    assert "Responde:      sí" in texto and "Herramientas:  sí" in texto and "Imágenes:      NO" in texto and "no admite imágenes" in texto


def test_probar_avisa_si_el_modelo_no_usa_herramientas(aj):
    poner(aj, proveedor="openai", modelo_rapido="m", url_base="http://localhost:1/v1")
    lineas, s = salida()
    ok = R(200, {"choices": [{"message": {"content": "claro"}}]})
    assert CLI.probar(salida=s, post=lambda *a, **k: ok) == 1
    assert "Herramientas:  NO" in "\n".join(lineas)


def test_probar_sin_clave_no_hace_peticiones(aj):
    poner(aj, proveedor="anthropic")
    lineas, s = salida()
    assert CLI.probar(salida=s, post=lambda *a, **k: 1 / 0) == 1 and "falta la clave" in lineas[0]


def test_modelos_lista_lo_que_ofrece_el_servicio(aj):
    poner(aj, proveedor="openai", modelo_rapido="m", url_base="http://localhost:1/v1")
    lineas, s = salida()
    llamadas = []

    def get(url, **k):
        llamadas.append(url)
        return R(200, {"data": [{"id": "b"}, {"id": "a"}]})
    assert CLI.modelos(salida=s, get=get) == 0
    assert llamadas == ["http://localhost:1/v1/models"] and lineas[1:] == ["  a", "  b"]


def test_cada_proveedor_sabe_listar_modelos():
    gemini = P.obtener("gemini").modelos("K", get=lambda *a, **k: R(200, {"models": [{"name": "models/g1", "supportedGenerationMethods": ["generateContent"]},
                                                                                 {"name": "models/emb", "supportedGenerationMethods": ["embedContent"]}]}))
    assert gemini == (["g1"], "")
    assert P.obtener("anthropic").modelos("K", get=lambda *a, **k: R(200, {"data": [{"id": "c1"}]})) == (["c1"], "")
    assert P.obtener("anthropic").modelos("K", get=lambda *a, **k: R(401, {"error": {"type": "authentication_error", "message": "mala"}}))[0] is None


# ------------------------------------------------------------------ lina doctor con otro proveedor
def test_doctor_nombra_el_proveedor_y_su_clave(aj):
    from lina.nucleo import doctor as D
    poner(aj, proveedor="anthropic")

    class Sonda(D.Sondas):
        def clave(self): return ""
    res = [r for r in D.comprobar(Sonda()) if r[1] in ("IA activa", "Clave de anthropic")]
    assert [(e, t) for e, t, *_ in res] == [(D.MAL, "IA activa"), (D.MAL, "Clave de anthropic")]
    assert all("lina " in arreglo for *_, arreglo in res)


def test_doctor_con_servidor_local_no_pide_clave(aj):
    from lina.nucleo import doctor as D
    poner(aj, proveedor="openai", modelo_rapido="llama3", url_base="http://localhost:11434/v1")

    class Sonda(D.Sondas):
        def clave(self): return ""
    res = {t: (e, d) for e, t, d, _ in D.comprobar(Sonda())}
    assert res["Clave de openai"][0] == D.OK and "servidor propio" in res["Clave de openai"][1] and res["IA activa"][0] == D.OK
    assert IAC.actual().servidor() == ("localhost", 11434)
