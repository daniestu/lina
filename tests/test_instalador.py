# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from lina.escritorio import atajo as A
from lina.nucleo import instalador as I
from lina.nucleo import modelos as MOD
from lina.voz import voces as V


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def falso(contenidos):
    def abrir(url, tiempo):
        for fin, datos in contenidos.items():
            if url.endswith(fin):
                return Respuesta(datos)
        raise OSError("sin red")
    return abrir


def ok(*a, **k):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def ctx_en(tmp_path, **k):
    (tmp_path / "bin").mkdir(exist_ok=True)
    lina = tmp_path / "bin" / "lina"
    lina.write_text("#!/bin/sh\n")
    salida = []
    c = I.Contexto(home=tmp_path, ejecutable=lina, salida=salida.append, manifiesto=I.Manifiesto(tmp_path / "m.json"),
                   ejecutar=k.pop("ejecutar", ok), which=k.pop("which", lambda n: None), terminal=False, **k)
    c.config = tmp_path / "config"
    c.texto = salida
    return c


def test_simular_no_toca_nada(tmp_path):
    c = ctx_en(tmp_path, simular=True)
    antes = sorted(p for p in tmp_path.rglob("*"))
    assert I.paso_enlace(c) and I.paso_servicio(c) and I.paso_modelos(c)
    assert sorted(p for p in tmp_path.rglob("*")) == antes


def test_enlace_y_manifiesto(tmp_path):
    c = ctx_en(tmp_path)
    assert I.paso_enlace(c)
    enlace = tmp_path / ".local" / "bin" / "lina"
    assert enlace.is_symlink() and enlace.resolve() == c.ejecutable.resolve()
    assert c.manifiesto.de("enlace")["ruta"] == str(enlace)


def test_enlace_no_pisa_un_archivo_ajeno(tmp_path):
    c = ctx_en(tmp_path)
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "lina").write_text("mío")
    assert not I.paso_enlace(c)
    assert (tmp_path / ".local" / "bin" / "lina").read_text() == "mío"


def test_sin_systemd_usa_autostart(tmp_path, monkeypatch):
    monkeypatch.setattr(I.PL, "detectar_init", lambda: "openrc")
    c = ctx_en(tmp_path)
    assert I.paso_servicio(c)
    arranque = tmp_path / "config" / "autostart" / "lina.desktop"
    assert arranque.exists() and f"Exec={c.ejecutable}" in arranque.read_text()
    assert c.manifiesto.de("autostart")


def test_servicio_systemd_y_desinstalacion(tmp_path, monkeypatch):
    monkeypatch.setattr(I.PL, "detectar_init", lambda: "systemd")
    ordenes = []
    c = ctx_en(tmp_path, which=lambda n: "/bin/" + n, ejecutar=lambda o, **k: (ordenes.append(o), ok())[1])
    assert I.paso_servicio(c)
    unidad = tmp_path / "config" / "systemd" / "user" / "lina.service"
    assert "ExecStart=" in unidad.read_text()
    assert ["systemctl", "--user", "enable", "--now", "lina.service"] in ordenes
    assert I.paso_enlace(c)
    assert I.desinstalar(["--si"], c) == 0
    assert not unidad.exists() and not (tmp_path / ".local" / "bin" / "lina").exists()
    assert ["systemctl", "--user", "disable", "--now", "lina.service"] in ordenes


def test_desinstalar_todo_exige_la_frase(tmp_path):
    c = ctx_en(tmp_path, entrada=lambda _: "sí")
    c.terminal = True
    c.manifiesto.anotar("enlace", ruta=str(tmp_path / "x"))
    assert I.desinstalar(["--todo"], c) == 1
    assert any("No se ha quitado nada" in t for t in c.texto)


def test_desinstalar_sin_manifiesto(tmp_path):
    c = ctx_en(tmp_path)
    assert I.desinstalar(["--si"], c) == 0
    assert any("No encuentro nada" in t for t in c.texto)


