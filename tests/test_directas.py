# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12: qué frases son una orden directa (sin IA) y, sobre todo, cuáles NO lo son. Función pura: sin sistema ni red."""
import pytest

from lina.nucleo import directas as D
from lina.nucleo import idioma as I


class Ajustes:
    def __init__(self, idioma):
        self.idioma = idioma

    def get(self, seccion, clave):
        return self.idioma


@pytest.fixture(autouse=True)
def espanol(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("es"))


@pytest.mark.parametrize("frase,esperado", [
    ("Abre Firefox.", ("abrir_app", {"nombre": "firefox"})),
    ("Abre Dolphin.", ("abrir_app", {"nombre": "dolphin"})),
    ("Ábreme Steam", ("abrir_app", {"nombre": "steam"})),
    ("abre el navegador", ("abrir_app", {"nombre": "navegador"})),
    ("Puedes abrir Visual Studio Code", ("abrir_app", {"nombre": "visual studio code"})),
    ("Oye, abre Spotify, por favor.", ("abrir_app", {"nombre": "spotify"})),
    ("lanza Heroic Games Launcher", ("abrir_app", {"nombre": "heroic games launcher"})),
    ("abre la aplicación de Stremio", ("abrir_app", {"nombre": "stremio"})),
    ("Sube el volumen.", ("volumen", {"accion": "subir"})),
    ("sube un poco el volumen", ("volumen", {"accion": "subir"})),
    ("Baja el volumen", ("volumen", {"accion": "bajar"})),
    ("baja el volumen un 20 por ciento", ("volumen", {"accion": "bajar", "valor": "20"})),
    ("sube el volumen un 15%", ("volumen", {"accion": "subir", "valor": "15"})),
    ("más volumen", ("volumen", {"accion": "subir"})),
    ("menos volumen", ("volumen", {"accion": "bajar"})),
    ("Pon el volumen al 40", ("volumen", {"accion": "volumen", "valor": "40"})),
    ("pon el volumen al 40 por ciento", ("volumen", {"accion": "volumen", "valor": "40"})),
    ("sube el volumen al 80", ("volumen", {"accion": "volumen", "valor": "80"})),
    ("volumen al 30%", ("volumen", {"accion": "volumen", "valor": "30"})),
    ("¿Puedes abrir Steam?", ("abrir_app", {"nombre": "steam"})),             # Whisper pone ¿? a las peticiones educadas
    ("Maximiza esta ventana.", ("ventanas", {"accion": "maximizar", "ventana": "activa"})),
    ("maximiza", ("ventanas", {"accion": "maximizar", "ventana": "activa"})),
    ("Pon esta ventana en pantalla completa.", ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})),
    ("pantalla completa", ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})),
    ("quita la pantalla completa", ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})),
    ("minimiza esta ventana", ("ventanas", {"accion": "minimizar", "ventana": "activa"})),
    ("muestra el escritorio", ("ventanas", {"accion": "mostrar_escritorio"})),
    ("¿Qué hora es?", ("hora", {"que": "hora"})),
    ("dime la hora", ("hora", {"que": "hora"})),
    ("me puedes decir la hora", ("hora", {"que": "hora"})),
    ("¿Qué día es hoy?", ("hora", {"que": "fecha"})),
    ("a qué día estamos", ("hora", {"que": "fecha"})),
    ("Silencia el sonido.", ("silencio", {"accion": "silenciar"})),
    ("silencia", ("silencio", {"accion": "silenciar"})),
    ("Silencia, el sonido.", ("silencio", {"accion": "silenciar"})),
    ("quita el silencio", ("silencio", {"accion": "activar_sonido"})),
    ("activa el sonido", ("silencio", {"accion": "activar_sonido"})),
])
def test_frases_que_son_ordenes_directas(frase, esperado):
    assert D.entender(frase) == esperado


@pytest.mark.parametrize("frase", [
    "",                                                          # nada
    "cómo abro Firefox",                                         # pregunta
    "qué pasa si abro Firefox",
    "no abras Firefox",                                          # negación
    "nunca abras Steam",
    "abre Firefox y busca recetas de tortilla",                  # encadena otra cosa
    "abre Steam y luego Discord",
    "abre Firefox en el otro monitor",
    "abre una ventana nueva",                                    # no es un programa
    "abre la puerta",
    "abre la carpeta de descargas",
    "abre el archivo de configuración",
    "abre algo",
    "abre todas las pestañas",
    "abre la página de youtube",
    "sube el volumen de la música de Spotify",                   # de una app concreta: lo resuelve la IA
    "sube la luz",
    "pon la música",
    "cállate",                                                   # eso es «para de hablar», no silenciar
    "borra todo",
    "cierra esta ventana",                                       # cerrar pierde trabajo: nunca directa
    "maximiza todas las ventanas y abre Firefox",
    "qué hora es en Tokio",                                      # otra zona: lo sabe la IA
    "qué día cae el próximo viernes",
    "apaga el ordenador",
    "reinicia el equipo",
    "instala Stremio",
    "abre " + "x" * 90,                                          # demasiado largo
    "qué volumen tengo",
    "dime el volumen",
])
def test_frases_que_NO_son_ordenes_directas(frase):
    assert D.entender(frase) is None


