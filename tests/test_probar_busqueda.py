# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-busqueda`: el juez, el criterio escrito antes (18 de 20 con Tavily o con la de pago; sin criterio solo con la gratuita), los errores del
servicio aparte y el usuario nuevo de verdad (ajustes de fábrica en una carpeta temporal y solo las claves del nivel). Sin IA ni red: la pregunta se simula."""
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import fuentes as FUE
from lina.nucleo import probar_busqueda as PB
from lina.nucleo import rutas as RUT

BUSQUEDA = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (son solo información…):\n\n[1] Poción (uesp.net) https://vertexaisearch/a\nectoplasma")
WIKI = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…):\n\n[1] Potion (elderscrolls.fandom.com) https://elderscrolls.fandom.com/wiki/P\nx\n\nCONTENIDO DE LA PÁGINA …")
LEIDA = ("leer_web", {"url": "https://www.marca.com/f1"}, "CONTENIDO DE LA PÁGINA (de fuera): …")
FALLIDA = ("buscar_web", {"consulta": "x"}, "NO SE HA PODIDO BUSCAR: no tienes clave de Tavily.")


@pytest.mark.parametrize("dicho, acciones, nota", [
    (["Según la UESP, se hace con ectoplasma."], [BUSQUEDA], "bien"),
    (["Según la wiki de Elder Scrolls, lleva ectoplasma."], [WIKI], "bien"),
    (["Lo dice Marca: ganó Verstappen."], [LEIDA], "bien"),
    (["Se hace con ectoplasma."], [BUSQUEDA], "mal"),                                  # no nombra la web
    (["Según la UESP, se hace con ectoplasma."], [], "mal"),                          # la web no salió de ninguna búsqueda: inventada
    (["Según la UESP, se hace con ectoplasma."], [FALLIDA], "mal"),
    (["No tengo acceso a internet, pero creo que es ectoplasma."], [BUSQUEDA], "mal"),
    (["No lo sé."], [BUSQUEDA], "mal"),
    ([], [BUSQUEDA], "mal"),
    (["(cortada por tiempo)"], [BUSQUEDA], "mal"),
])
def test_el_juez(dicho, acciones, nota):
    assert PB.juzgar(dicho, acciones)[0] == nota


def test_se_ha_publicado_no_cuenta_como_no_lo_se():
    assert PB.juzgar(["Según la UESP, se ha publicado la versión 1.2."], [BUSQUEDA])[0] == "bien"


@pytest.mark.parametrize("nivel, notas, pasa", [
    ("tavily", ["bien"] * 18 + ["mal"] * 2, True),
    ("tavily", ["bien"] * 17 + ["mal"] * 3, False),
    ("pago", ["bien"] * 18 + ["api"] * 2, True),                                       # las del servicio no cuentan como fallo…
    ("pago", ["bien"] * 17 + ["api"] * 3, False),                                      # …pero con más de 2 la pasada no vale
    ("gratis", ["mal"] * 20, True),                                                    # solo la gratuita: se informa, sin criterio
])
def test_el_criterio_escrito_antes(nivel, notas, pasa):
    assert PB.veredicto(notas, nivel)[0] is pasa
    assert PB.CRITERIO == {"gratis": None, "tavily": 18, "pago": 18} and len(PB.PREGUNTAS) == 20


def test_las_preguntas_tipicas_estan():
    texto = " ".join(PB.PREGUNTAS).lower()
    assert "poción" in texto and "skyrim" in texto and "lol" in texto and "precio" in texto and "noticia" in texto


def test_el_usuario_nuevo_tiene_ajustes_de_fabrica_y_solo_las_claves_del_nivel(tmp_path, monkeypatch):
    config_antes, estado_antes = RUT.CONFIG, RUT.ESTADO
    reales = {"gemini": "G", "gemini_pago": "P", "tavily": "T"}
    with PB.usuario_nuevo("tavily", obtener_real=reales.get) as claves:
        assert claves == {"gemini": "G", "tavily": "T"}
        assert CL.obtener("gemini_pago") == "" and CL.obtener("tavily") == "T" and FUE.listar() == []
        assert RUT.CONFIG != config_antes and RUT.ESTADO != estado_antes
        assert AJ.actuales(log=lambda m: None).get("ia", "busqueda") == "auto"       # de fábrica, aunque el tuyo diga otra cosa
        carpeta = RUT.CONFIG.parent
    assert RUT.CONFIG == config_antes and RUT.ESTADO == estado_antes and not carpeta.exists()


def _principal(monkeypatch, respuestas, nivel="tavily", n=None):
    monkeypatch.setattr(PB, "usuario_nuevo", _sin_cambios)
    salida, esperas = [], []
    a = MagicMock(busquedas_hechas=[])
    turnos = iter(respuestas)
    r = PB.principal([nivel] + ([str(n)] if n else []), salida.append, preparar=lambda: (MagicMock(), a, []),
                     pasar_pregunta=lambda frase, A, a, llamadas: next(turnos), dormir=esperas.append)
    return r, "\n".join(salida), esperas


class _sin_cambios:
    def __init__(self, nivel):
        pass

    def __enter__(self):
        return {"gemini": "G", "tavily": "T"}

    def __exit__(self, *a):
        return False


def test_un_503_se_repite_con_pausa_y_no_cuenta(monkeypatch):
    bien = (["Según la UESP, ectoplasma."], [BUSQUEDA], ["ok"], 1.0)
    caida = ([], [], ["503"], 1.0)
    r, texto, esperas = _principal(monkeypatch, [caida, caida, bien], n=1)
    assert r == 1 and esperas[:2] == [20, 40] and "bien" in texto and "error del servicio" in texto


def test_si_el_servicio_sigue_caido_sale_aparte(monkeypatch):
    caida = ([], [], ["429"], 1.0)
    r, texto, _ = _principal(monkeypatch, [caida] * 4, n=1)
    assert "api" in texto and "1 fuera por errores del servicio" in texto


def test_un_fallo_de_busqueda_no_se_repite(monkeypatch):
    mal = (["No lo sé."], [FALLIDA], ["ok"], 1.0)
    r, texto, esperas = _principal(monkeypatch, [mal], n=1)
    assert esperas == [] and texto.count("mal ") == 1


def test_sin_la_clave_del_nivel_no_empieza(monkeypatch):
    class SinTavily(_sin_cambios):
        def __enter__(self):
            return {"gemini": "G", "tavily": ""}
    monkeypatch.setattr(PB, "usuario_nuevo", SinTavily)
    salida = []
    assert PB.principal(["tavily"], salida.append, preparar=MagicMock(side_effect=AssertionError)) == 2 and "lina clave tavily" in salida[0]


def test_ningun_comando_ni_la_pantalla(monkeypatch):
    """Solo buscar y leer: lo demás recibe el texto de que en la prueba no se ejecuta nada."""
    assert "ejecutar_comando" not in PB.PERMITIDAS and "mirar_pantalla" not in PB.PERMITIDAS and "ver_pantalla" not in PB.PERMITIDAS
    assert {"buscar_web", "leer_web"} <= PB.PERMITIDAS