def test_no_borra_un_enlace_que_no_es_enlace(tmp_path):
    f = tmp_path / "lina"
    f.write_text("x")
    assert "no es un enlace" in I._borrar(f, solo_enlace=True) and f.exists()


def test_preguntar_respeta_si_y_la_falta_de_terminal(tmp_path):
    assert ctx_en(tmp_path, si=True).preguntar("¿?", por_defecto=False)
    assert not ctx_en(tmp_path).preguntar("¿?", por_defecto=False)


# ---------------------------------------------------------------- atajo
def test_escritorio_detectado():
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "KDE"}) == "kde"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}) == "gnome"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "sway"}) == "sway"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "i3"}) == "otro"


def test_atajo_kde_se_registra_y_se_quita(tmp_path):
    ordenes = []
    ej = lambda o, **k: (ordenes.append(o), ok())[1]
    hecho, msg, nota = A.registrar("kde", "Meta+Space", "/u/lina", tmp_path, ejecutar=ej, which=lambda n: "/bin/kwriteconfig6" if n == "kwriteconfig6" else None)
    assert hecho and nota["tecla"] == "Meta+Space"
    desktop = Path(nota["archivo"])
    assert "Exec=/u/lina pulsar" in desktop.read_text()
    assert ordenes[0][-2:] == ["_launch", "Meta+Space"]
    assert ["systemctl", "--user", "restart", "plasma-kglobalaccel.service"] in ordenes and "activado" in msg       # KDE lo coge sin cerrar sesión
    A.quitar(nota, tmp_path, ejecutar=ej, which=lambda n: "/bin/kwriteconfig6")
    assert not desktop.exists()


def test_atajo_kde_sin_herramienta_no_deja_basura(tmp_path):
    hecho, msg, nota = A.registrar("kde", "Meta+Space", "/u/lina", tmp_path, which=lambda n: None)
    assert not hecho and not list(tmp_path.rglob("*.desktop"))


def test_atajo_escritorio_desconocido_dice_que_hacer(tmp_path):
    hecho, msg, nota = A.registrar("otro", "x", "/u/lina", tmp_path)
    assert not hecho and "/u/lina pulsar" in msg


# ---------------------------------------------------------------- modelos y voces
def test_modelos_simulacion_no_crea_ajustes(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    ok_, problemas = MOD.asegurar_todo(log=lambda m: None, simular=True)
    assert ok_ and not list(tmp_path.rglob("*"))


def test_huella_de_voz_detecta_cambios(tmp_path):
    abrir = falso({".onnx.json": b"{}", ".onnx": b"modelo"})
    assert V.asegurar("es_MX-claude-high", tmp_path, lambda m: None, abrir)
    assert V.verificar("es_MX-claude-high", tmp_path)[0] is True
    onnx = next(p for p in tmp_path.iterdir() if p.name.endswith(".onnx"))
    onnx.write_bytes(b"otra cosa")
    estado, detalle = V.verificar("es_MX-claude-high", tmp_path)
    assert estado is False and "corrupto" in detalle


def test_voz_no_instalada_no_se_verifica(tmp_path):
    assert V.verificar("es_MX-claude-high", tmp_path)[0] is False



# ---------------------------------------------------------------- atajo en más escritorios
def test_escritorio_del_atajo_distingue_cinnamon_xfce_y_compositores():
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "X-Cinnamon"}) == "cinnamon"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "XFCE"}) == "xfce"
    assert A.escritorio({"SWAYSOCK": "x"}) == "sway"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "Budgie:GNOME"}) == "gnome"
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "i3"}) == "otro"


