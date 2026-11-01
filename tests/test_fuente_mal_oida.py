# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Lo que falló en la prueba en vivo: «Añade la fuente que tengo en el cortapapeles a recetas…» llegó a la IA, que contestó otra cosa sin decir que no había añadido nada. Añadir se
entiende en código, con lo que oye Whisper; si falta algo se pide; por manos libres se rechaza; y lo que no es añadir (consultar la fuente, tipografía) sigue yendo a la IA."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import fuentes as F
from lina.nucleo import idioma as IDI

TEMA = "recetas de No Man's Sky"
WEB = "https://nomanssky.fandom.com/wiki/Refining"


@pytest.fixture(autouse=True)
def archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ARCHIVO", tmp_path / "fuentes.json")
    monkeypatch.setattr(IDI, "actual", lambda: "es")


@pytest.mark.parametrize("frase", ["Añade la fuente que tengo en el cortapapeles a recetas de No Man's Sky", "Añade la fuente que tengo en el portapapeles a recetas de No Man's Sky",
                                   "añade la fuente del porta papeles a recetas de No Man's Sky", "anade la fuente del portapapeles a recetas de No Man's Sky",
                                   "Añade las fuentes del cortapapeles a recetas de No Man's Sky", "Añade la fuente que tengo copiada a recetas de No Man's Sky",
                                   "Guarda la fuente del portapapeles para recetas de No Man's Sky", "Apúntame la fuente del cortapapeles para recetas de No Man's Sky",
                                   "para recetas de No Man's Sky usa la web del portapapeles", "para recetas de No Man's Sky usa lo que tengo en el cortapapeles"])
def test_se_entiende_y_con_el_atajo_se_guarda(frase):
    accion = F.entender(frase)
    assert accion == ("copiada", TEMA)
    r = F.gestionar(accion, "atajo", lambda: WEB)
    assert r.startswith("Guardado") and [f["url"] for f in F.listar()] == [WEB]


@pytest.mark.parametrize("frase", ["Añade la fuente que tengo en el cortapapeles a recetas de No Man's Sky", "guarda esta fuente", "añade la fuente a recetas", "añade una fuente",
                                   "guarda esta web como fuente"])
def test_por_manos_libres_se_rechaza_sin_mirar_el_portapapeles_ni_escribir(frase):
    leer = MagicMock(side_effect=AssertionError("no debía mirar el portapapeles"))
    accion = F.entender(frase)
    assert accion
    assert "Las fuentes solo se cambian con el atajo" in F.gestionar(accion, "voz_libre", leer)
    assert F.listar() == []


@pytest.mark.parametrize("frase", ["guarda esta fuente", "añade una fuente", "apunta la fuente", "quiero añadir una fuente", "puedes guardar esta fuente", "añade fuentes", "guarda en fuentes",
                                   "usa esta web como fuente", "usa una nueva fuente"])
def test_incompleta_pide_lo_que_falta(frase):
    accion = F.entender(frase)
    assert accion == ("incompleta",)
    assert "me falta la web o el tema" in F.gestionar(accion, "atajo", MagicMock(side_effect=AssertionError))


def test_con_direccion_dictada_se_guarda():
    assert F.entender("añade la fuente nomanssky.fandom.com a recetas") == ("anadir", "recetas", "nomanssky.fandom.com")


@pytest.mark.parametrize("frase", ["usa la fuente de recetas", "utiliza la fuente de recetas", "usa mi fuente de recetas", "usa mi fuente", "usa la fuente", "usa la fuente de recetas para esto",
                                   "para esto usa la fuente de recetas", "usa la fuente de recetas para contestar"])
def test_consultar_la_fuente_no_es_gestionarla(frase):
    assert F.entender(frase) is None and not F.pide_anadir_suelto(frase)


@pytest.mark.parametrize("frase", ["usa una fuente más grande", "añade una fuente de agua a la base", "cambia la fuente a Arial", "pon otra fuente en el documento", "guarda la fuente en negrita",
                                   "añade una fuente de alimentación al pedido", "¿qué fuente usas?", "¿añades fuentes?", "añade sal a la receta", "guarda el archivo en descargas",
                                   "guarda esta página en marcadores", "guarda esta página en pdf", "añade lo que tengo copiado a la nota", "usa lo del portapapeles como título",
                                   "la fuente del texto es muy grande", "usa Spotify para la música", "para la música usa Spotify"])
