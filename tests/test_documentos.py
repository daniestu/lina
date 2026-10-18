# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Documentos: rehacer uno que Lina acaba de crear lo sustituye; lo del usuario nunca se sobrescribe."""
import time

from lina.nucleo import documentos as DOC
from lina.nucleo import registro as REG


def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(REG, "ARCHIVO_ACCIONES", tmp_path / "acciones.log")
    monkeypatch.setattr(DOC, "CARPETA_DOCUMENTOS", tmp_path / "Documentos")
    monkeypatch.setattr(DOC, "_abrir_con_escritorio", lambda r: None)
    monkeypatch.setattr(DOC.shutil, "which", lambda n, *a, **k: None)           # sin xdg-open
    monkeypatch.setattr(DOC, "_CREADOS", {})


def test_un_documento_del_usuario_no_se_sobrescribe(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    (tmp_path / "Documentos").mkdir()
    (tmp_path / "Documentos" / "carta.md").write_text("mío")
    r = DOC.crear_documento("carta", "texto nuevo", formato="md", abrir=False)
    assert "carta (2).md" in r and (tmp_path / "Documentos" / "carta.md").read_text() == "mío"


def test_lo_que_lina_acaba_de_crear_se_sustituye_al_rehacerlo(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    DOC.crear_documento("informe", "primera versión", formato="md", abrir=False)
    r = DOC.crear_documento("informe", "segunda versión", formato="md", abrir=False)
    assert "informe.md" in r and "(2)" not in r
    assert (tmp_path / "Documentos" / "informe.md").read_text() == "segunda versión"
    assert [p.name for p in (tmp_path / "Documentos").iterdir()] == ["informe.md"]


def test_pasado_un_rato_ya_no_se_sustituye(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    DOC.crear_documento("informe", "uno", formato="md", abrir=False)
    ruta = str(tmp_path / "Documentos" / "informe.md")
    DOC._CREADOS[ruta] = time.time() - DOC.VIDA_CREADOS_SEG - 5
    DOC.crear_documento("informe", "dos", formato="md", abrir=False)
    assert (tmp_path / "Documentos" / "informe (2).md").exists()
