# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Sin confirmación no hay éxito. El caso real: «Ábreme Steam» empataba con los juegos que se lanzan con `steam`, la IA repitió abrir_app diez veces, la
comprobación dio timeout y respondió «Abierto.» sin haber abierto nada. Con los lanzadores de aquel equipo; sin red, sin IA y sin abrir nada de verdad."""
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import comandos as C
from lina.nucleo import herramientas as H
from lina.nucleo import ia as IA
from lina.nucleo import proveedores as PROV
from lina.nucleo import turnos as TU

SISTEMA = "/usr/share/applications/"
STEAM = {"nombre": "Steam", "id": "steam", "comando": "/usr/bin/steam", "origen": SISTEMA + "steam.desktop"}
NMS = {"nombre": "No Man's Sky", "id": "No Man's Sky", "comando": "steam steam://rungameid/275850", "origen": SISTEMA + "nms.desktop"}
SKYRIM = {"nombre": "The Elder Scrolls V: Skyrim Special Edition", "id": "Skyrim", "comando": "steam steam://rungameid/489830", "origen": SISTEMA + "skyrim.desktop"}
EMPATADOS = [{"nombre": "Steam", "id": "steam-a", "comando": "/usr/bin/steam-a", "origen": SISTEMA + "a.desktop"},
             {"nombre": "Steam", "id": "steam-b", "comando": "/usr/bin/steam-b", "origen": SISTEMA + "b.desktop"}]
VARIOS = "Hay varios programas que encajan con «Steam»: «Steam» (id steam-a); «Steam» (id steam-b). Elige el que corresponde."


@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor()
    e.lanzados = []
    e.lanzar = lambda comando: e.lanzados.append(comando) or "Lanzado."
    monkeypatch.setattr(H, "juegos", None)
    monkeypatch.setattr(H, "anotar", lambda t: None)
    return e


def _con_apps(monkeypatch, apps):
    real = C.buscar_app
    monkeypatch.setattr(H.comandos, "buscar_app", lambda n, a=None: real(n, apps))


@pytest.fixture
def asistente(ej):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = ej
    a.pregunta_pura = "Ábreme Steam."
    a.acciones_turno, a.guion_herramientas, a.paso_guion, a.t_tarea = [], [], 0, time.time()
    a.max_tiempo, a.max_tokens = 300, 10 ** 9
    a._repetida = None
    return a


class Repetidor:
    """Un modelo que pide siempre lo mismo, como el del registro real."""
    nombre, busqueda_nativa = "falso", False

    def __init__(self, llamada):
        self.llamada, self.turnos = llamada, 0

    def turno(self, clave, modelo, sistema, mensajes, **k):
        self.turnos += 1
        return PROV.Respuesta(llamadas=[self.llamada], turno={})


# ---------------------------------------------------------------- Steam
def test_steam_ya_no_empata_con_los_juegos_que_se_lanzan_con_steam():
    r = C.buscar_app("Steam", [STEAM, NMS, SKYRIM])
    assert r[0] == (100, STEAM) and all(p < 100 for p, _ in r[1:])


def test_abrir_steam_lo_abre_a_la_primera(ej, monkeypatch):
    _con_apps(monkeypatch, [STEAM, NMS, SKYRIM])
    assert ej.abrir_app("Steam").startswith("Abierto «Steam»") and ej.lanzados == ["/usr/bin/steam"]


def test_un_comando_sigue_valiendo_si_ningun_programa_se_llama_asi():
    assert C.buscar_app("steam", [NMS])[0][0] == 100


def test_el_id_exacto_deshace_un_empate_de_verdad(ej, monkeypatch):
    _con_apps(monkeypatch, EMPATADOS)
    assert ej.abrir_app("Steam").startswith("Hay varios") and ej.lanzados == []
    assert ej.abrir_app("steam-b").startswith("Abierto") and ej.lanzados == ["/usr/bin/steam-b"]


# ---------------------------------------------------------------- el bucle
def test_el_bucle_del_registro_real_se_corta_y_dice_el_motivo(asistente, ej, monkeypatch):
    _con_apps(monkeypatch, EMPATADOS)
    modelo = Repetidor(PROV.Llamada("abrir_app", {"nombre": "Steam"}))
    r = IA.preguntar_ia(modelo, "c", "m", "Ábreme Steam.", None, herramientas=[{"name": "abrir_app"}], ejecutar_herramienta=asistente.ejecutar_herramienta, sistema="s")
    assert modelo.turnos == 3                                                  # antes, 11 llamadas a la IA
    assert len(asistente.acciones_turno) == 2 and ej.lanzados == []
    assert r.startswith("No lo he abierto: Hay varios programas que encajan con «Steam»") and r.endswith(".")


def test_si_el_resultado_cambia_no_es_un_bucle(asistente):
    resultados = iter(["uno", "dos", "tres", "cuatro"])
    asistente._ejecutar_herramienta = lambda n, a: next(resultados)
    for _ in range(4):
        asistente.ejecutar_herramienta("ejecutar_comando", {"comando": "wpctl status"})
    assert len(asistente.acciones_turno) == 4


def test_esperar_a_que_algo_cambie_no_es_un_bucle(asistente):
    asistente._ejecutar_herramienta = lambda n, a: "aún no"
    for _ in range(4):
        asistente.ejecutar_herramienta("ejecutar_comando", {"comando": "sleep 5; systemctl is-active x"})
    assert len(asistente.acciones_turno) == 4


def test_otra_herramienta_en_medio_reinicia_la_cuenta(asistente):
    asistente._ejecutar_herramienta = lambda n, a: "igual"
    for nombre in ("a", "a", "b", "a", "a"):
        asistente.ejecutar_herramienta(nombre, {})
    assert len(asistente.acciones_turno) == 5


# ---------------------------------------------------------------- sin confirmación no hay éxito
def test_el_abierto_del_registro_real_se_sustituye(asistente):
    asistente.acciones_turno = [("abrir_app", {"nombre": "Steam"}, VARIOS)] * 10
    assert asistente.asegurar_honestidad_final("Abierto.").startswith("No lo he abierto: Hay varios programas que encajan con «Steam»")


FALLO = ("ejecutar_comando", {"comando": "gsettings set x y"}, "código de salida: 1 (0 s)\n\nNo such key")
LEER = ("ejecutar_comando", {"comando": "ls ~/Descargas"}, "código de salida: 0 (0 s)\n\ninforme.pdf")


@pytest.mark.parametrize("peticion, acciones", [
    ("Sube el volumen.", []),                                                  # no se hizo nada
    ("Borra el informe de Descargas.", [LEER]),                                # solo se leyó
    ("Cambia el fondo de pantalla.", [FALLO]),                                 # lo intentado falló
    ("Instala gimp.", [("ejecutar_comando", {"comando": "paru -S gimp"}, "BLOQUEADO: no se instala")]),
    ("Crea una carpeta nueva.", []),
    ("Reinicia el servicio de red.", []),
    ("Pausa la música.", []),
    ("Apaga la pantalla.", []),
])
def test_cualquier_orden_sin_efecto_no_se_da_por_hecha(asistente, peticion, acciones):
    asistente.pregunta_pura, asistente.acciones_turno = peticion, acciones
    assert asistente.asegurar_honestidad_final("Hecho.").startswith("No lo he hecho: ")


def test_el_motivo_dice_lo_que_paso(asistente):
    asistente.pregunta_pura, asistente.acciones_turno = "Cambia el fondo de pantalla.", [FALLO]
    assert asistente.asegurar_honestidad_final("Listo.") == "No lo he hecho: No such key."
    asistente.acciones_turno = []
    assert asistente.asegurar_honestidad_final("Listo.") == "No lo he hecho: no he llegado a hacer nada."


@pytest.mark.parametrize("peticion, acciones, respuesta", [
    ("Sube el volumen.", [("ejecutar_comando", {"comando": "wpctl set-volume @DEFAULT_SINK@ 5%+"}, "código de salida: 0 (0 s)")], "Hecho."),   # consta
    ("Ábreme Steam.", [("abrir_app", {"nombre": "Steam"}, "Abierto «Steam». Ya está.")], "Abierto."),
    ("Cuéntame un dato curioso.", [], "Hecho curioso: los pulpos tienen tres corazones."),                                                      # no pide hacer nada
    ("¿Has abierto Steam?", [], "Hecho."),                                                                                                       # es una pregunta
    ("Sube el volumen.", [], "No he podido subirlo."),                                                                                           # ya lo reconoce
])
def test_lo_que_consta_o_no_es_una_orden_no_se_toca(asistente, peticion, acciones, respuesta):
    asistente.pregunta_pura, asistente.acciones_turno = peticion, acciones
    assert asistente.asegurar_honestidad_final(respuesta) == respuesta


def test_lo_pendiente_de_confirmar_no_se_sustituye(asistente):
    asistente.ejecutor.pendientes = ["algo"]
    assert asistente.asegurar_honestidad_final("Abierto.") == "Abierto."


@pytest.mark.parametrize("frase, sale", [("Ábreme Steam.", True), ("Sube el volumen", True), ("Por favor, bórralo", True), ("Bórralo", True),
                                         ("Dime la hora", False), ("Cuéntame algo", False), ("¿Subes el volumen?", False)])
def test_pide_hacer(frase, sale):
    assert TU.pide_hacer(frase) is sale


def test_motivo_corto():
    assert TU.motivo_corto("código de salida: 1 (0 s)\n\nNo such key. Y más texto") == "No such key"
    assert len(TU.motivo_corto("x" * 500)) == 160
