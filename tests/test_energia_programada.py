# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Apagar y reiniciar programados, y la frase de confirmación de energía escrita por el código.

Caso real: la IA preparó `systemctl poweroff` (apagado inmediato) y le dijo al usuario «dentro de una hora y media, ¿lo hago?». El usuario dijo «sí»
a la frase y el equipo se apagó al momento. Ahora la herramienta sabe programar y la frase sale del comando que de verdad se va a ejecutar."""
import pytest

from lina.modulos import sistema as S
from lina.nucleo import herramientas as H
from lina.nucleo import idioma as I


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        return self.idioma


@pytest.fixture
def en(monkeypatch):
    monkeypatch.setattr(I, "IDIOMAS", ("es", "en"))
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))


@pytest.fixture
def es(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))


# --- la herramienta -------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("valor, comando", [
    ("90", "shutdown -h +90"), ("90 minutos", "shutdown -h +90"), ("+90", "shutdown -h +90"), ("dentro de 90 minutos", "shutdown -h +90"),
    ("1,5 horas", "shutdown -h +90"), ("2 h", "shutdown -h +120"), ("23:30", "shutdown -h 23:30"), ("a las 7:05", "shutdown -h 07:05"),
])
def test_apagar_con_valor_programa_el_apagado(valor, comando):
    p = S.planificar_energia({"accion": "apagar", "valor": valor})
    assert p["comando"] == comando


def test_reiniciar_con_valor_programa_el_reinicio():
    assert S.planificar_energia({"accion": "reiniciar", "valor": "45 min"})["comando"] == "shutdown -r +45"


def test_sin_valor_apaga_ahora_y_el_motivo_lo_dice():
    p = S.planificar_energia({"accion": "apagar"})
    assert p["comando"] == "systemctl poweroff"
    assert "AHORA MISMO" in p["motivo"]


def test_cancelar_apagado():
    assert S.planificar_energia({"accion": "cancelar_apagado"})["comando"] == "shutdown -c"


@pytest.mark.parametrize("valor", ["mañana", "0", "99999", "25:00", "12:75", "cuando puedas"])
def test_un_momento_que_no_se_entiende_no_apaga_nada(valor):
    p = S.planificar_energia({"accion": "apagar", "valor": valor})
    assert "error" in p and "comando" not in p


def test_lo_que_no_se_puede_programar_no_se_hace_ahora():
    for accion in ("suspender", "hibernar", "cerrar_sesion", "bloquear", "apagar_pantalla", "cancelar_apagado"):
        p = S.planificar_energia({"accion": accion, "valor": "30"})
        assert "error" in p and "comando" not in p


def test_el_apagado_programado_se_lee_del_archivo_de_systemd():
    prog = S._apagado_programado(lambda: "USEC=1893456000000000\nWARN_WALL=1\nMODE=reboot\n")
    assert prog is not None and prog[0] == "reboot" and len(prog[1]) == 5
    assert S._apagado_programado(lambda: "MODE=poweroff\n") is None            # sin hora no se inventa
    assert S._apagado_programado(lambda: (_ for _ in ()).throw(FileNotFoundError())) is None


# --- la frase escrita por el código ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("comando, frase", [
    ("systemctl poweroff", "apagar el equipo ahora mismo"),
    ("sudo systemctl reboot", "reiniciar el equipo ahora mismo"),
    ("sudo -n systemctl suspend", "suspender el equipo ahora mismo"),
    ("systemctl hibernate", "hibernar el equipo ahora mismo"),
    ("loginctl poweroff", "apagar el equipo ahora mismo"),
    ("poweroff", "apagar el equipo ahora mismo"),
    ("shutdown now", "apagar el equipo ahora mismo"),
    ("shutdown -h now", "apagar el equipo ahora mismo"),
    ("shutdown", "apagar el equipo ahora mismo"),
    ("shutdown +120", "apagar el equipo dentro de 120 minutos"),
    ("shutdown -h +90", "apagar el equipo dentro de 90 minutos"),
    ("shutdown -h +1", "apagar el equipo dentro de un minuto"),
    ("shutdown -r +45", "reiniciar el equipo dentro de 45 minutos"),
    ("shutdown -r 23:30", "reiniciar el equipo a las 23:30"),
    ("shutdown -c", "cancelar el apagado programado"),
])
def test_describir_energia_dice_lo_que_hace_el_comando(es, comando, frase):
    assert H.describir_energia(comando) == frase


@pytest.mark.parametrize("comando", [
    "ls -la", "systemctl restart lina", "systemctl status sshd", "rm -rf /tmp/x", "echo apagar", "shutdown -k +10",
    "systemctl poweroff --when=+90min", "shutdown --raro +5", "shutdown mañana", "", "echo 'sin cerrar",
])
def test_describir_energia_no_adivina(es, comando):
    assert H.describir_energia(comando) is None


def test_la_frase_de_confirmacion_sale_del_comando_y_no_de_lo_que_diga_la_ia(es):
    # el caso real: comando inmediato aunque la IA hablara de «una hora y media»
    frase, solo = H.confirmacion_de_energia([{"comando": "systemctl poweroff"}])
    assert frase == "Voy a apagar el equipo ahora mismo, ¿lo hago?" and solo is True
    frase, solo = H.confirmacion_de_energia([{"comando": "shutdown -h +90"}])
    assert frase == "Voy a apagar el equipo dentro de 90 minutos, ¿lo hago?" and solo is True


def test_confirmacion_mixta_avisa_de_que_hay_mas_cosas(es):
    frase, solo = H.confirmacion_de_energia([{"comando": "systemctl reboot"}, {"comando": "rm /tmp/x"}])
    assert "reiniciar el equipo ahora mismo" in frase and solo is False


def test_sin_ordenes_de_energia_no_se_toca_la_respuesta(es):
    assert H.confirmacion_de_energia([]) == (None, False)
    assert H.confirmacion_de_energia([{"comando": "rm /tmp/x"}, {"funcion": True, "comando": "systemctl poweroff"}]) == (None, False)


def test_la_frase_sale_en_ingles(en):
    assert H.confirmacion_de_energia([{"comando": "systemctl poweroff"}])[0] == "I'm going to power off the computer right now, shall I?"
    assert H.describir_energia("shutdown -r 23:30") == "restart the computer at 23:30"
    assert H.describir_energia("shutdown +120") == "power off the computer in 120 minutes"