def test_en_ingles(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    assert D.entender("Open Firefox.") == ("abrir_app", {"nombre": "firefox"})
    assert D.entender("Could you please open the Steam app") == ("abrir_app", {"nombre": "steam"})
    assert D.entender("turn the volume up") == ("volumen", {"accion": "subir"})
    assert D.entender("volume down") == ("volumen", {"accion": "bajar"})
    assert D.entender("set the volume to 40") == ("volumen", {"accion": "volumen", "valor": "40"})
    assert D.entender("mute") == ("silencio", {"accion": "silenciar"})
    assert D.entender("unmute the sound") == ("silencio", {"accion": "activar_sonido"})
    assert D.entender("open Steam and then Discord") is None
    assert D.entender("don't open Steam") is None
    assert D.entender("how do I open Steam") is None
    assert D.entender("open the door") is None
    assert D.entender("What time is it?") == ("hora", {"que": "hora"})
    assert D.entender("what's the date today") == ("hora", {"que": "fecha"})
    assert D.entender("maximize this window") == ("ventanas", {"accion": "maximizar", "ventana": "activa"})
    assert D.entender("full screen") == ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})
    assert D.entender("show the desktop") == ("ventanas", {"accion": "mostrar_escritorio"})
    assert D.entender("what time is it in Tokyo") is None


def test_frase_de_volumen():
    assert D.frase_de_volumen("Ventana: Volume: 0.85") == "Volumen al 85 %."
    assert D.frase_de_volumen("Volume: 0.40 [MUTED]") == "Está silenciado."
    assert D.frase_de_volumen("no sé") is None


def test_frases_de_hora_y_fecha():
    from datetime import datetime
    assert D.frase_de_hora(datetime(2026, 10, 21, 16, 58)) == "Son las 16:58."
    assert D.frase_de_hora(datetime(2026, 10, 21, 1, 5)) == "Es la 1:05."
    assert D.frase_de_hora(datetime(2026, 10, 21, 0, 5)) == "Son las 00:05."
    assert D.frase_de_fecha(datetime(2026, 10, 21, 9, 0)) == "Hoy es miércoles 21 de octubre."


def test_lina_directas_lista_y_prueba():
    salida = []
    assert D.principal([], salida.append) == 0 and "abrir_app" in "\n".join(salida) and "activadas" in salida[0]
    salida.clear()
    assert D.principal(["probar", "abre", "Firefox"], salida.append) == 0 and "orden directa «abrir_app»" in salida[0]
    salida.clear()
    assert D.principal(["probar", "borra todo"], salida.append) == 0 and "no es una orden directa" in salida[0]
    assert D.principal(["probar"], salida.append) == 2 and D.principal(["otra"], salida.append) == 2


@pytest.mark.parametrize("frase,accion", [
    ("Pausa", "pausar"), ("pausa la música", "pausar"), ("pon la música en pausa", "pausar"), ("para la música", "pausar"), ("Oye, pausa, por favor.", "pausar"),
    ("reanuda", "reanudar"), ("sigue con la música", "reanudar"), ("continúa la reproducción", "reanudar"), ("dale al play", "reanudar"), ("quita la pausa", "reanudar"),
    ("siguiente", "siguiente"), ("la siguiente canción", "siguiente"), ("pasa a la siguiente", "siguiente"), ("salta esta canción", "siguiente"),
    ("anterior", "anterior"), ("la canción anterior", "anterior"), ("vuelve a la anterior", "anterior"),
])
def test_reproduccion(frase, accion):
    assert D.entender(frase) == ("reproduccion", {"accion": accion})


@pytest.mark.parametrize("frase", [
    "pon la música", "pon música de Queen",                      # empezar algo nuevo necesita elegir qué: la IA
    "para", "sigue", "continúa",                                 # sueltas pueden ser cualquier cosa
    "no pauses la música", "cuál es la siguiente", "cómo pauso la música",
    "pausa la música y abre Firefox", "pausa el temporizador", "siguiente capítulo", "pausa en 5 minutos",
])
def test_reproduccion_que_no_es_directa(frase):
    r = D.entender(frase)
    assert r is None or r[0] != "reproduccion"


def test_reproduccion_en_ingles(monkeypatch):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes("en"))
    for frase, accion in (("pause", "pausar"), ("pause the music", "pausar"), ("resume", "reanudar"), ("play", "reanudar"), ("next song", "siguiente"),
                          ("skip", "siguiente"), ("previous song", "anterior"), ("go back a song", "anterior")):
        assert D.entender(frase) == ("reproduccion", {"accion": accion}), frase
    assert D.entender("how do I pause the music") is None
