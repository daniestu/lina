"""Las reglas que dependen del idioma (fase 8, paso 3): en español se comportan exactamente como antes; con otro idioma usan su tabla
y, si no la tiene, la española. Sin red ni sistema."""
import re
from datetime import datetime

import pytest

from lina.modulos import notas as NOT
from lina.nucleo import comandos as C
from lina.nucleo import constantes as CON
from lina.nucleo import grupos as G
from lina.nucleo import idioma as I
from lina.nucleo import resolver as RES
from lina.nucleo import rutas as RUT
from lina.nucleo import texto as TX


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        return self.idioma


@pytest.fixture
def en(monkeypatch):
    """Lina en inglés (sin que haya traducciones: lo que se prueba es que cada regla elige su tabla)."""
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))


@pytest.fixture
def es(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))


def test_segun_elige_la_tabla_del_idioma_y_si_falta_la_espanola(en):
    assert I.segun({"es": "hola", "en": "hello"}) == "hello"
    assert I.segun({"es": "hola", "fr": "salut"}) == "hola"


# --- instrucciones a la IA ---

def test_las_instrucciones_en_espanol_son_las_de_siempre(es):
    assert CON.instrucciones() == CON.INSTRUCCIONES and CON.INSTRUCCIONES.startswith("Eres un asistente por voz")
    assert "español de España" in CON.instrucciones()