def test_lo_que_no_es_anadir_fuentes_sigue_su_camino(frase):
    assert F.entender(frase) is None and not F.pide_anadir_suelto(frase)


@pytest.mark.parametrize("frase, esperado", [(f"para recetas usa {WEB}", ("anadir", "recetas", WEB)), ("usa la página que tengo copiada para recetas", ("copiada", "recetas")),
                                             ("usa esta página", ("falta_tema",)), ("quita la última fuente", ("quitar_ultima",))])
def test_lo_de_f2_no_cambia(frase, esperado):
    assert F.entender(frase) == esperado


@pytest.mark.parametrize("frase, esperado", [("add the source from the clipboard to refinery recipes", ("copiada", "refinery recipes")), ("save this source", ("incompleta",)),
                                             ("use the recipes source", None), ("use my source", None), ("add a water source to the base", None), ("use this site as a source", ("incompleta",))])
def test_en_ingles(monkeypatch, frase, esperado):
    monkeypatch.setattr(IDI, "actual", lambda: "en")
    monkeypatch.setattr(IDI, "segun", lambda d: d["en"])
    assert F.entender(frase) == esperado


# ---------------------------------------------------------------- la frase no llega a la IA, y lo que se escapa avisa
@pytest.fixture
def lina():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], duda=None, efecto_sin_comprobar=False)
    a.fuente_turno, a.acciones_turno = None, []
    a._fuentes_antes = F.firma()
    return a


ESCAPADA = "lo de la fuente nueva guárdala en recetas"


def test_lo_escapado_avisa_de_que_no_se_anadio_nada(lina):
    assert F.entender(ESCAPADA) is None
    lina.pregunta_pura = ESCAPADA
    r = lina.asegurar_honestidad_final("Los gusanos de harina sirven de cebo.")
    assert r.startswith("Los gusanos") and r.endswith("«para este tema usa esta web».") and "no he añadido ninguna fuente" in r


def test_si_la_lista_cambio_no_avisa(lina):
    lina.pregunta_pura = ESCAPADA
    F.anadir("recetas", WEB)
    assert lina.asegurar_honestidad_final("Hecho el resumen.") == "Hecho el resumen."


def test_si_la_respuesta_ya_lo_dice_no_avisa(lina):
    lina.pregunta_pura = ESCAPADA
    assert lina.asegurar_honestidad_final("No he podido guardar la fuente.") == "No he podido guardar la fuente."


@pytest.mark.parametrize("peticion", ["usa la fuente de recetas", "¿qué sale si refino ferrita?", "usa una fuente más grande"])
def test_las_frases_normales_no_quedan_tocadas(lina, peticion):
    lina.pregunta_pura = peticion
    assert lina.asegurar_honestidad_final("Sale ferrita pura.") == "Sale ferrita pura."


@pytest.mark.parametrize("frase, ofrecida", [("usa la fuente de recetas", True), ("utiliza la fuente de recetas", True), ("usa mi fuente de recetas", True), ("guarda esta fuente", False)])
def test_las_consultas_llevan_usar_fuente_y_la_gestion_no_llega_a_la_ia(lina, monkeypatch, frase, ofrecida):
    monkeypatch.setattr(F, "listar", lambda: [{"id": "f1", "tema": "recetas", "url": WEB, "dominio": "nomanssky.fandom.com"}])
    monkeypatch.setattr(F, "activas", lambda: True)
    lina.pregunta_pura = frase
    assert (F.entender(frase) is None) is ofrecida
    if ofrecida:
        assert [d["name"] for d in lina._herramienta_de_fuente()] == ["usar_fuente"]


def test_atender_gestiona_sin_llamar_a_la_ia_ni_a_r3():
    from pathlib import Path
    fuente = Path(F.__file__).with_name("asistente.py").read_text(encoding="utf-8")
    assert fuente.index("FUE.entender(pregunta)") < fuente.index("MEM.entender(pregunta)") < fuente.index("self._intentar_contenido(pregunta, crono)")
