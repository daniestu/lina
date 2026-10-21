# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 12b: recetas de pasos. Qué se aprende, cuándo una frase encaja con una receta (y, sobre todo, cuándo NO), y que activar y desactivar no se mezclen."""
import pytest

from lina.nucleo import idioma as I
from lina.nucleo import recetas as R


class Ajustes:
    def get(self, seccion, clave):
        return "es"


@pytest.fixture(autouse=True)
def almacen(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "LECTOR", lambda: Ajustes())
    monkeypatch.setattr(R, "ARCHIVO", tmp_path / "recetas.json")


CAMARA_OFF = [{"herr": "ejecutar_comando", "args": {"comando": "sudo -n modprobe -r uvcvideo", "motivo": "Desactivar la cámara web"}}]
CAMARA_ON = [{"herr": "ejecutar_comando", "args": {"comando": "sudo -n modprobe uvcvideo", "motivo": "Activar la cámara web"}}]


def aprender(frase, pasos, veces=1, **kw):
    r = None
    for _ in range(veces):
        r = R.aprender_pasos(frase, pasos, **kw)
    return r


def test_se_aprende_y_se_repite_con_otras_palabras_de_cortesia():
    aprender("Desactiva la cámara", CAMARA_OFF, comprobar="lsmod", esperado="Module Size", verificada=True)
    r, valor = R.para_frase("Oye, desactiva la cámara por favor")
    assert r["pasos"][0]["args"]["comando"] == "sudo -n modprobe -r uvcvideo" and valor is None
    assert R.para_frase("apaga la cámara")[0]["id"] == r["id"]           # apagar = desactivar
    assert R.para_frase("desactívala")  is None                          # sin decir de qué: a la IA


@pytest.mark.parametrize("frase", ["¿Está desactivada la cámara?", "esta desactivada la camara", "cómo desactivo la cámara", "activa la cámara",
                                   "desactiva la cámara y abre Firefox", "no desactives la cámara", "desactiva el micrófono", "desactiva la cámara web",
                                   "dime si desactivaste la cámara", "desactiva la cámara luego sube el volumen"])
def test_lo_que_no_es_la_misma_orden_no_encaja(frase):
    aprender("desactiva la cámara", CAMARA_OFF, comprobar="lsmod", esperado="Module", verificada=True)
    assert R.para_frase(frase) is None


def test_activar_y_desactivar_son_recetas_distintas():
    aprender("desactiva la cámara", CAMARA_OFF, comprobar="lsmod", esperado="x", verificada=True)
    aprender("activa la cámara", CAMARA_ON, comprobar="lsmod", esperado="uvcvideo", verificada=True)
    assert len([r for r in R._cargar() if r["tipo"] == "pasos"]) == 2
    assert R.para_frase("activa la cámara")[0]["pasos"] == R._cargar()[1]["pasos"]
    assert R.para_frase("desactiva la cámara")[0]["pasos"][0]["args"]["comando"].endswith("-r uvcvideo")


def test_la_misma_secuencia_con_otra_frase_suma_la_frase_y_los_aciertos():
    aprender("desactiva la cámara", CAMARA_OFF)
    aprender("apaga la cámara web", CAMARA_OFF)
    recetas = R._cargar()
    assert len(recetas) == 1 and recetas[0]["exitos"] == 2 and len(recetas[0]["frases"]) == 2
    assert R.para_frase("apaga la cámara web") and R.para_frase("desactiva la cámara web")


def test_sin_comprobar_por_el_codigo_hace_falta_un_segundo_exito():
    aprender("desactiva la cámara", CAMARA_OFF)                          # solo lo confirmó el revisor
    assert R.para_frase("desactiva la cámara") is None
    aprender("desactiva la cámara", CAMARA_OFF)
    assert R.para_frase("desactiva la cámara") is not None


def test_el_numero_se_convierte_en_valor():
    pasos = [{"herr": "audio", "args": {"accion": "volumen", "valor": "40"}}]
    aprender("pon el volumen al 40", pasos, verificada=True, comprobar="wpctl get-volume @DEFAULT_AUDIO_SINK@", esperado="Volume: 0.40")
    receta, valor = R.para_frase("pon el volumen al 70 por favor")
    assert valor == "70" and R.con_valor(receta["pasos"][0]["args"], valor) == {"accion": "volumen", "valor": "70"}
    assert R.para_frase("pon el volumen") is None                       # sin número no encaja con una receta que lo necesita
    assert R.para_frase("pon el volumen al 70 y 80") is None


