# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 14: Bluetooth por tipo de dispositivo, con batería y como orden directa; y diagnóstico de juegos (solo mira)."""
import pytest

from lina.modulos import juegoconf as JC
from lina.modulos import sistema as S
from lina.nucleo import directas as D
from lina.nucleo import memoria as MEM

DISP = {"AA:AA": ("Sony WH-1000XM4", "audio-headset", 85, True), "BB:BB": ("JBL Flip", "audio-speakers", None, False),
        "CC:CC": ("Xbox Wireless Controller", "input-gaming", 40, True), "DD:DD": ("Anker Soundcore", "audio-headset", None, False)}


def falso_bluetoothctl(disp, orden):
    def ej(argv, timeout=8):
        if argv[:2] == ["bluetoothctl", "devices"]:
            if argv[2:] == ["Connected"]:
                return 0, "\n".join(f"Device {m} {d[0]}" for m, d in disp.items() if d[3])
            return 0, "\n".join(f"Device {m} {d[0]}" for m, d in disp.items())
        if argv[:2] == ["bluetoothctl", "info"]:
            d = disp[argv[2]]
            return 0, f"Device {argv[2]} ({d[0]})\n\tIcon: {d[1]}\n\tConnected: {'yes' if d[3] else 'no'}\n" + (f"\tBattery Percentage: 0x{d[2]:02x} ({d[2]})\n" if d[2] is not None else "")
        if argv[:2] == ["bluetoothctl", "show"]:
            return 0, "Controller 00:11\n\tName: pc\n\tPowered: yes\n\tPairable: yes"
        orden.append(argv)
        return 0, ""
    return ej


@pytest.fixture
def bt(monkeypatch, tmp_path):
    orden = []
    monkeypatch.setattr(S, "ej", falso_bluetoothctl(DISP, orden))
    monkeypatch.setattr(MEM, "ARCHIVO", tmp_path / "memoria.json")
    return orden


def test_estado_con_bateria_de_lo_conectado(bt):
    texto = S.planificar_red({"accion": "bluetooth_estado"})["texto"]
    assert "Sony WH-1000XM4 (AA:AA) CONECTADO · batería 85 %" in texto
    assert "JBL Flip (BB:BB) no conectado" in texto and "batería" not in texto.split("JBL")[1].split("\n")[0]


def test_por_tipo_aunque_no_se_llamen_asi(bt):
    p = S.planificar_red({"accion": "bluetooth_desconectar", "objetivo": "auriculares"})
    assert p["comando"] == "bluetoothctl disconnect AA:AA"                     # hay dos auriculares, pero solo uno conectado
    p = S.planificar_red({"accion": "bluetooth_conectar", "objetivo": "el mando"})
    assert p["comando"] == "bluetoothctl connect CC:CC"
    p = S.planificar_red({"accion": "bluetooth_conectar", "objetivo": "altavoz"})
    assert p["comando"] == "bluetoothctl connect BB:BB"


def test_varios_del_mismo_tipo_sin_pista_no_adivina(bt):
    p = S.planificar_red({"accion": "bluetooth_conectar", "objetivo": "mis auriculares"})
    assert "error" in p and "Sony" in p["error"] and "Anker" in p["error"]


def test_varios_del_mismo_tipo_con_recuerdo_usa_el_tuyo(bt):
    MEM.recordar("mis auriculares preferidos son los Anker")
    p = S.planificar_red({"accion": "bluetooth_conectar", "objetivo": "auriculares"})
    assert p["comando"] == "bluetoothctl connect DD:DD"


def test_por_nombre_sigue_funcionando(bt):
    assert S.planificar_red({"accion": "bluetooth_conectar", "objetivo": "jbl"})["comando"] == "bluetoothctl connect BB:BB"


