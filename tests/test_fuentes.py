# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""F1: guardar, ver y quitar las webs elegidas para cada tema. Las escribe solo el usuario y la IA no puede tocarlas. Con el archivo en tmp_path; sin red."""
import stat

import pytest

from lina.nucleo import clasificador as CLA
from lina.nucleo import fuentes as F
from lina.nucleo import ia as IA
from lina.nucleo import herramientas as H
from lina.nucleo import olvidar as OLV

TEMA = "recetas de refinería de No Man's Sky"
WEB = "https://nomanssky.fandom.com/wiki/Refining"


@pytest.fixture(autouse=True)
def archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ARCHIVO", tmp_path / "fuentes.json")
    return tmp_path / "fuentes.json"


def test_anadir_guarda_tema_direccion_y_dominio(archivo):
    fuente, frase = F.anadir(TEMA, WEB)
    assert fuente["id"] == "f1" and fuente["tema"] == TEMA and fuente["url"] == WEB and fuente["dominio"] == "nomanssky.fandom.com"
    assert "nomanssky.fandom.com" in frase and F.listar() == [fuente]
    assert stat.S_IMODE(archivo.stat().st_mode) == 0o600


@pytest.mark.parametrize("texto, url, dominio", [("nomanssky.fandom.com", "https://nomanssky.fandom.com", "nomanssky.fandom.com"),
                                                 ("https://www.ejemplo.es/a?lang=es#parte", "https://www.ejemplo.es/a?lang=es", "ejemplo.es"),
                                                 ("http://ejemplo.es/x?author=ana&monkey=1", "http://ejemplo.es/x?author=ana&monkey=1", "ejemplo.es")])
def test_direcciones_que_valen(texto, url, dominio):
    assert F.validar_direccion(texto) == (url, dominio)


@pytest.mark.parametrize("texto", ["", "no es una web", "ftp://ejemplo.es/x", "file:///etc/passwd", "https://usuario:clave" + "@ejemplo.es/", "https://usuario" + "@ejemplo.es/",
                                   "https://ejemplo.es/?token=abc", "https://ejemplo.es/?api_key=abc", "https://ejemplo.es/?a=1&password=x", "http://localhost:8080/",
                                   "http://192.168.1.10/", "https://ejemplo.es/?k=tvly-abcdefghijklmnopqrstuvwxyz"])
def test_direcciones_que_no(texto):
    with pytest.raises(ValueError):
        F.validar_direccion(texto)
    assert F.anadir(TEMA, texto)[0] is None and F.listar() == []


@pytest.mark.parametrize("tema", ["", "   ", "x" * 121, "mi contraseña del banco", "tema con clave tvly-abcdefghijklmnopqrstuvwxyz"])
def test_temas_que_no(tema):
    assert F.anadir(tema, WEB)[0] is None and F.listar() == []


def test_un_solo_tema_igual_y_tope():
    assert F.anadir(TEMA, WEB)[0]
    assert F.anadir("RECETAS de refineria de no man's sky", "https://otra.es")[0] is None
    for i in range(F.MAX_FUENTES - 1):
        assert F.anadir(f"tema número {i}", "https://ejemplo.es")[0]
    fuente, frase = F.anadir("uno más", "https://ejemplo.es")
    assert fuente is None and "máximo" in frase


def test_quitar_y_los_ids_no_se_reutilizan_mientras_haya_otros(archivo):
    a, _ = F.anadir("uno", "https://a.es")
    b, _ = F.anadir("dos", "https://b.es")
    assert F.quitar(a["id"])[0] and [f["id"] for f in F.listar()] == [b["id"]]
    assert F.anadir("tres", "https://c.es")[0]["id"] == "f3"
    assert F.quitar("f99")[0] is False
    assert F.quitar("todas")[0] and not archivo.exists() and F.quitar("todas")[0] is False


