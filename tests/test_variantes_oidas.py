# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import pytest
from lina.nucleo import comandos as C


def _app(nombre, comando=None):
    comando = comando or nombre.lower()
    return {"nombre": nombre, "comando": comando, "es": "", "id": comando, "generico": "", "claves": ""}


APPS = [_app("Firefox"), _app("Brave", "brave"), _app("Kate"), _app("Dolphin"), _app("Steam"), _app("Avahi Zeroconf Browser", "avahi-discover")]


@pytest.mark.parametrize("dicho, esperado", [
    ("abre feir folks", "abre Firefox"),
    ("Abre fair fox.", "Abre Firefox."),
    ("ábreme gate", "ábreme Kate"),
    ("abre Torfin", "abre Dolphin"),
    ("abre ahí", "abre Brave"),
    ("abre ahí y busca gatos", "abre Brave y busca gatos"),
    ("abre el estim", "abre el Steam"),
    ("cierra feir folks", "cierra Firefox"),
])
def test_arregla_el_nombre_mal_oido_si_esta_instalado(dicho, esperado):
    nuevo, hechos = C.aplicar_variantes(dicho, APPS)
    assert nuevo == esperado and hechos


@pytest.mark.parametrize("dicho", [
    "abre ahí la carpeta de descargas",      # «ahí» es una palabra corriente: solo vale si la frase acaba o sigue con «y…»
    "abre gate de mi correo",
    "pon la música",                         # sin verbo de abrir/cerrar no se toca nada
    "dime qué es feir folks",
    "abre Firefox",                          # ya está bien dicho
    "abre Kate",
    "abre el navegador",
])
def test_no_toca_lo_que_no_es_un_nombre_mal_oido(dicho):
    assert C.aplicar_variantes(dicho, APPS) == (dicho, [])


def test_si_el_programa_no_esta_instalado_no_se_cambia():
    sin_firefox = [a for a in APPS if a["nombre"] != "Firefox"]
    assert C.aplicar_variantes("abre feir folks", sin_firefox) == ("abre feir folks", [])


def test_si_lo_dicho_ya_es_un_programa_tuyo_manda_el_tuyo():
    apps = APPS + [_app("Gate One", "gateone")]
    assert C.aplicar_variantes("abre gate one", apps) == ("abre gate one", [])


def test_solo_cambia_el_nombre_tras_el_verbo():
    nuevo, _ = C.aplicar_variantes("abre feir folks y cierra gate", APPS)
    assert nuevo == "abre Firefox y cierra Kate"


def test_las_variantes_no_se_pisan_entre_programas():
    vistos = {}
    for destino, oidos in C.VARIANTES_OIDAS.items():
        for o in oidos:
            k = C.normalizar(o)
            assert vistos.setdefault(k, destino) == destino, f"«{o}» sirve para dos programas"
