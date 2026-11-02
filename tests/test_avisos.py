# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A7: los avisos opcionales. Apagados de fábrica, solo notificación, y como mucho una vez al día (la batería, una vez por descarga). Estado en tmp_path; sin notificaciones ni órdenes de verdad."""
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import avisos as AV

LUNES = 1793000000.0
MARTES = LUNES + 90000


class Aj:
    def __init__(self, **encendidos):
        self.encendidos = encendidos

    def get(self, seccion, clave):
        return self.encendidos.get(clave, False)


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(AV.RUT, "ESTADO", tmp_path)
    monkeypatch.setattr(AV, "_ultima_mirada", [0.0])
    return tmp_path


def _pendientes(aj, ahora=LUNES, bat=lambda: None, disc=lambda: None, act=lambda: None):
    return AV.pendientes(aj, ahora, bat, disc, act)


def test_de_fabrica_estan_apagados():
    assert [AJ.ESQUEMA["avisos"][k][0] for k in ("disco", "bateria", "actualizaciones")] == [False, False, False]


def test_apagados_no_miran_nada():
    nada = MagicMock(side_effect=AssertionError("no debía mirar"))
    assert _pendientes(Aj(), bat=nada, disc=nada, act=nada) == []


@pytest.mark.parametrize("libre, avisa", [(4 * 1024 ** 3, True), (50 * 1024 ** 3, False)])
def test_disco_por_gigas(libre, avisa):
    assert bool(AV.disco("/x", lambda r: (500 * 1024 ** 3, 0, libre))) is avisa


def test_disco_por_porcentaje_en_un_disco_grande():
    assert AV.disco("/x", lambda r: (4000 * 1024 ** 3, 0, 100 * 1024 ** 3))


def test_si_no_se_puede_leer_el_disco_no_hay_aviso():
    assert AV.disco("/x", MagicMock(side_effect=OSError)) is None


def test_el_disco_avisa_una_vez_al_dia():
    def disc():
        return "poco sitio"

    assert _pendientes(Aj(disco=True), disc=disc) == ["poco sitio"]
    assert _pendientes(Aj(disco=True), disc=disc) == []
    assert _pendientes(Aj(disco=True), MARTES, disc=disc) == ["poco sitio"]


def test_la_bateria_avisa_una_vez_por_descarga():
    aj = Aj(bateria=True)
    assert "14 %" in _pendientes(aj, bat=lambda: (True, 14))[0]
    assert _pendientes(aj, bat=lambda: (True, 12)) == []
    assert _pendientes(aj, bat=lambda: (False, 20)) == []        # la has enchufado
    assert _pendientes(aj, bat=lambda: (True, 15))


@pytest.mark.parametrize("estado_bat", [(False, 5), (True, 16), None])
def test_la_bateria_no_avisa_enchufada_ni_con_carga(estado_bat):
    assert _pendientes(Aj(bateria=True), bat=lambda: estado_bat) == []


def test_leer_la_bateria(tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir()
    (bat / "status").write_text("Discharging\n")
    (bat / "capacity").write_text("14\n")
    assert AV.bateria(str(tmp_path)) == (True, 14) and AV.bateria(str(tmp_path / "nada")) is None


@pytest.mark.parametrize("familia, codigo, salida, esperado", [
    ("arch", 0, "linux 6.1-1 -> 6.2-1\nvim 9.0-1 -> 9.1-1\n", 2), ("arch", 2, "", 0), ("arch", 1, "error", None),
    ("debian", 0, "Listing...\nvim/stable 2:9.1 amd64 [upgradable from: 2:9.0]\n", 1),
    ("fedora", 100, "vim.x86_64  2:9.1-1.fc40  updates\n\n", 1), ("fedora", 0, "", 0),
    ("suse", 0, "S | Repository | Name | Current | Available | Arch\n--+---\nv | Main | vim | 9.0 | 9.1 | x86_64\n", 1),
    ("otra", 0, "", None),
])
def test_contar_actualizaciones(monkeypatch, familia, codigo, salida, esperado):
    monkeypatch.setattr(AV.shutil, "which", lambda o: "/usr/bin/" + o)
    assert AV.actualizaciones(lambda orden: (codigo, salida), familia) == esperado


def test_sin_la_orden_no_se_sabe(monkeypatch):
    monkeypatch.setattr(AV.shutil, "which", lambda o: None)
    assert AV.actualizaciones(MagicMock(side_effect=AssertionError), "arch") is None


def test_las_ordenes_de_actualizaciones_son_de_solo_lectura():
    assert all(not {"upgrade", "update", "install", "sudo", "-Syu", "refresh"} & set(o[0]) for o in AV.ACTUALIZACIONES.values())


def test_las_actualizaciones_no_se_miran_en_cada_vuelta():
    act = MagicMock(return_value=0)
    _pendientes(Aj(actualizaciones=True), act=act)
    _pendientes(Aj(actualizaciones=True), LUNES + 60, act=act)
    assert act.call_count == 1
    _pendientes(Aj(actualizaciones=True), LUNES + AV.ACTUALIZACIONES_CADA_SEG, act=act)
    assert act.call_count == 2


def test_las_actualizaciones_avisan_una_vez_al_dia():
    assert "3 actualizaciones" in _pendientes(Aj(actualizaciones=True), act=lambda: 3)[0]
    assert _pendientes(Aj(actualizaciones=True), LUNES + AV.ACTUALIZACIONES_CADA_SEG, act=lambda: 3) == []


def test_el_bucle_solo_notifica_y_un_fallo_no_lo_rompe(monkeypatch):
    notificar = MagicMock()
    monkeypatch.setattr(AV.AJ, "actuales", lambda log=print: Aj(disco=True))
    monkeypatch.setattr(AV, "disco", lambda: "poco sitio")
    AV.vigilar(una_vez=True, notificar=notificar)
    notificar.assert_called_once_with("Lina: aviso", "poco sitio")
    monkeypatch.setattr(AV.AJ, "actuales", MagicMock(side_effect=RuntimeError("roto")))
    AV.vigilar(una_vez=True, notificar=notificar)


def test_un_estado_roto_no_rompe_nada(estado):
    (estado / AV.ARCHIVO).write_text("{roto", encoding="utf-8")
    assert _pendientes(Aj(disco=True), disc=lambda: "x") == ["x"]


def test_lina_avisos_enseña_y_no_notifica(monkeypatch):
    monkeypatch.setattr(AV.AJ, "actuales", lambda log=print: Aj(disco=True))
    monkeypatch.setattr(AV, "disco", lambda: None)
    monkeypatch.setattr(AV, "bateria", lambda: None)
    monkeypatch.setattr(AV, "actualizaciones", lambda: None)
    salida = []
    assert AV.principal([], salida.append) == 0
    assert "encendido" in salida[0] and "apagado" in salida[1] and "no hay batería" in salida[1]
    assert AV.principal(["x"], salida.append) == 2
