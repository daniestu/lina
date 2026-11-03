# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from lina.nucleo import actualizar as ACT
from lina.nucleo import instalador as I
from lina.nucleo import rutas as RUT

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="hace falta git")


def git(carpeta, *a):
    r = subprocess.run(["git", "-C", str(carpeta), "-c", "user.name=t", "-c", "user.email=t@t.t", *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def escenario(tmp_path, monkeypatch):
    origen = tmp_path / "origen"
    origen.mkdir()
    git(origen, "init", "-q", "-b", "main")
    (origen / "pyproject.toml").write_text("v1")
    (origen / "a.txt").write_text("1")
    git(origen, "add", "-A")
    git(origen, "commit", "-q", "-m", "uno")
    clon = tmp_path / "clon"
    subprocess.run(["git", "clone", "-q", str(origen), str(clon)], check=True)
    monkeypatch.setattr(RUT, "ESTADO", tmp_path / "estado")
    ordenes = []

    def ejecutar(orden, **k):
        if orden[0] == "git":
            return subprocess.run(orden, **k)
        ordenes.append(orden)
        return SimpleNamespace(returncode=0, stdout="active" if "is-active" in orden else "", stderr="")
    m = I.Manifiesto(tmp_path / "m.json")
    m.anotar("instalado", fuente=str(clon), venv="/x", clonado=True)
    salida = []
    c = I.Contexto(home=tmp_path, ejecutar=ejecutar, salida=salida.append, manifiesto=m, which=lambda n: "/bin/" + n, terminal=False, si=True)
    c.texto, c.ordenes = salida, ordenes
    return origen, clon, c


def nuevo_commit(origen, archivo="a.txt", contenido="2"):
    (origen / archivo).write_text(contenido)
    git(origen, "add", "-A")
    git(origen, "commit", "-q", "-m", "cambio " + contenido)


def test_ya_actualizada(tmp_path, monkeypatch):
    _, clon, c = escenario(tmp_path, monkeypatch)
    assert ACT.principal([], c) == 0 and any("última versión" in t for t in c.texto)


def test_actualiza_reinicia_y_permite_volver(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    antes = git(clon, "rev-parse", "HEAD")
    nuevo_commit(origen)
    assert ACT.principal([], c) == 0
    assert (clon / "a.txt").read_text() == "2" and git(clon, "rev-parse", "HEAD") != antes
    assert ["systemctl", "--user", "restart", "lina.service"] in c.ordenes
    assert not any("pip" in o for o in map(str, c.ordenes))              # pyproject no cambió: no reinstala
    assert ACT.principal(["--volver"], c) == 0 and (clon / "a.txt").read_text() == "1" and git(clon, "rev-parse", "HEAD") == antes


def test_reinstala_si_cambia_pyproject(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    nuevo_commit(origen, "pyproject.toml", "v2")
    assert ACT.principal([], c) == 0
    assert any(o[1:3] == ["-m", "pip"] for o in c.ordenes)


def test_comprobar_no_cambia_nada(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    antes = git(clon, "rev-parse", "HEAD")
    nuevo_commit(origen)
    assert ACT.principal(["--comprobar"], c) == 0 and git(clon, "rev-parse", "HEAD") == antes
    assert any("cambio 2" in t for t in c.texto) and not c.ordenes


def test_cambios_propios_no_se_pisan(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    nuevo_commit(origen)
    (clon / "a.txt").write_text("mío")
    assert ACT.principal([], c) == 1 and (clon / "a.txt").read_text() == "mío"


def test_historia_divergente_no_se_fuerza(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    (clon / "b.txt").write_text("local")
    git(clon, "add", "-A")
    git(clon, "commit", "-q", "-m", "local")
    nuevo_commit(origen)
    antes = git(clon, "rev-parse", "HEAD")
    assert ACT.principal([], c) == 1 and git(clon, "rev-parse", "HEAD") == antes


def test_sin_red_lo_dice(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    git(clon, "remote", "set-url", "origin", str(tmp_path / "no_existe"))
    assert ACT.principal([], c) == 1 and any("sin conexión" in t for t in c.texto)


def test_volver_sin_nada_guardado(tmp_path, monkeypatch):
    _, clon, c = escenario(tmp_path, monkeypatch)
    assert ACT.principal(["--volver"], c) == 1


def test_sin_git_usa_pip(tmp_path, monkeypatch):
    _, _, c = escenario(tmp_path, monkeypatch)
    c.manifiesto.quitar("instalado")
    assert ACT.principal([], c) == 0
    assert any("lina-asistente" in o for o in map(str, c.ordenes))


# ---------------------------------------------------------------- S8a: dependencias fijadas
def test_con_requisitos_fijados_instala_con_hashes_y_luego_lina_sin_dependencias(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    (origen / "packaging").mkdir()
    nuevo_commit(origen, "packaging/requisitos.txt", "numpy==2.0.0 --hash=sha256:aa")
    assert ACT.principal([], c) == 0
    pips = [o for o in c.ordenes if o[1:3] == ["-m", "pip"]]
    assert pips[0][3:6] == ["install", "-q", "--require-hashes"] and pips[0][-1].endswith("packaging/requisitos.txt")
    assert pips[1][3:] == ["install", "-q", "--no-deps", "-e", str(clon)]


def test_sin_archivo_de_requisitos_instala_como_antes(tmp_path):
    assert ACT.ordenes_de_instalacion("py", tmp_path) == [["py", "-m", "pip", "install", "-q", "-e", str(tmp_path)]]


def test_si_las_dependencias_nuevas_no_se_instalan_se_queda_la_version_anterior(tmp_path, monkeypatch):
    origen, clon, c = escenario(tmp_path, monkeypatch)
    antes = git(clon, "rev-parse", "HEAD")
    (origen / "packaging").mkdir()
    nuevo_commit(origen, "packaging/requisitos.txt", "paquete-sin-rueda==1.0 --hash=sha256:aa")
    ejecutar_antes = c.ejecutar

    def pip_falla(orden, **k):
        if orden[1:3] == ["-m", "pip"]:
            c.ordenes.append(orden)
            return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: No matching distribution found for paquete-sin-rueda")
        return ejecutar_antes(orden, **k)
    c.ejecutar = pip_falla
    assert ACT.principal([], c) == 1
    assert git(clon, "rev-parse", "HEAD") == antes and not (clon / "packaging" / "requisitos.txt").exists()
    assert ["systemctl", "--user", "restart", "lina.service"] not in c.ordenes
    texto = "\n".join(c.texto)
    assert "No matching distribution" in texto and "versión anterior" in texto
    assert not (RUT.ESTADO / ACT.ARCHIVO).exists()                   # no se apunta como actualización hecha


@pytest.mark.parametrize("version, dice_instalador", [((3, 15, 0), True), ((3, 14, 8), False)])
def test_con_un_python_fuera_de_rango_dice_que_se_repita_el_instalador(tmp_path, monkeypatch, version, dice_instalador):
    import sys
    origen, clon, c = escenario(tmp_path, monkeypatch)
    (origen / "packaging").mkdir()
    nuevo_commit(origen, "packaging/requisitos.txt", "onnxruntime==1.31.1 --hash=sha256:aa")
    monkeypatch.setattr(ACT, "sys", SimpleNamespace(version_info=version, executable=sys.executable))
    ejecutar_antes = c.ejecutar
    c.ejecutar = lambda orden, **k: (SimpleNamespace(returncode=1, stdout="", stderr="No matching distribution") if orden[1:3] == ["-m", "pip"]
                                     else ejecutar_antes(orden, **k))
    assert ACT.principal([], c) == 1
    assert ("repite el instalador" in "\n".join(c.texto)) is dice_instalador