def test_un_archivo_roto_no_rompe_nada(archivo):
    archivo.write_text("{roto", encoding="utf-8")
    assert F.listar() == []
    archivo.write_text('[{"id": "f1"}, "x", {"id": "f2", "tema": "t", "url": "https://a.es", "dominio": "a.es"}]', encoding="utf-8")
    assert [f["id"] for f in F.listar()] == ["f2"]


def test_la_orden(capsys, monkeypatch):
    monkeypatch.setattr(F, "activas", lambda: True)
    salida = []
    assert F.principal([], salida.append) == 0 and "No hay ninguna fuente" in salida[-1]
    assert F.principal(["añadir", TEMA, WEB], salida.append) == 0
    assert F.principal([], salida.append) == 0 and "Tus fuentes (1 de 20)." == salida[-2] and TEMA in salida[-1] and WEB in salida[-1]
    assert F.principal(["quitar", "f1"], salida.append) == 0
    assert F.principal(["añadir", TEMA], salida.append) == 2 and F.principal(["otra"], salida.append) == 2 and F.principal(["quitar"], salida.append) == 2
    assert F.principal(["añadir", TEMA, "no vale"], salida.append) == 1


@pytest.mark.parametrize("comando", ["lina fuentes", 'lina fuentes añadir "x" https://mala.es', "lina fuentes quitar todas", "python3 -m lina fuentes", "cd /tmp && lina fuentes", 'lina fuentes probar "x"',
                                     "cat ~/.local/share/lina/fuentes.json", "echo x > ~/.local/share/lina/fuentes.json"])
def test_la_ia_no_puede_tocarlas(comando):
    assert CLA._bloqueado(comando), comando


def test_ninguna_herramienta_escribe_fuentes():
    assert not [d["name"] for d in H.DECLARACIONES if "fuente" in d["name"]]
    usar = F.declaracion_usar_fuente([{"id": "f1", "tema": "t"}])
    assert set(usar["parameters"]["properties"]) == {"id", "consulta"}                  # solo elige: ni dirección ni tema
    from pathlib import Path
    assert "FUE._cargar" not in Path(F.__file__).with_name("asistente.py").read_text(encoding="utf-8")


def test_sin_gemini_la_lista_dice_que_no_se_usan(monkeypatch):
    monkeypatch.setattr(F, "activas", lambda: False)
    salida = []
    F.principal(["añadir", TEMA, WEB], salida.append)
    F.principal([], salida.append)
    assert any("Con esta configuración no se usan" in s for s in salida)


def test_olvidar():
    assert "fuentes" in OLV.QUE and "fuentes" in OLV.TODO and OLV.QUE["fuentes"][1]()[0].name == "fuentes.json"


# ---------------------------------------------------------------- F2: añadirlas con una frase
URL_FRASE = "https://nomanssky.fandom.com/wiki/Refining"


@pytest.mark.parametrize("frase, esperado", [
    (f"Para las recetas de refinería de No Man's Sky usa esta página {URL_FRASE}.", ("anadir", TEMA, URL_FRASE)),
    (f"Para las recetas de refinería de No Man's Sky, usa esta página: {URL_FRASE}", ("anadir", TEMA, URL_FRASE)),
    ("Para las recetas de refinería de No Man's Sky, usa la página que tengo copiada.", ("copiada", TEMA)),
    ("Para las recetas de refinería de No Man's Sky usa el enlace que he copiado", ("copiada", TEMA)),
    ("Usa nomanssky.fandom.com para las recetas de refinería", ("anadir", "recetas de refinería", "nomanssky.fandom.com")),
    ("Cuando te pregunte por las recetas, usa la web nomanssky punto fandom punto com", ("anadir", "recetas", "nomanssky.fandom.com")),
    ("Para las recetas usa siempre la página ejemplo.es/wiki", ("anadir", "recetas", "ejemplo.es/wiki")),
    ("Para las recetas usa esta página", ("falta_web", "recetas")),
    ("Usa esta página", ("falta_tema",)),
    ("Para las recetas usa la web cosa rara", ("mala", "recetas")),
    ("Quita la última fuente.", ("quitar_ultima",)),
    ("Quita la fuente de recetas.", ("quitar", "recetas")),
    ("Borra la fuente de las recetas de refinería", ("quitar", "las recetas de refinería")),
    ("por favor, elimina mi fuente sobre recetas", ("quitar", "recetas")),
])
def test_entender_las_frases(frase, esperado):
    assert F.entender(frase) == esperado