def test_con_otro_idioma_las_instrucciones_salen_de_su_tabla(en, monkeypatch):
    monkeypatch.setattr(CON, "INSTRUCCIONES_POR_IDIOMA", {**CON.INSTRUCCIONES_POR_IDIOMA, "en": "You are a voice assistant."})
    assert CON.instrucciones() == "You are a voice assistant."
    monkeypatch.setattr(I, "IDIOMAS", ("es", "fr"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("fr"))
    assert CON.instrucciones() == CON.INSTRUCCIONES                     # un idioma sin instrucciones propias: el español


# --- fecha y números para la voz ---

def test_la_fecha_en_espanol_no_ha_cambiado(es):
    d = datetime(2026, 10, 17, 22, 49)
    assert TX.texto_fecha_hora(d) == ("Ahora mismo son las 22:49 del sábado 17 de octubre de 2026 (hora del equipo). "
                                      "Úsala tal cual para la hora, la fecha y los cálculos con ellas; no la inventes ni repitas una de antes.")


def test_la_fecha_con_otro_idioma_usa_su_formato(en, monkeypatch):
    monkeypatch.setattr(TX, "_FECHA_POR_IDIOMA", {**TX._FECHA_POR_IDIOMA, "en": lambda d: f"It is {d:%H:%M} on {d:%A}."})
    assert TX.texto_fecha_hora(datetime(2026, 10, 17, 22, 49)) == "It is 22:49 on Saturday."


def test_los_numeros_se_leen_en_palabras_solo_en_espanol(es):
    assert TX.numeros_a_palabras("162%") == "ciento sesenta y dos por ciento"
    assert TX.numeros_a_palabras("tienes 21 años") == "tienes veintiún años"


def test_con_otro_idioma_las_cifras_se_dejan_para_la_voz(en):
    assert TX.numeros_a_palabras("162% y 21 años") == "162% y 21 años"


# --- qué herramientas se ofrecen según lo que dices ---

def test_grupos_en_espanol_como_siempre(es):
    assert "sistema" in G.elegir("sube el volumen") and "juegos" in G.elegir("abre steam")
    assert G.elegir("cuéntame un chiste") == set()


def test_un_grupo_puede_tener_palabras_por_idioma(en):
    G.registrar_grupo("prueba_idioma", ["herramienta_x"], "grupo de prueba", palabras={"es": r"\bhola\b", "en": r"\bhello\b"})
    try:
        assert "prueba_idioma" in G.elegir("hello there") and "prueba_idioma" not in G.elegir("hola amigo")
    finally:
        G.quitar_grupo("prueba_idioma")
    assert "prueba_idioma" not in G.GRUPOS


def test_un_grupo_con_palabras_solo_en_espanol_funciona_en_cualquier_idioma(en):
    G.registrar_grupo("prueba_idioma2", ["herramienta_x"], "grupo de prueba", palabras=r"\bhola\b")
    try:
        assert "prueba_idioma2" in G.elegir("hola amigo")
    finally:
        G.quitar_grupo("prueba_idioma2")


def test_quitar_un_grupo_olvida_tambien_sus_palabras_compiladas(es):
    G.registrar_grupo("prueba_idioma3", ["h"], "d", palabras=r"\buno\b")
    assert "prueba_idioma3" in G.elegir("uno")
    G.quitar_grupo("prueba_idioma3")
    G.registrar_grupo("prueba_idioma3", ["h"], "d", palabras=r"\bdos\b")
    try:
        assert "prueba_idioma3" not in G.elegir("uno") and "prueba_idioma3" in G.elegir("dos")
    finally:
        G.quitar_grupo("prueba_idioma3")


# --- enseñar alias ---

def test_alias_en_espanol_como_siempre(es):
    assert C.entender_alias("Cuando oigas cait quiero decir Kate") == ("aprender", "cait", "Kate")
    assert C.entender_alias("olvida el alias cait") == ("olvidar", "cait")
    assert C.entender_alias("recuerda que mañana es lunes") is None


def test_alias_con_las_frases_de_otro_idioma(en, monkeypatch):
    ingles = (re.compile(r"^when i say (?P<oido>.+?) i mean (?P<sig>.+)$", re.I), re.compile(r"^(?!x)x"), re.compile(r"^(?!x)x"),
              re.compile(r"^forget (?P<oido>.+)$", re.I))
    monkeypatch.setattr(C, "_ALIAS_POR_IDIOMA", {**C._ALIAS_POR_IDIOMA, "en": ingles})
    assert C.entender_alias("When I say cait I mean Kate") == ("aprender", "cait", "Kate")
    assert C.entender_alias("forget cait") == ("olvidar", "cait")
    assert C.entender_alias("Cuando oigas cait quiero decir Kate") is None            # las frases de otro idioma no valen


# --- el archivo de palabras (sí/no, cancelar, modo profundo…) ---

def test_el_archivo_de_palabras_es_el_de_siempre_en_espanol_y_si_falta_el_del_idioma(es, en, tmp_path, monkeypatch):
    monkeypatch.setattr(RUT, "CONFIG", tmp_path / "config")
    monkeypatch.setattr(RUT, "DEFECTOS", tmp_path / "fabrica")
    assert C.archivo() == C.ARCHIVO                                                   # sin comandos.en.txt, el español


def test_el_archivo_de_palabras_del_idioma(en, tmp_path, monkeypatch):
    monkeypatch.setattr(RUT, "CONFIG", tmp_path)
    monkeypatch.setattr(RUT, "DEFECTOS", tmp_path / "fabrica")
    (tmp_path / "comandos.en.txt").write_text("[confirmar_si_al_principio]\nyes\nsure\n", encoding="utf-8")
    assert C.archivo().name == "comandos.en.txt"


def test_las_palabras_de_si_cambian_con_el_idioma(tmp_path, monkeypatch):
    (tmp_path / "comandos.en.txt").write_text("[confirmar_si_al_principio]\nyes\nsure\n", encoding="utf-8")
    monkeypatch.setattr(RUT, "CONFIG", tmp_path)
    monkeypatch.setattr(RUT, "DEFECTOS", tmp_path / "fabrica")
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(C, "_cache", {"marca": "sin leer", "datos": None})
    monkeypatch.setattr(C, "log", lambda m: None)
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    assert C.es_afirmativo("yes, do it") is True
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))
    assert C.es_afirmativo("yes, do it") is False and C.es_afirmativo("sí, hazlo") is True      # al volver al español, se vuelve a leer su archivo


# --- notas y órdenes de abrir ---

