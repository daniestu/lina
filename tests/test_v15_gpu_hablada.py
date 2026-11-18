# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V15: lo que se dice en voz alta de la gráfica. El código hace una frase corta con los mismos datos (sin IA): si va bien, temperatura, uso y memoria de
vídeo; si algo la limita, solo eso y su dato. Las frecuencias y los vatios quedan en el detalle, para quien los pida. Con datos simulados de NVIDIA, AMD e
Intel (los de test_gpu.py); sin tarjeta, red ni IA."""
import re

from lina.modulos import gpu as G

from test_gpu import amd, escribir, falso_nvidia

TARJETA = {"nombre": "Radeon de prueba"}
SIN_UNIDADES_TECNICAS = re.compile(r"MHz|vatios|\bW\b", re.I)


def test_si_va_bien_dice_temperatura_uso_y_memoria_sin_frecuencias():
    m = {"temp_c": 45.0, "uso_pct": 30.0, "vram_usada_mb": 3174.4, "vram_total_mb": 16384.0, "potencia_w": 80.0, "limite_w": 300.0,
         "frec_gpu_mhz": 2400.0, "frec_mem_mhz": 10000.0, "limitacion": "ninguna"}
    f = G.frase_hablada(TARJETA, m)
    assert f == "La gráfica va bien: 45 grados, 30 % de uso y 3,1 de 16,0 GB de memoria."
    assert not SIN_UNIDADES_TECNICAS.search(f)


def test_si_le_faltan_datos_dice_solo_los_que_hay():
    assert G.frase_hablada(TARJETA, {"temp_c": 52.0, "limitacion": "ninguna detectada"}) == "La gráfica va bien: 52 grados."
    assert G.frase_hablada(TARJETA, {"uso_pct": 5.0, "vram_usada_mb": 1024.0, "limitacion": "ninguna"}) == "La gráfica va bien: 5 % de uso y 1,0 GB de memoria en uso."
    sin_nada = G.frase_hablada(TARJETA, {"frec_gpu_mhz": 1100.0, "limitacion": "no se puede saber en esta GPU"})
    assert "no informa de su temperatura" in sin_nada and not SIN_UNIDADES_TECNICAS.search(sin_nada)
    assert G.frase_hablada(TARJETA, {"error": "nvidia-smi no ha contestado"}) is None


def test_amd_bien_y_amd_limitada(tmp_path, monkeypatch):
    monkeypatch.setattr(G.shutil, "which", lambda n: None)
    amd(tmp_path)
    (g,) = G.detectar(tmp_path)
    assert G.frase_hablada(g, G.leer(g)) == "La gráfica va bien: 70 grados, 97 % de uso y 8,0 de 16,0 GB de memoria."
    amd(tmp_path, temp=109_000)
    assert G.frase_hablada(g, G.leer(g)) == "La gráfica está frenando su rendimiento por temperatura: está a 109 grados."
    amd(tmp_path, potencia_uw=199_000_000)
    assert G.frase_hablada(g, G.leer(g)) == "La gráfica está frenando su rendimiento por límite de potencia: consume 199 de 200 vatios."


def test_nvidia_limitada_por_potencia(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    (g,) = G.detectar(tmp_path)
    assert G.frase_hablada(g, G.leer(g)) == "La gráfica está frenando su rendimiento por límite de potencia: consume 196 de 200 vatios."


def test_nvidia_bien(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch, mascara="0x0000000000000001")                       # 0x1 = inactiva: no es una limitación
    monkeypatch.setattr(G, "SYS", tmp_path)
    (g,) = G.detectar(tmp_path)
    assert G.frase_hablada(g, G.leer(g)) == "La gráfica va bien: 61 grados, 98 % de uso y 6,8 de 12,0 GB de memoria."


def test_intel_con_sus_nombres_de_motivo(tmp_path, monkeypatch):
    monkeypatch.setattr(G.shutil, "which", lambda n: None)
    d = "class/drm/card1"
    escribir(tmp_path, f"{d}/device/vendor", "0x8086")
    escribir(tmp_path, f"{d}/gt_act_freq_mhz", 1100)
    escribir(tmp_path, f"{d}/gt_max_freq_mhz", 1300)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_status", 1)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_pl1", 1)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_thermal", 1)
    (g,) = G.detectar(tmp_path)
    f = G.frase_hablada(g, G.leer(g))
    assert f == "La gráfica está frenando su rendimiento por límite de potencia y temperatura." and "pl1" not in f


def test_la_herramienta_da_la_frase_primero_y_el_detalle_aparte(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch, mascara="0x0000000000000001")
    monkeypatch.setattr(G, "SYS", tmp_path)
    texto = G.planificar({"accion": "estado"})["texto"]
    dicho, detalle = texto.split("\n\n", 1)
    assert dicho.startswith("PARA DECIR EN VOZ ALTA") and "61 grados" in dicho and not SIN_UNIDADES_TECNICAS.search(dicho.split(": ", 1)[1])
    assert "Frecuencia" in detalle and "MHz" in detalle and "RTX 4070" in detalle


def test_con_dos_tarjetas_cada_frase_lleva_su_nombre():
    m = {"temp_c": 40.0, "limitacion": "ninguna"}
    assert G.frase_hablada({"nombre": "Intel UHD"}, m, con_nombre=True) == "La Intel UHD va bien: 40 grados."
