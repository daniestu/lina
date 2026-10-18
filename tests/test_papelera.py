# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La papelera: los borrados de tus archivos se convierten en «gio trash» y lo borrado se puede ver y vaciar."""
import pytest

from lina.nucleo import papelera as PAP
from lina.nucleo import registro as REG


@pytest.fixture(autouse=True)
def _registro_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(REG, "ARCHIVO_ACCIONES", tmp_path / "acciones.log")


def test_borrar_un_archivo_tuyo_pasa_a_la_papelera():
    nuevo, motivo = PAP.tratar_borrado("rm ~/Documentos/viejo.txt")
    assert motivo is None and nuevo.startswith("gio trash -- ") and "viejo.txt" in nuevo


def test_un_comando_que_no_borra_no_se_toca():
    assert PAP.tratar_borrado("ls -la ~") == ("ls -la ~", None)


def test_borrar_fuera_de_tu_carpeta_sigue_como_estaba():
    assert PAP.tratar_borrado("rm /tmp/prueba-lina.txt") == ("rm /tmp/prueba-lina.txt", None)


def test_las_opciones_van_antes_de_las_rutas():
    _, motivo = PAP.tratar_borrado("rm ~/a.txt -f")
    assert motivo and "opciones" in motivo


def test_una_opcion_desconocida_se_rechaza():
    _, motivo = PAP.tratar_borrado("rm --no-preserve-root ~/a.txt")
    assert motivo and "No reconozco" in motivo


def test_borrados_complejos_sobre_tus_archivos_se_piden_sencillos():
    _, motivo = PAP.tratar_borrado("rm ~/a.txt && rm ~/b.txt")
    assert motivo


def test_la_cache_y_lo_ya_borrado_no_van_a_la_papelera():
    assert not PAP._se_va_a_la_papelera("~/.cache/algo")
    assert not PAP._se_va_a_la_papelera("~/.local/share/Trash/files/x")
    assert PAP._se_va_a_la_papelera("~/Documentos/x.txt")


def _poner_en_la_papelera(base, nombre, origen, fecha):
    (base / "Trash" / "info").mkdir(parents=True, exist_ok=True)
    (base / "Trash" / "files").mkdir(parents=True, exist_ok=True)
    (base / "Trash" / "files" / nombre).write_text("contenido")
    (base / "Trash" / "info" / f"{nombre}.trashinfo").write_text(
        f"[Trash Info]\nPath={origen}\nDeletionDate={fecha}\n", encoding="utf-8")


def test_ver_y_vaciar_la_papelera(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setattr(PAP, "RUTA_DATOS", str(tmp_path / "sin_disco"))
    assert "vacía" in PAP.ver_papelera()
    _poner_en_la_papelera(tmp_path / "datos", "viejo.txt", "/tmp/origen/Documentos/viejo.txt", "2026-10-01T10:00:00")
    _poner_en_la_papelera(tmp_path / "datos", "nuevo.txt", "/tmp/origen/Documentos/nuevo.txt", "2026-10-02T10:00:00")
    elementos = PAP.contenido_papelera()
    assert [e["nombre"] for e in elementos] == ["nuevo.txt", "viejo.txt"]            # lo más reciente primero
    assert "2 elementos" in PAP.ver_papelera()
    assert "2 elementos borrados para siempre" in PAP.vaciar_papelera()
    assert PAP.contenido_papelera() == []


def test_restaurar_pide_un_nombre_y_avisa_si_no_hay(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setattr(PAP, "RUTA_DATOS", str(tmp_path / "sin_disco"))
    assert "Falta el nombre" in PAP.restaurar_de_papelera("")
    assert "No hay nada" in PAP.restaurar_de_papelera("fantasma")