def test_atajo_cinnamon_se_registra_y_se_quita(tmp_path):
    ordenes = []

    def ej(o, **k):
        ordenes.append(o)
        return SimpleNamespace(returncode=0, stdout="['custom0']" if o[1:2] == ["get"] else "", stderr="")
    hecho, msg, nota = A.registrar("cinnamon", "<Control><Alt>space", "/u/lina", tmp_path, ejecutar=ej, which=lambda n: "/bin/" + n)
    assert hecho and nota["escritorio"] == "cinnamon"
    assert ["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list", "['custom0', 'lina']"] in ordenes
    assert any(o[-2:] == ["binding", "['<Control><Alt>space']"] for o in ordenes)
    ordenes.clear()
    assert "Cinnamon quitado" in A.quitar(nota, tmp_path, ejecutar=ej, which=lambda n: "/bin/" + n)
    assert ["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list", "['custom0']"] in ordenes


def test_atajo_xfce_se_registra_y_se_quita(tmp_path):
    ordenes = []
    ej = lambda o, **k: (ordenes.append(o), ok())[1]
    hecho, msg, nota = A.registrar("xfce", "<Primary><Alt>space", "/u/lina", tmp_path, ejecutar=ej, which=lambda n: "/bin/" + n)
    assert hecho and ordenes[0][:4] == ["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p"]
    assert ordenes[0][4] == "/commands/custom/<Primary><Alt>space" and ordenes[0][-1] == "/u/lina pulsar"
    assert "XFCE quitado" in A.quitar(nota, tmp_path, ejecutar=ej, which=lambda n: "/bin/" + n) and ordenes[-1][-3:-1] == ["-r", "-p"]


def test_atajo_no_acepta_propiedades_de_otro_sitio(tmp_path):
    assert "no reconocida" in A.quitar({"escritorio": "xfce", "propiedad": "/otra/cosa"}, tmp_path, which=lambda n: "/bin/" + n)


def test_sway_e_hyprland_dan_la_linea_exacta(tmp_path):
    for escr, trozo in (("sway", "bindsym"), ("hyprland", "bind = SUPER")):
        hecho, msg, nota = A.registrar(escr, "x", "/u/lina", tmp_path)
        assert not hecho and trozo in msg and "/u/lina pulsar" in msg
    assert not list(tmp_path.rglob("*"))                                  # no toca la configuración de nadie


def test_ya_hay_atajo_en_xfce_y_cinnamon(tmp_path):
    xf = lambda o, **k: SimpleNamespace(returncode=0, stdout="/commands/custom/<Primary><Alt>space   /u/lina pulsar\n", stderr="")
    assert A.ya_hay_atajo("xfce", tmp_path, xf, lambda n: "/bin/" + n)
    cn = lambda o, **k: SimpleNamespace(returncode=0, stdout="['custom0', 'lina']", stderr="")
    assert A.ya_hay_atajo("cinnamon", tmp_path, cn, lambda n: "/bin/" + n)
    assert not A.ya_hay_atajo("cinnamon", tmp_path, lambda o, **k: SimpleNamespace(returncode=0, stdout="['custom0']", stderr=""), lambda n: "/bin/" + n)


def test_en_sway_el_servicio_avisa_de_que_puede_no_arrancar(tmp_path, monkeypatch):
    monkeypatch.setattr(I.PL, "detectar_init", lambda: "systemd")
    monkeypatch.setenv("SWAYSOCK", "/run/sway.sock")
    c = ctx_en(tmp_path, which=lambda n: "/bin/" + n)
    assert I.paso_servicio(c)
    assert any("graphical-session.target" in t and "exec " in t for t in c.texto)


def test_en_kde_no_hay_ese_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(I.PL, "detectar_init", lambda: "systemd")
    monkeypatch.delenv("SWAYSOCK", raising=False)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    c = ctx_en(tmp_path, which=lambda n: "/bin/" + n)
    assert I.paso_servicio(c) and not any("graphical-session.target" in t for t in c.texto)


