# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 15: GPU de solo lectura (NVIDIA, AMD, Intel simuladas), LACT con confirmación, registro con límites, y que sin GPU la herramienta ni se ofrece."""
import json
import time

import pytest

from lina.modulos import gpu as G
from lina.nucleo import declaraciones as DEC
from lina.nucleo import grupos as GR
from lina.nucleo import herramientas as H


def escribir(base, ruta, texto):
    p = base / ruta
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(texto))


def amd(base, potencia_uw=180_000_000, cap_uw=200_000_000, temp=70_000):
    d = "class/drm/card0/device"
    escribir(base, f"{d}/vendor", "0x1002")
    escribir(base, f"{d}/gpu_busy_percent", 97)
    escribir(base, f"{d}/mem_info_vram_used", 8_589_934_592)
    escribir(base, f"{d}/mem_info_vram_total", 17_179_869_184)
    escribir(base, f"{d}/hwmon/hwmon3/temp1_input", temp - 8000)
    escribir(base, f"{d}/hwmon/hwmon3/temp2_input", temp)
    escribir(base, f"{d}/hwmon/hwmon3/temp2_crit", 110_000)
    escribir(base, f"{d}/hwmon/hwmon3/power1_average", potencia_uw)
    escribir(base, f"{d}/hwmon/hwmon3/power1_cap", cap_uw)
    escribir(base, f"{d}/hwmon/hwmon3/freq1_input", 2_450_000_000)
    escribir(base, f"{d}/pp_dpm_mclk", "0: 96Mhz\n1: 1249Mhz *\n")
    (base / "class/drm/card0-DP-1").mkdir(parents=True, exist_ok=True)           # una salida de vídeo: no es una tarjeta


@pytest.fixture
def sin_nvidia(monkeypatch):
    monkeypatch.setattr(G.shutil, "which", lambda n: None)


def test_sin_gpu_no_se_ofrece(tmp_path, sin_nvidia, monkeypatch):
    assert G.detectar(tmp_path) == [] and not G.hay(tmp_path)
    monkeypatch.setattr(G, "hay", lambda raiz=None: False)
    nombres = {d["name"] for d in GR.herramientas(DEC.DECLARACIONES if hasattr(DEC, "DECLARACIONES") else [], ["sistema"])}
    assert "gpu" not in nombres


def test_con_gpu_si_se_ofrece(monkeypatch):
    decl = [{"name": "gpu"}, {"name": "ventanas"}]
    monkeypatch.setattr(G, "hay", lambda raiz=None: True)
    assert "gpu" in {d["name"] for d in GR.herramientas(decl, ["sistema"])}
    monkeypatch.setattr(G, "hay", lambda raiz=None: False)
    assert "gpu" not in {d["name"] for d in GR.herramientas(decl, ["sistema"])}
    lista = []
    GR.cargar("sistema", decl, lista, set())
    assert [d["name"] for d in lista] == ["ventanas"]


def test_amd_lee_sysfs(tmp_path, sin_nvidia):
    amd(tmp_path)
    (g,) = G.detectar(tmp_path)
    assert g["fabricante"] == "amd"
    m = G.leer(g)
    assert m["uso_pct"] == 97 and m["temp_c"] == 70 and round(m["vram_usada_mb"]) == 8590 and m["potencia_w"] == 180 and m["limite_w"] == 200
    assert m["frec_gpu_mhz"] == 2450 and m["frec_mem_mhz"] == 1249 and m["limitacion"].startswith("ninguna")
    assert "Uso: 97 %" in G.describir(g, m)


def test_amd_deduce_el_motivo_de_la_limitacion(tmp_path, sin_nvidia):
    amd(tmp_path, potencia_uw=199_000_000)
    assert "potencia" in G.leer(G.detectar(tmp_path)[0])["limitacion"]
    amd(tmp_path, temp=109_000)
    assert "temperatura" in G.leer(G.detectar(tmp_path)[0])["limitacion"]


def test_intel(tmp_path, sin_nvidia):
    d = "class/drm/card1"
    escribir(tmp_path, f"{d}/device/vendor", "0x8086")
    escribir(tmp_path, f"{d}/gt_act_freq_mhz", 1100)
    escribir(tmp_path, f"{d}/gt_max_freq_mhz", 1300)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_status", 1)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_pl1", 1)
    escribir(tmp_path, f"{d}/gt/gt0/throttle_reason_thermal", 0)
    m = G.leer(G.detectar(tmp_path)[0])
    assert m["frec_gpu_mhz"] == 1100 and m["limitacion"] == "pl1"


def falso_nvidia(monkeypatch, mascara="0x0000000000000004"):
    monkeypatch.setattr(G.shutil, "which", lambda n: "/usr/bin/" + n if n in ("nvidia-smi", "lact") else None)

    def ej(argv, timeout=8):
        if argv[0] == "nvidia-smi" and "--query-gpu=index,name" in argv:
            return 0, "0, NVIDIA GeForce RTX 4070"
        if argv[0] == "nvidia-smi":
            if "clocks_event_reasons.active" not in " ".join(argv):
                return 2, "Field is not a valid field to query."           # un controlador antiguo no conoce el nombre nuevo
            return 0, f"61, 98, 7000, 12282, 195.50, 200.00, 2745, 10501, {mascara}"
        if argv[:4] == ["lact", "cli", "profile", "list"]:
            return 0, "Gaming\nSilencioso\nPerformance"
        if argv[:4] == ["lact", "cli", "profile", "get"]:
            return 0, "Gaming"
        return 1, ""
    monkeypatch.setattr(G, "_ej", ej)


