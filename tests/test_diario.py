"""Diario de cambios: anotar, marcar como deshecho, copias de seguridad, restaurarlas y limpiar lo viejo."""
import os
import time

import pytest

from lina.nucleo import diario as D


@pytest.fixture(autouse=True)
def _carpeta_propia(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "DIR", tmp_path / "diario")


def test_anotar_y_listar_lo_mas_reciente_primero():
    a = D.anotar({"comando": "uno"})
    b = D.anotar({"comando": "dos"})
    assert [e["comando"] for e in D.listar()] == ["dos", "uno"]
    assert D.listar(1)[0]["id"] == b["id"] and a["id"] != b["id"]
    assert os.stat(D.DIR / "diario.jsonl").st_mode & 0o777 == 0o600


def test_marcar_como_deshecho_no_reescribe_el_archivo():
    e = D.anotar({"comando": "algo"})
    D.marcar(e["id"], deshecho=True)
    assert D.listar()[0]["deshecho"] is True
    assert len((D.DIR / "diario.jsonl").read_text().splitlines()) == 2


def test_una_linea_rota_no_tumba_el_diario():
    D.anotar({"comando": "bueno"})
    with (D.DIR / "diario.jsonl").open("a") as f:
        f.write("esto no es json\n")
    assert [e["comando"] for e in D.listar()] == ["bueno"]


def test_obtener_por_id_exacto_o_por_trozo_unico():
    e = D.anotar({"comando": "x"})
    assert D.obtener(e["id"])["comando"] == "x"
    assert D.obtener(e["id"][-6:])["comando"] == "x"
    assert D.obtener("") is None and D.obtener("no-existe") is None


def test_guardar_y_restaurar_una_copia(tmp_path):
    origen = tmp_path / "ajustes.conf"
    origen.write_text("valor=1")
    copia, motivo = D.guardar_respaldo("id1", origen)
    assert motivo == "" and D.respaldo_valido(copia)
    origen.write_text("valor=2")
    ok, msg = D.restaurar_respaldo(copia, origen, modo=0o640)
    assert ok and msg == "" and origen.read_text() == "valor=1" and origen.stat().st_mode & 0o777 == 0o640


def test_no_se_copia_lo_que_no_se_debe(tmp_path):
    assert D.guardar_respaldo("id", tmp_path / "no_existe")[1] == "no existe"
    enlace = tmp_path / "enlace"
    (tmp_path / "real").write_text("x")
    enlace.symlink_to(tmp_path / "real")
    assert D.guardar_respaldo("id", enlace)[1] == "es un enlace"
    assert D.guardar_respaldo("id", tmp_path)[1] == "no es un archivo normal"
    grande = tmp_path / "grande"
    grande.write_bytes(b"x" * 2048)
    assert "pesa más" in D.guardar_respaldo("id", grande, limite_mb=0)[1]


def test_solo_se_restaura_desde_la_carpeta_de_copias(tmp_path):
    ajeno = tmp_path / "ajeno"
    ajeno.write_text("malo")
    assert not D.respaldo_valido(ajeno)
    ok, msg = D.restaurar_respaldo(ajeno, tmp_path / "destino")
    assert not ok and "ya no existe" in msg and not (tmp_path / "destino").exists()


def test_limpiar_conserva_las_ultimas_entradas_y_borra_copias_huerfanas(tmp_path):
    for i in range(5):
        D.anotar({"comando": f"c{i}"})
    viva = D.listar()[0]["id"]
    for ident in (viva, "huerfana"):
        (D.DIR / "respaldos" / ident).mkdir(parents=True)
        (D.DIR / "respaldos" / ident / "0_f").write_text("x")
    borradas = D.limpiar(max_entradas=3)
    assert borradas == 1 and (D.DIR / "respaldos" / viva).exists() and not (D.DIR / "respaldos" / "huerfana").exists()
    assert [e["comando"] for e in D.listar()] == ["c4", "c3", "c2"]


def test_limpiar_borra_las_copias_antiguas(tmp_path):
    e = D.anotar({"comando": "viejo"})
    carpeta = D.DIR / "respaldos" / e["id"]
    carpeta.mkdir(parents=True)
    (carpeta / "0_f").write_text("x")
    hace_mucho = time.time() - 40 * 86400
    os.utime(carpeta, (hace_mucho, hace_mucho))
    assert D.limpiar(dias=30) == 1
