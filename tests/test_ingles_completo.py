# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El inglés de punta a punta (fase 8, opción B): lo que Lina dice en la terminal, las órdenes del manos libres, los recordatorios, las redes de
seguridad y los manuales. Sin red ni sistema."""
from datetime import datetime

import pytest

from lina.modulos import recordatorios as REC
from lina.nucleo import clasificador as CLA
from lina.nucleo import idioma as I
from lina.nucleo import privacidad as PRI
from lina.nucleo import privilegios as PRIV
from lina.voz import manos_libres as ML


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        return self.idioma


@pytest.fixture
def en(monkeypatch):
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))


@pytest.fixture
def es(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))


REF = datetime(2026, 10, 18, 10, 0)


# --- marcadores y tablas ---

def test_n_no_traduce_pero_t_si(en):
    assert I.N_("Hecho.") == "Hecho." and I.T(I.N_("Hecho.")) == "Done."


def test_por_idioma_delega_en_la_tabla_activa(es, monkeypatch):
    import re
    tabla = I.PorIdioma({"es": re.compile("hola"), "en": re.compile("hello")})
    assert tabla.search("hola mundo") and not tabla.search("hello world")
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    assert tabla.search("hello world") and not tabla.search("hola mundo")


def test_el_catalogo_ingles_es_valido():
    assert I.comprobar("en") == []


# --- terminal en inglés ---

def test_las_ayudas_salen_en_ingles(en):
    from lina import __main__ as M
    from lina.nucleo import ajustes as AJ
    assert "voice assistant for the Linux desktop" in I.T(M.AYUDA, version="x")
    assert "shows all settings" in I.T(AJ.AYUDA)


def test_las_ayudas_en_espanol_no_cambian(es):
    from lina.nucleo import ajustes as AJ
    assert I.T(AJ.AYUDA) == AJ.AYUDA


def test_el_manual_de_privacidad_sale_en_el_idioma_activo(en, tmp_path):
    salida = []
    class Aj:
        def get(self, *a):
            return "preguntar"
    PRI.principal([], salida=salida.append, ajustes=Aj(), es_terminal=False)
    assert "what leaves your computer" in "\n".join(salida)


def test_el_manual_de_privacidad_tiene_las_mismas_secciones_en_los_dos_idiomas():
    es_md = (PRI.MANUAL).read_text(encoding="utf-8")
    en_md = PRI.MANUAL.with_name("privacidad.en.md").read_text(encoding="utf-8")
    assert es_md.count("\n## ") == en_md.count("\n## ") and es_md.count("|---|") == en_md.count("|---|")


def test_la_frase_de_acceso_total_vale_en_los_dos_idiomas(en):
    assert I.T(PRIV.FRASE_TOTAL) == "GRANT FULL ACCESS"
    assert I.T(PRIV.FRASE_TOTAL) != PRIV.FRASE_TOTAL and PRIV.FRASE_TOTAL == "DAR ACCESO TOTAL"


# --- manos libres ---

@pytest.mark.parametrize("frase, esperado", [
    ("what's your name", ("pregunta_nombre",)),
    ("your name is Jarvis", ("nombre", "jarvis")),
    ("turn off hands free mode", ("desactivar",)),
    ("turn on hands free mode", ("activar",)),
])
def test_ordenes_del_manos_libres_en_ingles(en, frase, esperado):
    assert ML.entender_orden(frase) == esperado


def test_ordenes_del_manos_libres_en_espanol_siguen_igual(es):
    assert ML.entender_orden("cómo te llamas") == ("pregunta_nombre",)
    assert ML.entender_orden("te llamas Jarvis") == ("nombre", "jarvis")


# --- recordatorios ---

@pytest.mark.parametrize("frase, esperado", [
    ("in 10 minutes", datetime(2026, 10, 18, 10, 10)),
    ("tomorrow at 9", datetime(2026, 10, 19, 9, 0)),
    ("tomorrow at 9 pm", datetime(2026, 10, 19, 21, 0)),
    ("in two hours", datetime(2026, 10, 18, 12, 0)),
    ("today at 5 pm", datetime(2026, 10, 18, 17, 0)),
])
def test_recordatorios_entienden_el_cuando_en_ingles(en, frase, esperado):
    assert REC.parse_cuando(frase, REF) == esperado


def test_recordatorios_dicen_la_hora_en_ingles(en):
    assert REC.humano(datetime(2026, 10, 19, 9, 0), REF) == "tomorrow at 9 am"
    assert REC.humano(datetime(2026, 10, 18, 17, 30), REF) == "today at 5:30 pm"


def test_recordatorios_en_espanol_siguen_igual(es):
    assert REC.parse_cuando("mañana a las 9", REF) == datetime(2026, 10, 19, 9, 0)


# --- red de seguridad ---

@pytest.mark.parametrize("texto", ["format the whole disk", "wipe the entire system", "formatea el disco entero"])
def test_la_destruccion_total_se_detecta_en_cualquier_idioma(es, texto):
    assert CLA.destruccion_total(texto)


def test_lo_normal_no_es_destruccion_total(es):
    assert not CLA.destruccion_total("delete the temporary file") and not CLA.destruccion_total("borra el archivo temporal")


# --- voces ---

def test_toda_voz_del_catalogo_es_de_calidad_media_o_alta():
    from lina.voz import voces as V
    for idioma, voces in V.CATALOGO.items():
        assert V.POR_DEFECTO[idioma] in voces
        for nombre, ficha in voces.items():
            assert ficha["modelo"].rsplit("-", 1)[-1] in ("medium", "high"), nombre


def test_las_voces_inglesas_no_son_las_descartadas_por_licencia():
    from lina.voz import voces as V
    for nombre in V.CATALOGO["en"]:
        assert not any(x in nombre for x in ("lessac", "amy", "hfc", "ryan", "arctic", "libritts", "joe")), nombre