def test_nvidia_y_motivo(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    (g,) = G.detectar(tmp_path)
    m = G.leer(g)
    assert g["fabricante"] == "nvidia" and m["temp_c"] == 61 and m["potencia_w"] == 195.5 and m["limite_w"] == 200 and m["limitacion"] == "límite de potencia (software)"


def test_planificar_estado_y_lact(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    assert "RTX 4070" in G.planificar({"accion": "estado"})["texto"]
    t = G.planificar({"accion": "lact"})["texto"]
    assert "«Gaming»" in t and "Performance" in t and "confirmación" in t


def test_cambiar_de_perfil_es_un_comando_que_pide_confirmacion(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    plan = G.planificar({"accion": "perfil", "objetivo": "perform"})
    assert plan["comando"] == "lact cli profile set Performance"
    assert H.clasificar(plan["comando"])[0] == "critico"
    assert "error" in G.planificar({"accion": "perfil", "objetivo": "inexistente"})
    assert H.clasificar("lact cli profile list")[0] == "lectura" and H.clasificar("nvidia-smi -pl 100")[0] == "critico"


def test_lact_no_instalado(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G.shutil, "which", lambda n: "/usr/bin/nvidia-smi" if n == "nvidia-smi" else None)
    monkeypatch.setattr(G, "SYS", tmp_path)
    assert "no está instalado" in G.planificar({"accion": "lact"})["error"]


def test_registro_escribe_csv_y_respeta_limites(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    monkeypatch.setattr(G, "ARCHIVO_REGISTRO", tmp_path / "reg.json")
    ruta = tmp_path / "g" / "m.csv"
    t = [0.0]
    G.registrar(ruta, 2, 10, dormir=lambda s: t.__setitem__(0, t[0] + s), reloj=lambda: t[0])
    filas = ruta.read_text().splitlines()
    assert filas[0].startswith("hora,temp_c,uso_pct") and len(filas) == 1 + 5 and "limite de potencia" not in filas[1] and "195.5" in filas[1]
    ruta2 = tmp_path / "g" / "tope.csv"
    t[0] = 0.0
    G.registrar(ruta2, 1, 1000, tam_max=300, dormir=lambda s: t.__setitem__(0, t[0] + s), reloj=lambda: t[0])
    assert len(ruta2.read_text().splitlines()) < 10                         # el tope de tamaño lo detuvo mucho antes de los 1000 s


def test_limites_de_la_peticion(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "ARCHIVO_REGISTRO", tmp_path / "reg.json")
    assert "intervalo" in G.iniciar_registro(0, 5)["error"] and "intervalo" in G.iniciar_registro(120, 5)["error"]
    assert "como mucho" in G.iniciar_registro(2, 600)["error"] and "como mucho" in G.iniciar_registro(2, 0)["error"]


def test_registro_se_ve_y_se_cancela(monkeypatch, tmp_path):
    falso_nvidia(monkeypatch)
    monkeypatch.setattr(G, "SYS", tmp_path)
    monkeypatch.setattr(G, "ARCHIVO_REGISTRO", tmp_path / "reg.json")
    monkeypatch.setattr(G, "CARPETA_REGISTROS", tmp_path / "gpu")
    lanzados = []

    class P:
        pid = 4242
    monkeypatch.setattr(G.subprocess, "Popen", lambda cmd, **k: lanzados.append(cmd) or P())
    r = G.planificar({"accion": "registro_iniciar", "intervalo_s": 2, "minutos": 15})
    assert "Registro en marcha" in r["texto"] and lanzados[0][1:4] == ["-m", "lina.modulos.gpu", "--registrar"] and lanzados[0][-2:] == ["2", "900"]
    # el proceso «existe» y es de Lina → se ve; si el pid lo ocupa otro programa, no se toca
    monkeypatch.setattr(G.os, "kill", lambda pid, s: None)
    monkeypatch.setattr(G, "_leer", lambda ruta, por_defecto=None: "python -m lina.modulos.gpu --registrar" if "cmdline" in str(ruta) else por_defecto)
    assert "en marcha (pid 4242)" in G.planificar({"accion": "registro_estado"})["texto"]
    assert "Ya hay un registro" in G.iniciar_registro(2, 5)["error"]
    muertos = []
    monkeypatch.setattr(G.os, "killpg", lambda pid, s: muertos.append(pid))
    assert "Registro parado" in G.planificar({"accion": "registro_parar"})["texto"] and muertos == [4242]
    assert not (tmp_path / "reg.json").exists()
    monkeypatch.setattr(G, "_leer", lambda ruta, por_defecto=None: "firefox" if "cmdline" in str(ruta) else por_defecto)
    (tmp_path / "reg.json").write_text(json.dumps({"pid": 99, "csv": "x", "inicio": time.time(), "intervalo": 2, "minutos": 5}))
    assert "No había ningún registro" in G.planificar({"accion": "registro_parar"})["texto"]