@pytest.mark.parametrize("frase", ["Para la música usa Spotify", "Para jugar usa Proton", "¿Para las recetas puedes usar esta página?", "Para las recetas no uses esta página",
                                   "Recuerda que para las recetas uso esa web", "Usa esa web", "Abre No Man's Sky", "¿Cómo refino el ferrito?", "Quita la música", ""])
def test_lo_que_no_es_una_fuente_sigue_su_camino(frase):
    assert F.entender(frase) is None


def _nada():
    raise AssertionError("no debía mirar el portapapeles")


def test_guardar_repite_el_tema_el_dominio_hablado_y_como_quitarla():
    r = F.gestionar(("anadir", TEMA, URL_FRASE), "atajo", _nada)
    assert TEMA in r and "nomanssky punto fandom punto com" in r and "quita la última fuente" in r and "lina fuentes quitar f1" in r
    assert F.listar()[0]["url"] == URL_FRASE


def test_por_escrito_el_dominio_va_tal_cual():
    assert "nomanssky.fandom.com" in F.gestionar(("anadir", TEMA, URL_FRASE), "texto", _nada)


def test_el_dominio_dictado_con_guion_se_oye_bien():
    assert F.dominio_hablado("no-mans.ejemplo.es") == "no guion mans punto ejemplo punto es"


def test_quitar_por_tema_quita_solo_la_que_encaja():
    F.anadir(TEMA, WEB)
    F.anadir("recetas de cocina", "https://cocina.es/recetas")
    assert F.gestionar(("quitar", "las recetas de cocina"), "atajo", _nada) == "Quitada: recetas de cocina."
    assert [f["tema"] for f in F.listar()] == [TEMA]


def test_quitar_por_unas_palabras_si_solo_estan_en_una():
    F.anadir(TEMA, WEB)
    assert F.gestionar(("quitar", "refinería"), "texto", _nada) == f"Quitada: {TEMA}."
    assert F.listar() == []


def test_si_varias_encajan_no_quita_ninguna_y_las_dice():
    F.anadir("recetas de refinería", WEB)
    F.anadir("recetas de cocina", "https://cocina.es/recetas")
    r = F.gestionar(("quitar", "recetas"), "atajo", _nada)
    assert "recetas de refinería" in r and "recetas de cocina" in r and "no he quitado nada" in r and len(F.listar()) == 2


def test_el_tema_entero_gana_a_uno_que_lo_contiene():
    F.anadir("recetas", WEB)
    F.anadir("recetas de cocina", "https://cocina.es/recetas")
    assert F.gestionar(("quitar", "recetas"), "atajo", _nada) == "Quitada: recetas."


@pytest.mark.parametrize("tema", ["coches", "de la", "recetas de coches"])
def test_si_no_encaja_ninguna_no_se_quita_nada(tema):
    F.anadir("recetas de cocina", "https://cocina.es/recetas")
    assert "No he quitado nada" in F.gestionar(("quitar", tema), "atajo", _nada) and len(F.listar()) == 1


@pytest.mark.parametrize("frase", ["usa la fuente de recetas", "¿quita la fuente de recetas?"])
def test_consultar_o_preguntar_no_es_quitar(frase):
    assert F.entender(frase) is None


