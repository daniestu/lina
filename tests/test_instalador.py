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
    assert A.escritorio({"XDG_CURRENT_DESKTOP": "sway"}) == "otro"


def test_atajo_kde_se_registra_y_se_quita(tmp_path):
    ordenes = []
    ej = lambda o, **k: (ordenes.append(o), ok())[1]
    hecho, msg, nota = A.registrar("kde", "Meta+Space", "/u/lina", tmp_path, ejecutar=ej, which=lambda n: "/bin/kwriteconfig6" if n == "kwriteconfig6" else None)
    assert hecho and nota["tecla"] == "Meta+Space"
    desktop = Path(nota["archivo"])
    assert "Exec=/u/lina pulsar" in desktop.read_text()
    assert ordenes[0][-2:] == ["_launch", "Meta+Space"]
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

