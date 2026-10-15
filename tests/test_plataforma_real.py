"""Pruebas contra la distribución REAL en la que se ejecutan. Se activan con LINA_FAMILIA_ESPERADA=arch|debian|fedora|suse
(la CI las lanza dentro de contenedores de cada familia; en tu equipo, `scripts/probar_en_contenedores.sh`)."""
import os
import subprocess

import pytest

from lina.nucleo import ejecucion as EJ
from lina.nucleo import herramientas as H
from lina.nucleo import plataforma as PL

ESPERADA = os.environ.get("LINA_FAMILIA_ESPERADA")
pytestmark = pytest.mark.skipif(not ESPERADA, reason="solo dentro de un contenedor de una familia concreta (LINA_FAMILIA_ESPERADA)")


def test_detecta_la_familia_y_el_gestor_reales():
    d = PL.detectar(entorno={})                      # sin LINA_DISTRO: lo que dice /etc/os-release de verdad
    assert d["familia"] == ESPERADA
    assert d["tiene_gestor"], f"no encuentro {d['gestor']}"


def test_comprueba_paquetes_instalados_de_verdad(monkeypatch):
    monkeypatch.setenv("LINA_DISTRO", ESPERADA)
    assert PL.esta_instalado("bash", EJ._ejecutar_simple) is True
    assert PL.esta_instalado("paquete-que-no-existe-lina", EJ._ejecutar_simple) is False


def test_las_ordenes_de_consulta_existen_en_el_sistema(monkeypatch):
    monkeypatch.setenv("LINA_DISTRO", ESPERADA)
    for orden in (PL.consulta_instalado("bash"), PL.orden("buscar", ["zzzz"]), PL.orden("instalar", ["bash"]), PL.orden("quitar", ["bash"])):
        assert orden and subprocess.run(["which", orden[0]], capture_output=True).returncode == 0, orden


def test_las_capacidades_se_leen_sin_romperse():
    c = PL.capacidades()
    assert c["familia"] == ESPERADA and c["init"] in ("systemd", "openrc", "runit", "s6", "otro")
    assert PL.describir(c)


def test_el_filtro_funciona_con_el_gestor_real(monkeypatch):
    monkeypatch.setenv("LINA_DISTRO", ESPERADA)
    assert H.clasificar(PL.orden_canonica_instalar(["vlc"]))[0] == "instalar"
    assert H.clasificar(" ".join(PL.orden("buscar", ["vlc"])))[0] == "lectura"
