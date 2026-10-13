import importlib
import os

import pytest


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith("XDG_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("HOME", str(tmp_path))
    from lina.nucleo import rutas as R
    return importlib.reload(R)


def test_carpetas_xdg_por_defecto(rutas, tmp_path):
    assert rutas.CONFIG == tmp_path / ".config" / "lina"
    assert rutas.DATOS == tmp_path / ".local" / "share" / "lina"
    assert rutas.ESTADO == tmp_path / ".local" / "state" / "lina"


def test_respeta_variables_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from lina.nucleo import rutas as R
    R = importlib.reload(R)
    assert R.CONFIG == tmp_path / "cfg" / "lina"


def test_editable_copia_el_de_fabrica_una_sola_vez(rutas):
    ruta = rutas.editable("activacion.txt")
    assert ruta == rutas.CONFIG / "activacion.txt" and ruta.is_file()
    ruta.write_text("# mío\n", encoding="utf-8")
    assert rutas.editable("activacion.txt").read_text(encoding="utf-8") == "# mío\n"      # no se pisa lo del usuario


def test_editable_sin_archivo_de_fabrica_solo_devuelve_la_ruta(rutas):
    assert rutas.editable("no_existe.txt") == rutas.CONFIG / "no_existe.txt"
    assert not (rutas.CONFIG / "no_existe.txt").exists()


def test_carpeta_usuario_lee_user_dirs(rutas, tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_DOCUMENTS_DIR="$HOME/Docs"\n', encoding="utf-8")
    assert rutas.carpeta_usuario("DOCUMENTS", "Documents") == tmp_path / "Docs"
    assert rutas.carpeta_usuario("MUSIC", "Music") == tmp_path / "Music"


def test_datos_de_fabrica_completos(rutas):
    for n in ("activacion.txt", "comandos.txt", "politica.txt", "presupuesto.txt", "vocabulario.txt", "paquetes_confiables.txt"):
        assert (rutas.DEFECTOS / n).is_file(), n
