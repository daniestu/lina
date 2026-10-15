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