def test_numero_que_no_esta_en_los_pasos_es_parte_de_la_frase():
    aprender("pon el modo 2 en la lámpara", [{"herr": "ejecutar_comando", "args": {"comando": "lampara --modo-fijo", "motivo": "m"}}], verificada=True)
    assert R.para_frase("pon el modo 2 en la lámpara") is not None
    assert R.para_frase("pon el modo 3 en la lámpara") is None


@pytest.mark.parametrize("pasos", [
    [{"herr": "ejecutar_comando", "args": {"comando": "bluetoothctl --password abc", "motivo": "m"}}],
    [{"herr": "ejecutar_comando", "args": {"comando": "pactl set-source-mute @DEFAULT_SOURCE@ toggle", "motivo": "m"}}],
    [{"herr": "notas", "args": {"accion": "añadir"}}],
    [{"herr": "ejecutar_comando", "args": {"comando": "x", "motivo": "m"}}] * 7,
    [],
])
def test_lo_que_no_se_debe_repetir_no_se_aprende(pasos):
    assert R.aprender_pasos("haz la cosa rara", pasos) is None and R._cargar() == []


@pytest.mark.parametrize("frase", ["¿qué hora es?", "cierra esto y abre eso otro", "", "haz lo de siempre y luego lo otro", "y"])
def test_frases_que_no_son_una_orden_sencilla_no_se_aprenden(frase):
    assert R.aprender_pasos(frase, CAMARA_OFF) is None


def test_dos_fallos_la_olvidan_y_un_acierto_los_perdona():
    r = aprender("desactiva la cámara", CAMARA_OFF, veces=2)
    assert R.para_frase("desactiva la cámara")
    R.resultado_pasos(r["id"], False)
    assert R.para_frase("desactiva la cámara") is None                  # con un fallo suelto ya no se repite sola
    R.resultado_pasos(r["id"], True)
    assert R.para_frase("desactiva la cámara")
    R.resultado_pasos(r["id"], False)
    assert R.resultado_pasos(r["id"], False) == "desactiva la cámara" and R._cargar() == []


def test_olvidar_por_voz_respeta_la_direccion():
    aprender("desactiva la cámara", CAMARA_OFF)
    aprender("activa la cámara", CAMARA_ON)
    assert R.olvidar("olvida cómo desactivar la cámara") == ["desactiva la cámara"]
    assert [r["ajuste"] for r in R._cargar()] == ["activa la cámara"]


def test_la_comprobacion_tolera_ruido_pero_no_otro_estado():
    assert R.coincide_salida("Volume: 0.40", "Volume: 0.40 ")
    assert R.coincide_salida("uvcvideo 114688 1 gspca", "uvcvideo 114688 2 gspca_main otra cosa")
    assert not R.coincide_salida("Volume: 0.40", "Volume: 0.85 [MUTED]")
    assert R.coincide_salida("", "lo que sea")


def test_se_ve_en_la_lista_y_se_prueba_sin_ejecutar():
    aprender("desactiva la cámara", CAMARA_OFF, veces=2)
    salida = []
    assert R.principal([], salida.append) == 0 and any("desactiva la cámara" in s and "*" in s for s in salida)
    salida.clear()
    assert R.principal(["probar", "desactiva la cámara"], salida.append) == 0 and any("modprobe -r uvcvideo" in s for s in salida)
    salida.clear()
    assert R.principal(["probar", "activa la cámara"], salida.append) == 0 and any("IA" in s for s in salida)
    assert R.principal(["borrar", "r9999"], lambda s: None) == 1
    assert R.principal(["borrar", "todas"], lambda s: None) == 0 and R._cargar() == []
    assert R.principal(["rarezas"], lambda s: None) == 2


def test_las_recetas_de_pasos_conviven_con_las_de_siempre():
    R.aprender_comando("luz nocturna", "", "pon la luz nocturna", "kwriteconfig6 --key Active true", "true", "kreadconfig6 --key Active", "leído: true")
    aprender("desactiva la cámara", CAMARA_OFF)
    assert {r["tipo"] for r in R._cargar()} == {"comando", "pasos"}
    assert "pasos" in R.listar() and R.obtener("desactiva la cámara").count("modprobe") == 1
    nota, ids = R.ofrecer("desactiva la cámara")
    assert ids and "modprobe" in nota