def test_las_notas_ignoran_las_palabras_vacias_de_cada_idioma(es, monkeypatch):
    assert NOT._palabras("la nota de la compra") == ["compra"]
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    monkeypatch.setattr(NOT, "_PARAR_POR_IDIOMA", {**NOT._PARAR_POR_IDIOMA, "en": {"the", "of", "note"}})
    assert NOT._palabras("the note of shopping") == ["shopping"]


def test_abrir_un_programa_en_espanol_como_siempre(es):
    assert RES._motivo_es_abrir("Abrir Dolphin") is True and RES._motivo_es_abrir("Cambiar el volumen") is False


# --- el inglés entregado (fase 8, paso 5) ---

def test_el_ingles_se_puede_elegir_y_tiene_todo_lo_que_hace_falta():
    from lina.voz import voces as V
    assert "en" in I.IDIOMAS
    assert I.POR_DEFECTO in CON.INSTRUCCIONES_POR_IDIOMA and "en" in CON.INSTRUCCIONES_POR_IDIOMA
    assert "Always answer in English" in CON.INSTRUCCIONES_POR_IDIOMA["en"]
    assert V.POR_DEFECTO["en"] in V.CATALOGO["en"] and I.comprobar("en") == []
    for tabla in (TX._FECHA_POR_IDIOMA, C._ALIAS_POR_IDIOMA, NOT._PARAR_POR_IDIOMA, RES._LANZAMIENTO_POR_IDIOMA, G._VERBOS_POR_IDIOMA):
        assert "en" in tabla
    for g, patron in G._PALABRAS.items():
        assert isinstance(patron, dict) and "en" in patron, g


def test_el_catalogo_ingles_cubre_todos_los_textos_envueltos():
    """Cada T("…") con texto literal tiene su traducción inglesa (y cada traducción corresponde a algún texto)."""
    import ast
    from pathlib import Path
    raiz = Path(I.__file__).parent.parent
    textos = set()
    for f in raiz.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "T" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                textos.add(n.args[0].value)
    cat = I.catalogo("en")
    assert textos - set(cat) == set() and set(cat) - textos == set()


def test_con_lina_en_ingles_se_traduce_y_las_redes_de_seguridad_entienden_ingles(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    monkeypatch.setattr(I, "_catalogos", {})
    assert I.T("No te he oído.") == "I did not hear you."
    assert I.T("Recordatorio: {texto}.", texto="tea") == "Reminder: tea."
    assert TX.afirma_hecho("I've installed it, all set.") and TX.afirma_hecho("Done.")
    assert not TX.afirma_hecho("Which one do you want me to install?")
    assert TX.admite_duda("I couldn't verify that it worked.") and not TX.admite_duda("It is installed.")
    assert TX.PIDE_CONFIRMACION.search("Shall I install it?") and not TX.PIDE_CONFIRMACION.search("It is installed.")
    assert "Eres un asistente" not in CON.instrucciones() and CON.instrucciones().startswith("You are a voice assistant")
    assert "It is now 22:49" in TX.texto_fecha_hora(datetime(2026, 10, 17, 22, 49))
    assert G.elegir("turn up the volume") == {"sistema"} and "juegos" in G.elegir("open steam")
    assert C.entender_alias("When I say cait I mean Kate") == ("aprender", "cait", "Kate")
    assert C.quiere_cancelar("stop") and C.quiere_cancelar("cancel that please") and not C.quiere_cancelar("stop the music and play jazz")
    assert RES._motivo_es_abrir("Open Dolphin") is True and RES._motivo_es_abrir("Change the volume") is False
    assert NOT._palabras("the note about shopping") == ["shopping"]


def test_el_archivo_de_palabras_ingles_entregado_no_tiene_avisos():
    from pathlib import Path
    ruta = Path(RUT.DEFECTOS) / "comandos.en.txt"
    secciones, avisos = C._parsear(ruta.read_text(encoding="utf-8"))
    assert avisos == [] and set(C.SECCIONES) <= set(secciones)
