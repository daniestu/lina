# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Un alias no puede convertir un verbo de orden en otro («conecta = desconecta»): cambiaría lo que hace Lina cada vez que lo dices."""
import pytest

from lina.nucleo import comandos as C
from lina.nucleo import idioma as IDI


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    """alias.txt en una carpeta temporal y el idioma fijado: nada del equipo real."""
    monkeypatch.setattr(C, "ARCHIVO_ALIAS", tmp_path / "alias.txt")
    monkeypatch.setattr(IDI, "actual", lambda: "es")
    return tmp_path / "alias.txt"


@pytest.mark.parametrize("oido, significa", [
    ("conecta", "desconecta"),
    ("sube", "apaga el equipo"),
    ("súbelo", "apágalo"),
    ("activa", "desactiva la cámara"),
    ("baja", "sube"),
    ("abre steam", "borra steam"),
    ("quita", "reproduce"),                                       # casi sinónimos también caen (el mensaje lo explica)
])
def test_rechaza_dos_verbos_de_orden_distintos(aislado, oido, significa):
    hecho, mensaje = C.guardar_alias(oido, significa)
    assert not hecho
    assert "órdenes distintas" in mensaje and "aunque sean casi sinónimos" in mensaje and "a mano" in mensaje and str(aislado) in mensaje
    assert not aislado.exists()


@pytest.mark.parametrize("oido, significa", [
    ("renuda", "reanuda"),                                        # «renuda» no es un verbo conocido: es una corrección de verdad
    ("cait", "Kate"),
    ("abre stim", "abre Steam"),
    ("súbelo", "sube"),                                           # el mismo verbo con otra forma
    ("esteam", "Steam para jugar"),                               # «para» como preposición no cuenta
])
def test_deja_las_correcciones_de_verdad(aislado, oido, significa):
    hecho, mensaje = C.guardar_alias(oido, significa)
    assert hecho, mensaje
    assert C.listar_alias()[-1] == (oido, significa)


def test_en_ingles_tambien(aislado, monkeypatch):
    monkeypatch.setattr(IDI, "actual", lambda: "en")
    assert not C.guardar_alias("connect", "disconnect")[0]
    assert C.guardar_alias("stim", "Steam")[0]