@pytest.mark.parametrize("buscar, reserva, url, avisa", [
    (False, False, "https://nomanssky.fandom.com", True), (False, False, "https://nomanssky.fandom.com/", True),
    (False, False, "https://nomanssky.fandom.com/wiki/Refining", False), (False, False, "https://ejemplo.es/?p=3", False),
    (True, False, "https://nomanssky.fandom.com", False), (False, True, "https://nomanssky.fandom.com", False),
])
def test_guardar_la_portada_sin_poder_buscar_avisa(monkeypatch, buscar, reserva, url, avisa):
    monkeypatch.setattr(IA, "hay_busqueda_tavily", lambda: buscar)
    monkeypatch.setattr(IA, "reserva_sin_clave", lambda: reserva)
    r = F.gestionar(("anadir", TEMA, url), "atajo", _nada)
    assert ("solo leeré esa dirección" in r) is avisa and F.listar()[0]["url"] == url


def test_la_terminal_tambien_avisa_de_la_portada(monkeypatch):
    monkeypatch.setattr(IA, "hay_busqueda_tavily", lambda: False)
    monkeypatch.setattr(IA, "reserva_sin_clave", lambda: False)
    salida = []
    assert F.principal(["añadir", TEMA, "https://nomanssky.fandom.com"], salida.append) == 0
    assert "solo leeré esa dirección" in salida[0]


@pytest.mark.parametrize("accion", [("anadir", TEMA, URL_FRASE), ("copiada", TEMA), ("quitar_ultima",), ("quitar", "ya estaba")])
@pytest.mark.parametrize("origen", ["voz_libre", None, "lo que sea"])
def test_por_manos_libres_no_se_cambia_nada_ni_se_mira_el_portapapeles(accion, origen):
    assert F.anadir("ya estaba", "https://a.es")[0]
    r = F.gestionar(accion, origen, _nada)
    assert "con el atajo o con lina di" in r and [f["tema"] for f in F.listar()] == ["ya estaba"]


def test_el_portapapeles_con_el_atajo():
    assert "nomanssky punto fandom punto com" in F.gestionar(("copiada", TEMA), "atajo", lambda: f"  {URL_FRASE}\n")
    assert F.listar()[0]["url"] == URL_FRASE


def test_con_lina_di_no_se_mira_el_portapapeles():
    assert "escríbeme la dirección" in F.gestionar(("copiada", TEMA), "texto", _nada) and F.listar() == []


@pytest.mark.parametrize("copiado", ["mi contraseña es Secreta123", "tvly-abcdefghijklmnopqrstuvwxyz", f"{URL_FRASE}\notra línea privada", "http://192.168.1.10/privado"])
def test_lo_copiado_que_no_vale_no_se_repite_ni_se_guarda(copiado, archivo, capsys):
    r = F.gestionar(("copiada", TEMA), "atajo", lambda: copiado)
    assert r == "Lo que tienes copiado no es una dirección web válida. No he guardado nada." and not archivo.exists()
    salida = capsys.readouterr()
    assert copiado not in salida.out and copiado not in salida.err


def test_portapapeles_vacio_o_que_falla():
    def falla():
        raise OSError("sin portapapeles")
    assert "No he podido leer el portapapeles" in F.gestionar(("copiada", TEMA), "atajo", lambda: "")
    assert "No he podido leer el portapapeles" in F.gestionar(("copiada", TEMA), "atajo", falla) and F.listar() == []


def test_lo_incompleto_dice_que_falta_y_no_guarda():
    assert "qué página" in F.gestionar(("falta_web", "recetas"), "atajo", _nada)
    assert "qué tema" in F.gestionar(("falta_tema",), "atajo", _nada)
    assert "No he guardado nada" in F.gestionar(("mala", "recetas"), "atajo", _nada) and F.listar() == []


def test_quita_la_ultima():
    F.anadir("uno", "https://a.es")
    F.anadir("dos", "https://b.es")
    assert F.gestionar(("quitar_ultima",), "texto", _nada) == "Quitada: dos." and [f["tema"] for f in F.listar()] == ["uno"]
    F.quitar("todas")
    assert "No hay ninguna" in F.gestionar(("quitar_ultima",), "atajo", _nada)