@pytest.mark.parametrize("shell, donde, contiene", [
    ("/usr/bin/fish", ".config/fish/conf.d/lina.fish", "fish_add_path"), ("/bin/bash", ".bashrc", "export PATH"), ("/usr/bin/zsh", ".zshrc", "export PATH"),
])
def test_si_el_bin_no_esta_en_el_path_se_añade_al_shell_y_se_deshace(tmp_path, monkeypatch, shell, donde, contiene):
    monkeypatch.setenv("SHELL", shell)
    monkeypatch.setenv("PATH", "/usr/bin")
    c = ctx_en(tmp_path)
    c.config = tmp_path / ".config"
    (tmp_path / ".bashrc").write_text("alias a=b\n", encoding="utf-8")
    (tmp_path / ".zshrc").write_text("alias a=b\n", encoding="utf-8")
    assert I.paso_enlace(c) and I.paso_enlace(c)                       # repetir no duplica
    archivo = tmp_path / donde
    texto = archivo.read_text(encoding="utf-8")
    assert contiene in texto and texto.count(I.MARCA_PATH) == 1
    assert c.manifiesto.de("path")["archivo"] == str(archivo)
    p = c.manifiesto.de("path")
    I._quitar_de_path(p["archivo"], p["propio"])
    assert not archivo.exists() or (I.MARCA_PATH not in archivo.read_text(encoding="utf-8") and "alias a=b" in archivo.read_text(encoding="utf-8"))


def test_si_ya_esta_en_el_path_no_se_toca_ningun_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/bash")
    c = ctx_en(tmp_path)
    monkeypatch.setenv("PATH", f"/usr/bin:{c.bin}")
    assert I.paso_enlace(c)
    assert not (tmp_path / ".bashrc").exists() and c.manifiesto.de("path") is None


def test_al_desinstalar_se_ofrece_borrar_tambien_ajustes_claves_y_datos(tmp_path, monkeypatch):
    carpetas = {n: tmp_path / "mundo" / n for n in ("CONFIG", "DATOS", "ESTADO", "CACHE")}
    for n, p in carpetas.items():
        p.mkdir(parents=True)
        (p / "algo").write_text("x")
        monkeypatch.setattr(I.RUT, n, p)
    borradas = []
    monkeypatch.setattr(I.CL, "borrar", lambda nombre, ejecutar=None: borradas.append(nombre) or nombre == "gemini")
    respuestas = iter(["s", "s"])                                  # ¿Sigo? sí · ¿Los borro también? sí
    c = ctx_en(tmp_path, entrada=lambda _: next(respuestas))
    c.terminal = True
    c.manifiesto.anotar("enlace", ruta=str(tmp_path / "x"))
    assert I.desinstalar([], c) == 0
    assert not any(p.exists() for p in carpetas.values())
    assert "gemini" in borradas and any("llavero: gemini" in t for t in c.texto)


def test_al_desinstalar_por_defecto_se_conservan_los_datos(tmp_path, monkeypatch):
    p = tmp_path / "mundo" / "CONFIG"
    p.mkdir(parents=True)
    monkeypatch.setattr(I.RUT, "CONFIG", p)
    respuestas = iter(["s", ""])                                   # ¿Sigo? sí · ¿Los borro también? (Intro = no)
    c = ctx_en(tmp_path, entrada=lambda _: next(respuestas))
    c.terminal = True
    c.manifiesto.anotar("enlace", ruta=str(tmp_path / "x"))
    assert I.desinstalar([], c) == 0 and p.exists()
    assert any("he dejado TUS AJUSTES" in t for t in c.texto)


def test_atajo_kde_si_no_se_puede_recargar_avisa_de_cerrar_sesion(tmp_path):
    def ej(o, **k):
        return SimpleNamespace(returncode=3 if o[:3] == ["systemctl", "--user", "is-active"] else 0, stdout="", stderr="")
    hecho, msg, nota = A.registrar("kde", "Meta+Space", "/u/lina", tmp_path, ejecutar=ej, which=lambda n: "/bin/kwriteconfig6")
    assert hecho and "cierres sesión" in msg
