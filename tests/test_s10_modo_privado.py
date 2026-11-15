# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S10: lo que promete el modo privado, una prueba por promesa. HOME aislado (conftest); los archivos de recetas y memoria, en carpetas temporales.

  · El registro, y lo que el servicio vuelca al journal (su salida estándar), no lleva lo que dices ni lo que contesto, ni la consulta ni la dirección de
    una web, aunque privacidad.registrar_preguntas esté activo. Fuera del modo privado, todo sigue como antes.
  · No se aprende ninguna receta nueva; las que hay se siguen usando.
  · La memoria se usa, pero no se apunta nada nuevo; olvidar sí se puede.
  · Los manuales dicen lo que el modo privado no cubre.
"""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import memoria as MEM
from lina.nucleo import recetas as REC
from lina.nucleo import registro as REG
from lina.nucleo import rutas as RUT

PREGUNTA = "¿Cuánto cuesta el piso de la calle Inventada 42?"
RESPUESTA = "Según la web, unos ciento veinte mil euros."
URL = "https://pisos-inventados.test/anuncio/42"
A = None


@pytest.fixture(autouse=True)
def asistente_mod(tmp_path, monkeypatch):
    global A
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    A = asistente
    monkeypatch.setattr(A, "ARCHIVO_PRIVADO", tmp_path / "datos" / "modo_privado")
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(MEM, "ARCHIVO", tmp_path / "memoria.json")


def _asistente(privado):
    a = A.Asistente.__new__(A.Asistente)
    a.historial, a.origen_voz_libre, a.interrumpiendo = [], False, False
    a.contexto, a.titulo, a.ids_recetas, a.grupos_previos = {"tipo": "general", "nombre": None, "clase": ""}, "", [], set()
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    a.hilo_captura = MagicMock()
    a.captura_guardada = None
    a._poner_modo_privado(privado)
    a._intentar_directa = lambda p, c: None
    a._hay_recuerdos_pertinentes = lambda p: False
    a._intentar_receta_pasos = lambda p, c: None
    a.nueva_tarea = lambda: None
    a._decidir_pantalla = lambda imagen, pregunta: None
    a.elegir_modo = lambda t: ("rapido", "")
    a.pista_de_voz = lambda t: ""
    a._aprender_automatico = a._aprender_pasos = lambda: None
    a.decir = lambda t: None
    a._anotar_tiempos = lambda *x: None

    def responder(pregunta, imagen, modo):              # la IA lee una web (la descarga falla y se apunta), y contesta
        a.leer_web({"url": URL})
        return RESPUESTA, "prueba"
    a.responder = responder
    return a


def _turno(monkeypatch, privado):
    monkeypatch.setattr(A, "preparar_imagen", lambda ruta=None: None)
    monkeypatch.setattr(A.W, "leer", MagicMock(side_effect=A.W.ErrorWeb(f"No encuentro el servidor de {URL}.")))
    a = _asistente(privado)
    a._atender(PREGUNTA, 0.0, origen="atajo")
    return a


def test_en_privado_el_journal_no_lleva_la_pregunta_la_direccion_ni_la_respuesta(monkeypatch, capsys):
    _turno(monkeypatch, privado=True)
    salida = capsys.readouterr().out
    assert "Respuesta [" in salida                                  # la línea sigue, para saber que hubo respuesta…
    for privado in (PREGUNTA, RESPUESTA, URL, "pisos-inventados", "Inventada", "ciento veinte"):
        assert privado not in salida, privado                       # …pero sin nada de lo tuyo


def test_fuera_del_modo_privado_todo_sigue_como_antes(monkeypatch, capsys):
    _turno(monkeypatch, privado=False)
    salida = capsys.readouterr().out
    assert RESPUESTA in salida and URL in salida


@pytest.mark.parametrize("linea", [                                # las líneas reales que llevan texto tuyo (su formato, tal cual)
    f"Pregunta: «{PREGUNTA}» (1.2 s)",
    "Búsqueda de Google (gratis) «precio piso calle Inventada» en pisos-inventados.test: 5 fuentes (0.8 s)",
    "Búsqueda de reserva (DuckDuckGo) «precio piso calle Inventada»: 3 resultados (1.0 s)",
    f"Leer web {URL}: No he podido conectar con esa página.",
    "Acción [autonomo]: xdg-open pisos-inventados.test  # ver el anuncio",
    "Nota creada: notas/piso-calle-inventada.md",
    "Recordatorio r1: «llamar por el piso de la calle Inventada» para mañana",
    "Manos libres: me has llamado y has dicho «busca el piso de la calle Inventada»",
    "Ajuste cambiado por la IA: 'fondo' -> 'calle Inventada': hecho",
])
def test_cada_linea_con_texto_tuyo_queda_tapada(linea, capsys):
    REG.privado(True)
    REG.log(linea)
    salida = capsys.readouterr().out
    assert "Inventada" not in salida and "pisos-inventados" not in salida, salida
    assert salida.strip().endswith("…")


def test_las_frases_del_turno_se_tapan_aunque_vayan_sin_comillas(capsys):
    REG.privado(True)
    REG.tapar(PREGUNTA)
    REG.log(f"Lo que pediste {PREGUNTA} sigue en marcha")
    assert PREGUNTA not in capsys.readouterr().out


def test_las_lineas_sin_texto_tuyo_quedan_enteras(capsys):
    REG.privado(True)
    REG.log("Escuchando…")
    assert capsys.readouterr().out.strip().endswith("Escuchando…")


def test_los_registros_de_cada_modulo_pasan_por_el_mismo_sitio(capsys):
    from lina.nucleo import comandos, politica, presupuesto
    REG.privado(True)
    for modulo in (comandos, politica, presupuesto, REC):
        modulo.log("Prueba: calle Inventada")
    assert "Inventada" not in capsys.readouterr().out


def test_quitar_el_modo_privado_olvida_las_frases_y_vuelve_a_registrar(capsys):
    REG.privado(True)
    REG.tapar(PREGUNTA)
    REG.privado(False)
    REG.log(f"Pregunta: «{PREGUNTA}»")
    assert PREGUNTA in capsys.readouterr().out


# ---------------------------------------------------------------- recetas
def _aprender_todas():
    return [
        REC.aprender_kde("animaciones", "", "quita las animaciones", "kwinrc", ["Plugins"], "blurEnabled", "false", "kcm_kwin", "Desenfoque", "apagado"),
        REC.aprender_comando("brillo del teclado", "", "baja el brillo del teclado", "brightnessctl -d kbd set {valor}", "0", "brightnessctl -d kbd get", "0"),
        REC.aprender_interfaz("activar el modo oscuro de kate", "", "", [{"accion": "pulsar", "ventana": "Kate", "nombre": "Oscuro", "rol": "botón"}], "", ""),
        REC.aprender_pasos("pon el volumen al 30", [{"herr": "ejecutar_comando", "args": {"comando": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%"}}]),
    ]


def test_en_privado_ninguna_forma_de_aprender_escribe_recetas():
    REG.privado(True)
    assert _aprender_todas() == [None, None, None, None]
    assert not REC.ARCHIVO.exists()


def test_fuera_del_modo_privado_se_siguen_aprendiendo():
    assert all(_aprender_todas())
    assert REC.ARCHIVO.exists()


def test_en_privado_una_receta_que_ya_habia_se_usa_y_se_apunta_si_salio_bien():
    receta = REC.aprender_pasos("pon el volumen al 30", [{"herr": "ejecutar_comando", "args": {"comando": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%"}}],
                                comprobar="wpctl get-volume @DEFAULT_AUDIO_SINK@", esperado="Volume: 0.30", verificada=True)
    REC.resultado_pasos(receta["id"], True)
    REG.privado(True)
    usada = REC.para_frase("pon el volumen al 30")
    assert usada and usada[0]["id"] == receta["id"]
    exitos = lambda: next(r for r in REC._cargar() if r["id"] == receta["id"])["exitos"]       # noqa: E731
    antes = exitos()
    REC.resultado_pasos(receta["id"], True)
    assert exitos() == antes + 1
    assert len(REC._cargar()) == 1


def test_la_comprobacion_de_una_receta_de_interfaz_no_cambia_en_privado():
    REG.privado(True)
    pasos = [{"accion": "pulsar", "ventana": "Kate", "nombre": "Oscuro", "rol": "botón"}]
    assert REC.aprender_interfaz("activar el modo oscuro de kate", "", "", pasos, "", "", solo_comprobar=True) is True


# ---------------------------------------------------------------- memoria
def test_en_privado_recuerda_que_no_apunta_nada_y_lo_dice():
    REG.privado(True)
    hecho, dicho = MEM.recordar("mi equipo favorito es el de mi barrio")
    assert not hecho and "modo privado" in dicho
    assert not MEM.ARCHIVO.exists()


def test_en_privado_lo_que_ya_habia_se_usa_y_se_puede_olvidar():
    assert MEM.recordar("prefiero el modo oscuro en todo")[0]
    REG.privado(True)
    assert any("modo oscuro" in r for r in MEM.relevantes("pon el modo oscuro"))           # a la IA le sigue llegando
    assert MEM.olvidar("modo oscuro")[0]
    assert not any("modo oscuro" in r["texto"] for r in MEM._cargar())


# ---------------------------------------------------------------- el manual
@pytest.mark.parametrize("archivo, frases", [
    ("privacidad.md", ["El proveedor de la IA sigue recibiendo tus preguntas", "Steam y ProtonDB ven tu dirección IP", "journalctl --user -u lina",
                       "No aprendo recetas nuevas", "No apunto nada nuevo en la memoria"]),
    ("privacidad.en.md", ["The AI provider still receives your questions", "Steam and ProtonDB see your IP address", "journalctl --user -u lina",
                          "I don't learn new recipes", "I don't note anything new in my memory"]),
])
def test_el_manual_dice_lo_que_cubre_y_lo_que_no(archivo, frases):
    texto = (RUT.DEFECTOS / "ayuda" / archivo).read_text(encoding="utf-8")
    for frase in frases:
        assert frase in texto, (archivo, frase)
