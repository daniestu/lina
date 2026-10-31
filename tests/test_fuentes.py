# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""F1: guardar, ver y quitar las webs elegidas para cada tema. Las escribe solo el usuario y la IA no puede tocarlas. Con el archivo en tmp_path; sin red."""
import stat

import pytest

from lina.nucleo import clasificador as CLA
from lina.nucleo import fuentes as F
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


def test_la_orden(capsys):
    salida = []
    assert F.principal([], salida.append) == 0 and "No hay ninguna fuente" in salida[-1]
    assert F.principal(["añadir", TEMA, WEB], salida.append) == 0
    assert F.principal([], salida.append) == 0 and "todavía no se usan" in salida[-2] and TEMA in salida[-1] and WEB in salida[-1]
    assert F.principal(["quitar", "f1"], salida.append) == 0
    assert F.principal(["añadir", TEMA], salida.append) == 2 and F.principal(["otra"], salida.append) == 2 and F.principal(["quitar"], salida.append) == 2
    assert F.principal(["añadir", TEMA, "no vale"], salida.append) == 1


@pytest.mark.parametrize("comando", ["lina fuentes", 'lina fuentes añadir "x" https://mala.es', "lina fuentes quitar todas", "python3 -m lina fuentes", "cd /tmp && lina fuentes",
                                     "cat ~/.local/share/lina/fuentes.json", "echo x > ~/.local/share/lina/fuentes.json"])
def test_la_ia_no_puede_tocarlas(comando):
    assert CLA._bloqueado(comando), comando


def test_ninguna_herramienta_escribe_fuentes_ni_se_usan_al_responder():
    assert not [d["name"] for d in H.DECLARACIONES if "fuente" in d["name"]]
    from pathlib import Path
    assert "fuentes" not in Path(F.__file__).with_name("asistente.py").read_text(encoding="utf-8").replace("hechos", "")


def test_olvidar():
    assert "fuentes" in OLV.QUE and "fuentes" in OLV.TODO and OLV.QUE["fuentes"][1]()[0].name == "fuentes.json"