@pytest.fixture
def asistente():
    import sys
    import threading
    from unittest.mock import MagicMock
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado, a.sustituida, a.interrumpiendo = False, False, False
    a.estado, a.cerrojo, a.fin_tarea = "esperando", threading.Lock(), threading.Event()
    a.dicho, a.historial = [], []
    a.decir = a.dicho.append
    a.ejecutor = MagicMock(pendientes=[])
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    a._preparar_contexto = lambda: None
    return a, A


@pytest.mark.parametrize("origen, se_guarda", [("atajo", True), ("texto", True), ("voz_libre", False), (None, False)])
def test_la_frase_entra_por_el_codigo_sin_ia_y_segun_el_origen(asistente, origen, se_guarda):
    a, _ = asistente
    a._atender(f"Para las recetas de refinería de No Man's Sky usa esta página {URL_FRASE}", 0.0, origen=origen)
    assert bool(F.listar()) is se_guarda and len(a.dicho) == 1 and a.historial == []


def test_al_retomar_una_tarea_no_se_vuelve_a_guardar(asistente, monkeypatch):
    a, A = asistente

    class Parar(Exception):
        pass

    def parar(frase):
        raise Parar
    monkeypatch.setattr(A.MEM, "entender", parar)                           # lo siguiente a las fuentes: de ahí no hace falta pasar
    with pytest.raises(Parar):
        a._atender(f"Para las recetas usa esta página {URL_FRASE}", 0.0, profundidad=1, origen="atajo")
    assert F.listar() == [] and a.dicho == []


# ---------------------------------------------------------------- los manuales dicen lo que hace
def test_los_manuales_de_las_fuentes_dicen_lo_que_hace():
    from pathlib import Path
    ayuda = Path(F.__file__).parents[1] / "datos" / "ayuda"
    uso = (ayuda / "uso.md").read_text(encoding="utf-8")
    assert "puede ir a la búsqueda general" in uso and "suele ir" not in uso
    assert "no pide confirmación previa" in uso and "quita la última fuente" in uso
    for frase in ("`tavily`", "`ninguna`", "`google`"):
        assert frase in uso
    privacidad = (ayuda / "privacidad.md").read_text(encoding="utf-8")
    assert "de momento solo se guardan" not in privacidad and "ve tu dirección IP" in privacidad and "clave de pago" in privacidad
    ingles = (ayuda / "privacidad.en.md").read_text(encoding="utf-8")
    assert "only saved" not in ingles and "sees your IP address" in ingles


def test_la_ayuda_de_la_ia_sobre_si_misma_sabe_lo_de_las_fuentes():
    from lina.nucleo import autoconocimiento as AUTO
    limites = " ".join(AUTO.LIMITES)
    assert "no puedes añadirlas ni quitarlas" in limites and "quita la última fuente" in limites and "puede ir a la búsqueda general" in limites


# ---------------------------------------------------------------- quitar por id, varias o todas (bloque B)
@pytest.mark.parametrize("frase, esperado", [
    ("Quita las fuentes F3 y F4", ("quitar_ids", ["f3", "f4"])),                       # la frase real que acabó en sudo pacman -R ttf-f3 ttf-f4
    ("quita f3", ("quitar_ids", ["f3"])), ("Quita la fuente f3.", ("quitar_ids", ["f3"])), ("borra la fuente 3", ("quitar_ids", ["f3"])),
    ("quita las fuentes f3, f4 y f5", ("quitar_ids", ["f3", "f4", "f5"])), ("quita la fuente efe tres", ("quitar_ids", ["f3"])),
    ("olvida la fuente f2 por favor", ("quitar_ids", ["f2"])),
    ("quita todas las fuentes", ("quitar_todas",)), ("Borra todas mis fuentes.", ("quitar_todas",)), ("elimina las fuentes todas", ("quitar_todas",)),
    ("olvida la fuente de recetas", ("quitar", "recetas")),
    ("quita esa fuente", ("quitar_incompleta",)), ("elimina las fuentes", ("quitar_incompleta",)), ("quita la fuente f3 y la de recetas", ("quitar_incompleta",)),
])
def test_quitar_se_entiende_por_id_varias_y_todas(frase, esperado):
    assert F.entender(frase) == esperado


