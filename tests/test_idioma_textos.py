"""Los textos fijos que Lina muestra (fase 8, paso 4): en español salen como siempre y con un catálogo cambian. Sin red ni sistema."""
import pytest

from lina.nucleo import ia_activa as IA
from lina.nucleo import ia_cli as CLI
from lina.nucleo import idioma as I


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        return self.idioma


@pytest.fixture
def en(tmp_path, monkeypatch):
    (tmp_path / "en.toml").write_text(
        '"falta la clave: `lina clave {nombre}`" = "key missing: `lina clave {nombre}`"\n'
        '"Lista para usar." = "Ready to use."\n'
        '"Proveedor: {nombre}" = "Provider: {nombre}"\n', encoding="utf-8")
    monkeypatch.setattr(I, "CARPETA", tmp_path)
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "_catalogos", {})
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))


@pytest.fixture
def es(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))


def test_ia_cli_con_espanol_sigue_igual(es):
    assert I.T("Proveedor: {nombre}", nombre="gemini") == "Proveedor: gemini"
    assert I.T("Lista para usar.") == "Lista para usar."


def test_el_texto_de_ia_cli_cambia_con_el_catalogo(en):
    assert I.T("Lista para usar.") == "Ready to use."
    assert I.T("Proveedor: {nombre}", nombre="gemini") == "Provider: gemini"


def test_la_ayuda_de_ia_sin_traducir_sale_en_espanol(en):
    assert I.T(CLI.AYUDA) == CLI.AYUDA


def test_los_estados_de_ia_activa_se_traducen(en):
    a = IA.Activa.__new__(IA.Activa)
    a.nombre = "openai"
    fuente = open(IA.__file__, encoding="utf-8").read()
    assert 'T("falta la clave: `lina clave {nombre}`"' in fuente


def test_ya_no_se_pide_reiniciar_siempre():
    fuente = open(CLI.__file__, encoding="utf-8").read()
    assert "Se aplica en tu siguiente petición" in fuente
