# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Captura de pantalla bajo demanda (fase 17, V2): no se captura si no se podrá usar; en un juego, al pulsar; fuera, después y solo si la frase lo pide,
volviendo a comprobar en ese momento la privacidad y que sigue siendo la MISMA ventana; las órdenes directas no la esperan; y el archivo no se queda.
Escritorio simulado, HOME aislado."""
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from lina.nucleo import ajustes as AJ

A = None


class _Escritorio:
    """Sesión de escritorio simulada: la ventana activa se puede cambiar a mano; cada captura se cuenta y deja una imagen de verdad."""
    def __init__(self):
        self.ventana = {"titulo": "Documento — Kate", "clase": "org.kde.kate", "pid": 0, "id": "{ventana-1}", "metodo": "kdotool"}
        self.capturas, self.lenta = [], 0.0

    def ventana_activa(self, vigencia=0.6):
        return dict(self.ventana)

    def capturar(self, destino, activa=False, tiempo=15):
        time.sleep(self.lenta)
        self.capturas.append((str(destino), self.ventana["id"]))
        Image.new("RGB", (40, 30), "white").save(destino)
        return True


@pytest.fixture
def escritorio(monkeypatch):
    global A
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    A = asistente
    e = _Escritorio()
    monkeypatch.setattr(A.SES, "actual", lambda: e)
    yield e
    AJ.actuales(log=lambda m: None).establecer("privacidad", "capturas", "preguntar")


def _permiso(valor):
    AJ.actuales(log=lambda m: None).establecer("privacidad", "capturas", valor)


def _asistente():
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado, a.ultima_pantalla_t, a.pantalla_adjunta, a.captura_guardada, a.pedir_pantalla = False, 0.0, False, None, False
    a.ejecutor = MagicMock()
    a.ejecutor.contaminado = ""
    a.ejecutor.pendientes = []
    return a


def _pulsar_y_pedir(a, pregunta):
    a._preparar_contexto()
    return a._captura_de_la_peticion(pregunta)


@pytest.mark.parametrize("permiso", ["preguntar", "no"])
def test_sin_permiso_no_se_captura_nada(escritorio, permiso):
    _permiso(permiso)
    assert _pulsar_y_pedir(_asistente(), "¿qué pone aquí?") is None and escritorio.capturas == []


def test_en_modo_privado_no_se_captura_nada(escritorio):
    _permiso("si")
    a = _asistente()
    a.modo_privado = True
    assert _pulsar_y_pedir(a, "¿qué pone aquí?") is None and escritorio.capturas == []


def test_con_una_ventana_sensible_no_se_captura_nada(escritorio):
    _permiso("si")
    escritorio.ventana["titulo"] = "Banco Santander — Firefox"
    assert _pulsar_y_pedir(_asistente(), "¿qué pone aquí?") is None and escritorio.capturas == []


def test_en_un_juego_se_captura_al_pulsar(escritorio):
    _permiso("si")
    escritorio.ventana.update(titulo="Skyrim", clase="steam_app_72850")
    a = _asistente()
    a._preparar_contexto()
    a.hilo_captura.join(5)
    assert len(escritorio.capturas) == 1                           # al pulsar, antes de saber qué dirás
    assert a._captura_de_la_peticion("¿dónde está la misión?") is not None and len(escritorio.capturas) == 1


def test_fuera_de_un_juego_solo_si_la_frase_lo_pide_y_despues_de_hablar(escritorio):
    _permiso("si")
    a = _asistente()
    a._preparar_contexto()
    assert escritorio.capturas == []                               # al pulsar no
    assert a._captura_de_la_peticion("¿qué pone aquí?") is not None and len(escritorio.capturas) == 1
    b = _asistente()
    assert _pulsar_y_pedir(b, "¿qué hora es en Tokio?") is None and len(escritorio.capturas) == 1


def test_una_ventana_sensible_que_aparece_entre_la_pulsacion_y_la_captura_no_se_captura(escritorio):
    _permiso("si")
    a = _asistente()
    a._preparar_contexto()
    escritorio.ventana["titulo"] = "PayPal — Mozilla Firefox"       # misma ventana (mismo id), pero ahora enseña el banco
    assert a._captura_de_la_peticion("¿qué pone aquí?") is None and escritorio.capturas == []
    assert "sensible" in a.nota_captura


def test_si_la_ventana_activa_cambio_no_se_captura_y_se_dice(escritorio):
    _permiso("si")
    a = _asistente()
    a._preparar_contexto()
    escritorio.ventana.update(id="{ventana-2}", titulo="Otra cosa — Dolphin", clase="org.kde.dolphin")
    assert a._captura_de_la_peticion("¿qué pone aquí?") is None and escritorio.capturas == []
    assert "ya no es la que tenía delante" in a.nota_captura


def test_sin_identificador_se_compara_titulo_y_clase(escritorio):
    _permiso("si")
    escritorio.ventana["id"] = ""
    a = _asistente()
    a._preparar_contexto()
    escritorio.ventana["titulo"] = "Otro documento — Kate"
    assert a._captura_de_la_peticion("¿qué pone aquí?") is None and escritorio.capturas == []


def test_si_activas_el_modo_privado_entre_medias_no_se_captura(escritorio):
    _permiso("si")
    a = _asistente()
    a._preparar_contexto()
    a.modo_privado = True
    assert a._captura_de_la_peticion("¿qué pone aquí?") is None and escritorio.capturas == []


def test_una_orden_directa_no_espera_a_la_captura(escritorio, monkeypatch):
    _permiso("si")
    escritorio.ventana.update(titulo="Skyrim", clase="steam_app_72850")
    escritorio.lenta = 1.5                                          # una captura lenta, en un juego (donde se hace al pulsar)
    a = _asistente()
    a._preparar_contexto()
    a.historial = []
    a._hay_recuerdos_pertinentes = lambda p: False
    a.nueva_tarea = lambda: None
    a._ejecutar_directa = lambda ident, datos: "Hecho."
    t0 = time.monotonic()
    assert a._intentar_directa("sube el volumen", A.TIE.Cronometro()) == ("Hecho.", "volumen")
    assert time.monotonic() - t0 < 0.5
    a.hilo_captura.join(5)


def test_ver_pantalla_captura_en_ese_momento(escritorio):
    _permiso("si")
    a = _asistente()
    a._preparar_contexto()
    assert "se te adjuntará" in a._ejecutar_herramienta("ver_pantalla", {})
    assert a.captura_guardada and a.pedir_pantalla and len(escritorio.capturas) == 1


def test_conceder_el_permiso_a_mitad_de_peticion_captura_entonces(escritorio):
    _permiso("preguntar")
    a = _asistente()
    a.imagen_del_turno = _pulsar_y_pedir(a, "¿qué pone aquí?")
    assert a.imagen_del_turno is None and escritorio.capturas == []
    assert "Permiso concedido" in a._conceder_capturas()
    assert a.captura_guardada and a.pedir_pantalla and len(escritorio.capturas) == 1


def test_el_archivo_de_la_captura_no_se_queda_y_cada_peticion_tiene_el_suyo(escritorio):
    _permiso("si")
    a = _asistente()
    _pulsar_y_pedir(a, "¿qué pone aquí?")
    primera = Path(a.ruta_captura)
    assert primera.exists()
    a._soltar_captura()
    assert not primera.exists()
    _pulsar_y_pedir(a, "¿y esto qué es?")
    assert Path(a.ruta_captura) != primera


def test_al_pulsar_se_sigue_leyendo_la_ventana(escritorio):
    a = _asistente()
    a._preparar_contexto()
    assert a.titulo == "Documento — Kate" and a.ventana_al_pulsar["id"] == "{ventana-1}"