@pytest.mark.parametrize("frase,esperado", [
    ("conecta mis auriculares", ("bluetooth", {"accion": "bluetooth_conectar", "objetivo": "auriculares"})),
    ("desconecta el mando", ("bluetooth", {"accion": "bluetooth_desconectar", "objetivo": "mando"})),
    ("enciende el bluetooth", ("bluetooth", {"accion": "bluetooth_encender"})),
    ("conecta el bluetooth", ("bluetooth", {"accion": "bluetooth_encender"})),
    ("conecta los auriculares por favor", ("bluetooth", {"accion": "bluetooth_conectar", "objetivo": "auriculares"})),
])
def test_ordenes_directas_de_bluetooth(frase, esperado):
    assert D.entender(frase) == esperado


@pytest.mark.parametrize("frase", ["conéctate al wifi", "conecta con el servidor", "conecta la base de datos", "desconecta el bluetooth", "conecta mis auriculares y pon música",
                                   "no conectes los auriculares", "conecta el ordenador a la red"])
def test_no_son_ordenes_directas_de_bluetooth(frase):
    orden = D.entender(frase)
    assert orden is None or orden[0] != "bluetooth"


def test_en_ingles():
    from lina.nucleo import idioma as IDI
    IDI.fijar("en") if hasattr(IDI, "fijar") else None
    try:
        if IDI.actual() == "en":
            assert D.entender("connect my headphones") == ("bluetooth", {"accion": "bluetooth_conectar", "objetivo": "headphones"})
    finally:
        IDI.fijar("es") if hasattr(IDI, "fijar") else None


# ---- diagnóstico de juegos
def falso_juegos(monkeypatch, tmp_path, programas, salidas, capas=()):
    monkeypatch.setattr(JC.shutil, "which", lambda n: f"/usr/bin/{n}" if n in programas else None)
    monkeypatch.setattr(JC, "_ej", lambda argv, timeout=8: salidas.get(argv[0], (1, "")))
    monkeypatch.setattr(JC, "_capas_vulkan", lambda: list(capas))
    monkeypatch.setattr(JC, "RUTA_MANGOHUD", tmp_path / "MangoHud.conf")
    monkeypatch.setattr(JC.Path, "home", staticmethod(lambda: tmp_path))


def test_diagnostico_todo_bien(monkeypatch, tmp_path):
    (tmp_path / "MangoHud.conf").write_text("fps\ngpu_stats\n")
    falso_juegos(monkeypatch, tmp_path, {"gamemoderun", "gamemoded", "vulkaninfo", "mangohud"},
                 {"gamemoded": (0, "gamemode self-test was successful"), "vulkaninfo": (0, "deviceName = AMD Radeon RX 7800 XT\napiVersion = 1.3.274")},
                 capas=["VkLayer_MESA_overlay.json", "lsfg_vk_layer.json"])
    t = JC.diagnostico()
    assert "✔ GameMode" in t and "✔ Vulkan: AMD Radeon RX 7800 XT (API 1.3.274)" in t and "✔ MangoHud" in t and "2 opción" in t and "✔ LSFG" in t
    assert "✘" not in t and "no he cambiado nada" in t


def test_diagnostico_con_fallos_los_senala(monkeypatch, tmp_path):
    falso_juegos(monkeypatch, tmp_path, {"vulkaninfo"}, {"vulkaninfo": (0, "deviceName = llvmpipe (LLVM 17)\napiVersion = 1.3")})
    t = JC.diagnostico()
    assert "✘ GameMode: no está instalado" in t and "✘ Vulkan: solo veo renderizado por software" in t and "✘ MangoHud: no está instalado" in t and "· LSFG" in t


def test_diagnostico_sin_vulkaninfo(monkeypatch, tmp_path):
    falso_juegos(monkeypatch, tmp_path, set(), {})
    assert "falta «vulkaninfo»" in JC.diagnostico()


def test_gamemode_instalado_con_prueba_que_falla(monkeypatch, tmp_path):
    falso_juegos(monkeypatch, tmp_path, {"gamemoded"}, {"gamemoded": (1, "gamemode self-test failed: no daemon")})
    assert "✘ GameMode: instalado pero la prueba falla" in JC.diagnostico()