@pytest.mark.parametrize("frase", ["quita 3", "quita el volumen", "pon la fuente f3", "usa la fuente de recetas", "¿quita la fuente f3?",
                                   "quita la fuente negrita", "quita la fuente de letra grande", "borra la tipografía Comic Sans", "quita la fuente del sistema"])
def test_lo_que_no_es_quitar_una_fuente_web_sigue_su_camino(frase):
    assert F.entender(frase) is None


@pytest.mark.parametrize("frase", ["quita esa fuente", "olvídate de las fuentes viejas", "saca la fuente que puse ayer", "borra las fuentes repetidas"])
def test_quitar_algo_de_las_fuentes_nunca_llega_a_la_ia(frase):
    accion = F.entender(frase)
    assert accion is not None and accion[0].startswith("quitar")


def test_quitar_varias_por_id_solo_si_existen_todas():
    F.anadir("recetas", WEB)
    F.anadir("partidos", "https://lolesports.com")
    F.anadir("precios", "https://ejemplo.es/precios")
    assert F.gestionar(("quitar_ids", ["f1", "f9"]), "atajo", _nada) == "No tengo f9. No he quitado nada." and len(F.listar()) == 3
    assert F.gestionar(("quitar_ids", ["f1", "f3"]), "texto", _nada) == "Quitadas: recetas; precios."
    assert [f["id"] for f in F.listar()] == ["f2"]
    assert F.gestionar(("quitar_ids", ["f2"]), "atajo", _nada) == "Quitada: partidos." and F.listar() == []


def test_quitar_todas_queda_pendiente_de_tu_si():
    F.anadir("recetas", WEB)
    F.anadir("partidos", "https://lolesports.com")
    pendientes = []
    r = F.gestionar(("quitar_todas",), "atajo", _nada, preparar=lambda d, f: pendientes.append((d, f)))
    assert "¿Las quito todas?" in r and "recetas; partidos" in r and len(F.listar()) == 2
    [(descripcion, hacer)] = pendientes
    assert "2 fuentes" in descripcion
    hacer()
    assert F.listar() == []


def test_quitar_todas_sin_fuentes_o_sin_confirmacion_no_hace_nada():
    assert F.gestionar(("quitar_todas",), "atajo", _nada, preparar=lambda d, f: None) == "No hay ninguna fuente guardada."
    F.anadir("recetas", WEB)
    assert "lina fuentes quitar todas" in F.gestionar(("quitar_todas",), "atajo", _nada) and len(F.listar()) == 1


def test_la_confirmacion_de_quitar_todas_usa_la_de_siempre():
    ej = H.Ejecutor(confirmar=True)
    ej.nueva_tarea()
    F.anadir("recetas", WEB)
    F.gestionar(("quitar_todas",), "atajo", _nada, preparar=lambda d, f: ej.preparar_accion(d, f, "quitar fuentes", razon="no se puede deshacer"))
    assert len(ej.pendientes) == 1 and ej.pendientes[0]["categoria"] == "interna" and len(F.listar()) == 1


@pytest.mark.parametrize("accion", [("quitar_ids", ["f1"]), ("quitar_todas",), ("quitar_incompleta",)])
def test_por_manos_libres_tampoco_se_quita_por_id_ni_todas(accion):
    F.anadir("recetas", WEB)
    pendientes = []
    r = F.gestionar(accion, "voz_libre", _nada, preparar=lambda d, f: pendientes.append(d))
    assert "con el atajo o con lina di" in r and len(F.listar()) == 1 and pendientes == []


def test_en_ingles_tambien(monkeypatch):
    monkeypatch.setattr(F.IDI, "actual", lambda: "en")
    assert F.entender("remove sources f3 and f4") == ("quitar_ids", ["f3", "f4"])
    assert F.entender("delete all my sources") == ("quitar_todas",)
    assert F.entender("remove that source") == ("quitar_incompleta",)
    assert F.entender("remove the bold font") is None
