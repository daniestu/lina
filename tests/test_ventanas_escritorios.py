# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
from lina.escritorio import sesion as SES
from lina.modulos import sistema as S

WIN = {"41943042": ("Terminal", "xfce4-terminal", 200), "52428810": ("Mozilla Firefox", "Navigator", 100)}


def x11(monkeypatch, escritorio="XFCE", programas=("xdotool",)):
    visto = []

    def ej(argv, timeout=8):
        visto.append(list(argv))
        if argv[0] == "xdotool":
            if argv[1] == "search":
                if argv[-1] == "%@":
                    idx = {"getwindowname": 0, "getwindowclassname": 1, "getwindowpid": 2}[argv[-2]]
                    return 0, "\n".join(str(v[idx]) for v in WIN.values())
                return 0, "\n".join(WIN)
            if argv[1] == "getactivewindow":
                return 0, "52428810"
            if argv[1] == "getwindowgeometry":
                return 0, "Position: 0,0\nGeometry: 800x600"
            return 0, ""
        return None, ""
    monkeypatch.setattr(S, "EJ", ej)
    s = SES.Sesion({"XDG_CURRENT_DESKTOP": escritorio, "XDG_SESSION_TYPE": "x11"}, which=lambda p: "/usr/bin/" + p if p in programas else None)
    monkeypatch.setattr(SES, "actual", lambda: s)
    return visto


def test_x11_lista_ventanas_con_xdotool(monkeypatch):
    visto = x11(monkeypatch)
    p = S.planificar("ventanas", {"accion": "listar"})
    assert "52428810" in p["texto"] and "Mozilla Firefox" in p["texto"] and "← activa" in p["texto"]
    assert all(v[0] == "xdotool" for v in visto)


def test_x11_cierra_con_xdotool(monkeypatch):
    x11(monkeypatch)
    p = S.planificar("ventanas", {"accion": "cerrar", "ventana": "terminal"})
    assert p.get("comando") == f"xdotool windowclose {S._q('41943042')}", p


def test_x11_no_promete_lo_que_solo_hace_kde(monkeypatch):
    x11(monkeypatch)
    for accion in ("maximizar", "mosaico", "mostrar_escritorio", "cambiar_escritorio", "mover_a_monitor"):
        p = S.planificar("ventanas", {"accion": accion, "ventana": "firefox", "valor": "izquierda"})
        assert "error" in p and "solo sé hacerlo en KDE" in p["error"], accion


def test_sin_xdotool_dice_que_falta(monkeypatch):
    x11(monkeypatch, programas=())
    p = S.planificar("ventanas", {"accion": "listar"})
    assert "error" in p and "xdotool" in p["error"]


def test_sway_dice_que_no_sabe_manejar_ventanas(monkeypatch):
    x11(monkeypatch, escritorio="sway", programas=("swaymsg",))
    p = S.planificar("ventanas", {"accion": "listar"})
    assert "error" in p and "sway" in p["error"]
