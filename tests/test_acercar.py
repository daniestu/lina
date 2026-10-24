# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Acercar lo oído a las órdenes y al vocabulario propio, y la segunda tanda de `lina probar-voz mas`. Sin tarjeta, sin Ollama, sin modelos."""
import numpy as np

from lina.nucleo import acercar as A
from lina.nucleo import probar_voz as PV
from lina.nucleo import probar_voz_mas as MAS

ORDENES = A.ORDENES["es"]
VOCAB = ["Kate", "Dolphin", "Firefox", "Steam"]


def test_acerca_frases_cortas_a_una_orden():
    assert A.acercar("Pausas.", ORDENES, VOCAB) == ("pausa", [("Pausas.", "pausa")])
    assert A.acercar("Por música", ORDENES, VOCAB)[0] == "pon música"
    assert A.acercar("Silencia al sonido.", ORDENES, VOCAB)[0] == "silencia el sonido"


def test_no_toca_lo_que_ya_esta_bien_ni_lo_que_no_se_parece():
    for frase in ("Sube el volumen", "pon música", "Escribe una nota para mañana con la lista de la compra", "Dime qué tiempo hace en Zaragoza"):
        assert A.acercar(frase, ORDENES, VOCAB) == (frase, [])


def test_una_frase_larga_no_se_convierte_en_una_orden():
    larga = "Pausa la música cuando termine de cargar el juego que he abierto"
    assert A.acercar(larga, ORDENES, VOCAB)[0] == larga


def test_palabra_rara_contra_el_vocabulario_propio():
    texto, cambios = A.acercar("Abre dolfin en la carpeta", ORDENES, ["Dolphin"], umbral_palabra=0.8)
    assert "Dolphin" in texto and cambios


def test_las_ordenes_incluyen_abrir_cada_programa():
    assert "abre Kate" in A.ordenes_para("es", ["Kate"]) and "open Kate" in A.ordenes_para("en", ["Kate"])


def test_vacio_no_rompe():
    assert A.acercar("", ORDENES, VOCAB) == ("", [])


# ----- la segunda tanda
class Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos

    def raise_for_status(self):
        pass


def test_corregir_con_ollama_pide_json_sin_pensar_y_en_cpu_si_se_pide():
    llamadas = []

    class Http:
        def post(self, url, json=None, timeout=None):
            llamadas.append(json)
            return Respuesta({"message": {"content": '{"texto": "Pausa"}'}})
    assert MAS.corregir_con_ollama("m", "Pausas", ORDENES, VOCAB, cpu=True, http=Http()) == "Pausa"
    assert llamadas[0]["options"]["num_gpu"] == 0 and llamadas[0]["format"] == "json" and llamadas[0]["options"]["temperature"] == 0
    assert MAS.corregir_con_ollama("m", "Pausas", ORDENES, VOCAB, cpu=False, http=type("H", (), {"post": lambda s, *a, **k: Respuesta({"message": {"content": "no json"}})})()) == "Pausas"


def test_medir_ollama_suma_con_whisper_y_descarga_cada_modelo():
    soltados = []
    filas = MAS.medir_ollama(["a", "b"], "es", VOCAB, ["Pausa"], 1000, 2400, vram=lambda: 3500,
                             corregir=lambda modelo, texto, *a: dict(MAS.ERRORES["es"]).get(texto, texto), soltar=soltados.append)
    assert len(filas) == 4 and soltados == ["a", "a", "b", "b"]
    f = filas[0]
    assert f["total_mb"] == 2500 and f["vram_mb"] == 100 and f["de"] == len(MAS.ERRORES["es"])
    assert f["bien"] == f["de"] and f["estropea"] == 0


def test_informe_avisa_cuando_se_pasa_del_tope():
    ollama = [{"modelo": "grande", "cpu": False, "bien": 5, "de": 12, "estropea": 1, "de_control": 22, "frio_s": 2.0, "media_s": 0.4, "larga_s": 0.6, "vram_mb": 5000, "total_mb": 7400},
              {"modelo": "grande", "cpu": True, "error": "ConnectionError: x"}]
    texto = MAS.informe([{"calculo": "float16", "error": "RuntimeError: x"}], [], ollama, 2400, "float16")
    assert "⚠" in texto and "no disponible" in texto


def test_elegir_calculo_prefiere_el_ligero_si_no_acierta_menos():
    f = lambda c, a: {"calculo": c, "variante": "pista de siempre", "aciertos": a}              # noqa: E731
    assert MAS.calculo_elegido([f("float16", 14), f("int8_float16", 14)]) == "int8_float16"
    assert MAS.calculo_elegido([f("float16", 14), f("int8_float16", 12)]) == "float16"
    assert MAS.calculo_elegido([{"calculo": "float16", "error": "x"}]) is None


def test_principal_sin_grabaciones_lo_dice(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "nada")
    dicho = []
    assert MAS.principal([], salida=dicho.append) == 1 and "lina probar-voz" in dicho[0]


def test_principal_completo_con_motores_falsos(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "pv")
    monkeypatch.setattr(MAS, "INFORME", tmp_path / "pv" / "informe-mas.txt")
    monkeypatch.setattr(MAS.RUT, "DATOS", tmp_path)
    monkeypatch.setattr(MAS, "vocabulario_propio", lambda: VOCAB)
    monkeypatch.setattr(PV, "_pista", lambda: "")
    monkeypatch.setattr(MAS, "vram_usada_mb", lambda: 1000)
    esperadas = PV.frases()
    for i in range(len(esperadas)):
        PV.guardar_wav(PV.ruta_audio(i), np.ones(PV.FRECUENCIA, dtype="float32") * 0.1)
    cuenta = {"i": 0}

    def cargar(calculo):
        def transcribir(audio, pista=None, palabras=None):
            cuenta["i"] += 1
            return esperadas[(cuenta["i"] - 1) % len(esperadas)]
        return transcribir, lambda: None

    class Http:
        def get(self, url, timeout=None):
            return Respuesta({"models": []})
    dicho = []
    monkeypatch.setattr(MAS.shutil, "which", lambda n: None)
    assert MAS.principal([], salida=dicho.append, cargar=cargar, http=Http()) == 0
    todo = "\n".join(dicho)
    assert "WHISPER EN LA TARJETA" in todo and "ACERCAR" in todo and "No hay ningún modelo pequeño" in todo
    assert (tmp_path / "pv" / "informe-mas.txt").exists()
