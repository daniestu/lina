# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La prueba grande: las frases son coherentes con `directas`, los números cuentan bien y todo corre con motores falsos."""
import numpy as np

from lina.nucleo import directas as DIR
from lina.nucleo import probar_voz as PV
from lina.nucleo import probar_voz_grande as G
from lina.nucleo import probar_voz_mas as MAS


def test_las_frases_directas_son_directas_y_las_largas_no():
    assert all(DIR.entender(f) is not None for f in G.DIRECTAS_ES), [f for f in G.DIRECTAS_ES if DIR.entender(f) is None]
    assert all(DIR.entender(f) is None for f in G.LARGAS_ES), [f for f in G.LARGAS_ES if DIR.entender(f) is not None]
    assert len(G.frases()) == len(G.DIRECTAS_ES) + len(G.LARGAS_ES) >= 90
    assert len({f for f, _ in G.frases()}) == len(G.frases())                  # ninguna repetida


def test_ninguna_frase_lleva_cifras():
    assert not any(any(c.isdigit() for c in f) for f, _ in G.frases())


def test_evaluar_cuenta_texto_ordenes_y_falsas():
    lista = [("Pausa", True), ("Abre Firefox", True), ("Cuéntame un chiste corto", False), ("Pon música", False)]
    r = G.evaluar(lista, ["Pausas", "abre firefox.", "Cuéntame un chiste corto", "Pausa"])
    assert r["texto_ok"] == 2 and r["directa_ok"] == 1 and r["directas"] == 2 and r["directa_falsa"] == 1


def test_comparar_y_politica_barata():
    lista = [("Pausa", True), ("Pon música", False), ("Sube el volumen", True)]
    antes = ["Pausas", "Pon música", "Sube lo loven"]
    despues = ["Pausa", "Pon la música", "Sube el volumen"]
    arregla, estropea = G.comparar(lista, antes, despues)
    assert arregla == [("Pausas", "Pausa"), ("Sube lo loven", "Sube el volumen")] and estropea == [("Pon música", "Pon la música")]
    assert G.solo_si_no_es_directa(["Pausa", "Pon música"], ["Pausa.", "Pon la música"]) == ["Pausa", "Pon la música"]


class Respuesta:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d

    def raise_for_status(self):
        pass


def test_grabar_se_puede_parar_y_seguir(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "pv")
    dicho, cuenta = [], {"n": 0}

    def grabar(entrada=None, salida=None):
        cuenta["n"] += 1
        if cuenta["n"] > 3:
            raise KeyboardInterrupt
        return np.ones(PV.FRECUENCIA, dtype="float32") * 0.1
    assert G.grabar_todas(False, grabar=grabar, salida=dicho.append) == 3
    cuenta["n"] = 100                                                           # al volver, no repite las que ya están
    dicho.clear()
    G.grabar_todas(False, grabar=grabar, salida=dicho.append)
    assert any("sigo por donde lo dejaste" in d for d in dicho) and "Frase 1 de" not in "".join(dicho)


def test_principal_medir_con_motores_falsos(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "pv")
    monkeypatch.setattr(MAS, "vocabulario_propio", lambda: ["Firefox"])
    monkeypatch.setattr(PV, "_pista", lambda: "")
    monkeypatch.setattr(MAS, "vram_usada_mb", lambda: 1000)
    monkeypatch.setattr(MAS, "soltar_modelo", lambda *a, **k: None)
    lista = G.frases()
    for i in range(len(lista)):
        PV.guardar_wav(G.ruta(i), np.ones(PV.FRECUENCIA, dtype="float32") * (0.1 + i / 10000))
    contador = {"i": 0}

    def cargar(calculo):
        def transcribir(audio, pista=None, palabras=None):
            i = contador["i"] % len(lista)
            contador["i"] += 1
            return lista[i][0]
        return transcribir, lambda: None

    class Http:
        def get(self, url, timeout=None):
            return Respuesta({"models": [{"name": "qwen2.5:3b"}]})

        def post(self, url, json=None, timeout=None):
            return Respuesta({"message": {"content": '{"texto": "Pausa"}'}})
    dicho = []
    assert G.principal(["medir", "--modelos=qwen2.5:3b"], salida=dicho.append, cargar=cargar, http=Http()) == 0
    todo = "\n".join(dicho)
    assert "PRUEBA GRANDE" in todo and "qwen2.5:3b" in todo and "solo si no es orden" in todo
    assert (tmp_path / "pv" / "informe-grande.txt").exists()


def test_fallos_de_whisper_solo_dicen_si_la_orden_se_entiende_igual():
    lista = [("Reanuda la música", True), ("Pausa", True), ("Cuéntame un chiste corto", False), ("Sube el volumen", True)]
    r = G.fallos_whisper(lista, ["Renuda la música", "Pausa", "Cuéntame un chiste", "sube el volumen."])
    assert [(f, ok) for f, _, d, ok in r if d] == [("Reanuda la música", False)]
    assert [f for f, _, d, _ in r if not d] == ["Cuéntame un chiste corto"]


def test_un_programa_mal_oido_cuenta_si_lina_lo_llevaria_al_mismo(monkeypatch):
    monkeypatch.setattr(G.C, "buscar_app", lambda n, apps=None: [(80, {"nombre": "Kate"})] if "cate" in n.lower() or "kate" in n.lower() else [])
    assert G.entiende_igual("Abre Kate", "Abre el Cate.")
    assert not G.entiende_igual("Abre Kate", "Abre fær, fóks.")
