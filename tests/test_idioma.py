"""La capa de idioma (fase 8): el ajuste, T() y los catálogos de traducción, sin tocar el sistema."""
import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import idioma as I


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        assert (seccion, clave) == ("asistente", "idioma")
        return self.idioma


@pytest.fixture
def en(tmp_path, monkeypatch):
    """Un idioma «en» de prueba, con un catálogo en una carpeta temporal."""
    (tmp_path / "en.toml").write_text(
        '"Lista para usar" = "Ready to use"\n'
        '"Hola, {nombre}" = "Hello, {nombre}"\n'
        '"Quedan {n} archivos" = "{n} files left"\n'
        '"Mal escrita {nombre}" = "Badly written {otro}"\n'
        '"Vacía" = ""\n', encoding="utf-8")
    monkeypatch.setattr(I, "CARPETA", tmp_path)
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "_catalogos", {})
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    return tmp_path


def test_el_idioma_por_defecto_es_el_espanol():
    assert AJ.ESQUEMA["asistente"]["idioma"][0] == "es" and I.POR_DEFECTO == "es"
    assert I.IDIOMAS == AJ.IDIOMAS == ("es", "en")


def test_en_espanol_el_texto_sale_tal_cual_y_con_sus_huecos(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))
    assert I.T("Lista para usar") == "Lista para usar"
    assert I.T("Hola, {nombre}", nombre="Dani") == "Hola, Dani"
    assert I.T("Llaves {{literales}}") == "Llaves {{literales}}"                  # sin datos no se toca
    assert I.T("Llaves {{literales}} y {n}", n=3) == "Llaves {literales} y 3"


@pytest.mark.parametrize("valor", ["fr", "", None, 7])
def test_un_idioma_desconocido_o_roto_cae_al_espanol(monkeypatch, valor):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes(valor))
    assert I.actual() == "es"


def test_el_codigo_del_idioma_se_normaliza(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes(" EN "))
    assert I.actual() == "en"


def test_un_config_roto_no_deja_a_lina_muda(monkeypatch):
    def roto():
        raise RuntimeError("config.toml ilegible")
    monkeypatch.setattr(I, "LECTOR", roto)
    assert I.actual() == "es" and I.T("Hola") == "Hola"


def test_con_otro_idioma_se_traduce(en):
    assert I.actual() == "en"
    assert I.T("Lista para usar") == "Ready to use"
    assert I.T("Hola, {nombre}", nombre="Dani") == "Hello, Dani"
    assert I.T("Quedan {n} archivos", n=4) == "4 files left"


def test_sin_traduccion_sale_el_espanol(en):
    assert I.T("Algo que nadie ha traducido") == "Algo que nadie ha traducido"
    assert I.T("Quedan {n} cosas", n=2) == "Quedan 2 cosas"
    assert I.T("Vacía") == "Vacía"                                                # una traducción en blanco no cuenta


def test_una_traduccion_mal_escrita_no_rompe_nada(en):
    assert I.T("Mal escrita {nombre}", nombre="Dani") == "Mal escrita Dani"


def test_un_idioma_sin_archivo_o_con_archivo_roto_equivale_al_espanol(en):
    (en / "en.toml").write_text("esto no es toml = = =", encoding="utf-8")
    I._catalogos.clear()
    assert I.catalogo("en") == {} and I.T("Lista para usar") == "Lista para usar"
    I._catalogos.clear()
    (en / "en.toml").unlink()
    assert I.catalogo("en") == {}


def test_comprobar_encuentra_huecos_que_no_coinciden(en):
    problemas = I.comprobar("en")
    assert len(problemas) == 1 and "Mal escrita" in problemas[0]
    assert I.comprobar("es") == []


def test_comprobar_encuentra_llaves_sin_cerrar(tmp_path, monkeypatch):
    (tmp_path / "en.toml").write_text('"Hola {nombre" = "Hello {name"\n', encoding="utf-8")
    monkeypatch.setattr(I, "CARPETA", tmp_path)
    monkeypatch.setattr(I, "_catalogos", {})
    assert len(I.comprobar("en")) == 1


def test_los_catalogos_que_se_entregan_estan_bien():
    """Cada idioma que viaja en el paquete tiene que estar bien escrito (huecos iguales en el texto y en su traducción)."""
    for archivo in sorted(I.CARPETA.glob("*.toml")):
        I._catalogos.pop(archivo.stem, None)
        assert I.comprobar(archivo.stem) == [], archivo.name


def test_con_los_ajustes_de_verdad(tmp_path):
    ajustes = AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)
    assert I.actual(lambda: ajustes) == "es"
    ajustes.establecer("asistente", "idioma", "es")
    assert I.actual(lambda: ajustes) == "es"
    ajustes.establecer("asistente", "idioma", "en")
    assert I.actual(lambda: ajustes) == "en"
    with pytest.raises(Exception):                                  # un idioma que no está entregado no se puede elegir
        ajustes.establecer("asistente", "idioma", "fr")


# --- voces y reconocimiento de voz según el idioma ---

@pytest.fixture
def voces_en(en, monkeypatch):
    from lina.voz import voces as V
    ficha = {"modelo": "en_US-prueba-medium", "carpeta": "en/en_US/prueba/medium", "locutor": None, "descripcion": "Prueba · inglés"}
    monkeypatch.setattr(V, "CATALOGO", {**V.CATALOGO, "en": {"en_US-prueba-medium": ficha}})
    monkeypatch.setattr(V, "POR_DEFECTO", {**V.POR_DEFECTO, "en": "en_US-prueba-medium"})
    return V


def test_las_voces_que_se_ofrecen_son_las_del_idioma_activo(voces_en):
    V = voces_en
    assert V.idioma() == "en" and list(V.catalogo()) == ["en_US-prueba-medium"] and V.por_defecto() == "en_US-prueba-medium"


def test_sin_voces_en_ese_idioma_se_usan_las_espanolas(en, monkeypatch):
    from lina.voz import voces as V
    monkeypatch.setattr(I, "IDIOMAS", ("es", "fr"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("fr"))
    assert V.idioma() == "es" and "es_MX-claude-high" in V.catalogo() and V.por_defecto() == V.VOZ_POR_DEFECTO


def test_la_voz_elegida_de_otro_idioma_se_sustituye_por_la_de_este(voces_en, monkeypatch):
    V = voces_en

    def con_voz(nombre):
        class Falsos:
            def get(self, seccion, clave):
                return nombre
        monkeypatch.setattr(V.AJ, "actuales", lambda log=None: Falsos())
    con_voz("es_MX-claude-high")                              # la de fábrica en español, con Lina en inglés
    assert V.voz_elegida() == "en_US-prueba-medium"
    con_voz("en_US-prueba-medium")
    assert V.voz_elegida() == "en_US-prueba-medium"
    con_voz("mi_voz_propia")                                  # una voz que el usuario instaló por su cuenta no se toca
    assert V.voz_elegida() == "mi_voz_propia"


def test_el_reconocimiento_de_voz_no_tiene_el_idioma_fijo():
    from pathlib import Path
    fuente = (Path(I.__file__).parent / "asistente.py").read_text(encoding="utf-8")
    assert 'language="es"' not in fuente and "language=IDI.actual()" in fuente


def test_un_hueco_puede_llamarse_texto(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))
    assert I.T("Recordatorio: {texto}.", texto="té") == "Recordatorio: té."
