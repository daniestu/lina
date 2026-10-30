# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""N2: si la IA abre la ficha de una plataforma (Netflix, Movistar…) con un número que no ha salido de ninguna búsqueda, página ni comando de esta
petición, el código no deja que la respuesta lo dé por bueno; y leer el registro de Lina (que puede llevar tus preguntas) pide confirmación.
Con las órdenes del registro real de «ponme Aquí no hay quien viva en Netflix». Sin red ni IA."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import contenido as CONT
from lina.nucleo import herramientas as H
from lina.nucleo import turnos as TU

PLATAFORMAS = sorted({d for ds in CONT.PLATAFORMAS.values() for d in ds})
PIDE = "Ponme, aquí no hay quien viva en Netflix."
ABRIR_INVENTADA = ("ejecutar_comando", {"comando": 'xdg-open "https://www.netflix.com/title/70281358"'}, "código de salida: 0\nAbierto")
SIN_BUSQUEDA = ("buscar_web", {"consulta": "aquí no hay quien viva netflix"}, "La búsqueda en internet ha llegado a su límite de uso")
BUSQUEDA_A_MANO = ("ejecutar_comando", {"comando": "python3 -c 'import urllib.request…'  # lite.duckduckgo.com"},
                   "código de salida: 0\nhttps://www.netflix.com/es/title/81439208")


def _lectura(c):
    return H.clasificar(c)[0] == "lectura"


def test_el_numero_inventado_del_registro_real_se_detecta():
    assert TU.enlace_sin_comprobar([SIN_BUSQUEDA, ABRIR_INVENTADA], PLATAFORMAS, _lectura, PIDE) == ("https://www.netflix.com/title/70281358", "netflix.com")


def test_si_el_numero_salio_de_una_busqueda_o_de_un_comando_vale():
    buscado = ("buscar_web", {}, "[1] Ve Aquí no hay quien viva | Netflix (netflix.com) https://www.netflix.com/es/title/81439208\nVecinos…")
    abrir = ("ejecutar_comando", {"comando": "xdg-open https://www.netflix.com/es/title/81439208"}, "Abierto")
    assert TU.enlace_sin_comprobar([buscado, abrir], PLATAFORMAS, _lectura, PIDE) is None
    assert TU.enlace_sin_comprobar([BUSQUEDA_A_MANO, abrir], PLATAFORMAS, _lectura, PIDE) is None          # la búsqueda que hizo la IA a mano


def test_leer_una_ficha_con_curl_no_es_abrirla():
    leer = ("ejecutar_comando", {"comando": 'curl -s -L "https://www.netflix.com/es/title/81439208" -A "Mozilla/5.0" | grep -i "<title>"'}, "(sin salida)")
    assert TU.enlace_sin_comprobar([leer], PLATAFORMAS, _lectura, PIDE) is None


def test_si_lo_dijiste_tu_o_no_es_una_plataforma_no_se_corrige():
    abrir = ("ejecutar_comando", {"comando": "xdg-open https://www.netflix.com/title/70281358"}, "Abierto")
    assert TU.enlace_sin_comprobar([abrir], PLATAFORMAS, _lectura, "abre https://www.netflix.com/title/70281358") is None
    otra = ("ejecutar_comando", {"comando": "xdg-open https://www.ejemplo.test/title/70281358"}, "Abierto")
    assert TU.enlace_sin_comprobar([otra], PLATAFORMAS, _lectura, PIDE) is None
    portada = ("ejecutar_comando", {"comando": "xdg-open https://www.netflix.com/"}, "Abierto")
    assert TU.enlace_sin_comprobar([portada], PLATAFORMAS, _lectura, "abre netflix") is None


@pytest.fixture
def asistente():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], duda=None, efecto_sin_comprobar=False)
    a.pregunta_pura = PIDE
    return a


def test_la_respuesta_que_lo_da_por_hecho_se_corrige(asistente):
    asistente.acciones_turno = [SIN_BUSQUEDA, ABRIR_INVENTADA]
    r = asistente.asegurar_honestidad_final("Ya tienes abierta la página de Aquí no hay quien viva en Netflix.")
    assert r.startswith("Ya tienes abierta") and "Ojo, corrijo: la ficha de Netflix que he abierto no ha salido de ninguna búsqueda" in r


def test_si_la_respuesta_ya_reconoce_la_duda_no_se_toca(asistente):
    asistente.acciones_turno = [SIN_BUSQUEDA, ABRIR_INVENTADA]
    texto = "Te he abierto una ficha de Netflix, pero no he podido comprobar que sea la serie."
    assert asistente.asegurar_honestidad_final(texto) == texto


@pytest.mark.parametrize("comando", ["journalctl --user -u lina -n 60 --no-pager", 'journalctl --user -u lina --since "10 minutes ago" | grep -C 2 -i "netflix"',
                                     "journalctl --user-unit=lina -n 5"])
def test_leer_el_registro_de_lina_pide_confirmacion(comando):
    clase, motivo = H.clasificar(comando)
    assert clase == "critico" and "preguntas anteriores" in motivo


def test_leer_el_registro_de_otro_servicio_sigue_libre():
    assert H.clasificar("journalctl -u NetworkManager -n 20")[0] == "lectura"
