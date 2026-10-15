"""Pruebas de ataque al ayudante de root (lina-instalar): lo que se le puede mandar y lo que nunca debe llegar al gestor de paquetes."""
import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "src" / "lina" / "datos" / "privilegios" / "lina-instalar"


def _cargar():
    cargador = importlib.machinery.SourceFileLoader("lina_instalar", str(RUTA))
    spec = importlib.util.spec_from_loader("lina_instalar", cargador)
    modulo = importlib.util.module_from_spec(spec)
    cargador.exec_module(modulo)
    return modulo


LI = _cargar()


def os_release(tmp_path, texto):
    ruta = tmp_path / "os-release"
    ruta.write_text(texto, encoding="utf-8")
    return str(ruta)


class Falso:
    def __init__(self, codigo=0):
        self.llamadas, self.codigo = [], codigo

    def __call__(self, cmd, **kw):
        self.llamadas.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, self.codigo)


MALOS = ["-Syu", "--overwrite=/etc/passwd", "--overwrite", "-U", "foo;rm -rf /", "foo && id", "$(id)", "`id`", "a b", "", " ", "../x", "/tmp/x.pkg.tar.zst",
         "./x.deb", "https://evil.example/x.rpm", "http://x", "paquete-", "@grupo", "*", "foo*", "foo=1.0", "foo/stable", "extra/foo", "foo:amd64x", "foo\nbar",
         "x" * 101, "ñandú", "-", "--", ".oculto", "a..b", "foo|bar", "foo>bar", "~root", "foo\x00bar"]


@pytest.mark.parametrize("nombre", MALOS)
def test_nombres_peligrosos_se_rechazan(nombre):
    with pytest.raises(LI.Rechazo):
        LI.validar([nombre])


def test_nombres_normales_valen():
    assert LI.validar(["gtk-layer-shell", "python-gobject", "libstdc++", "SDL2", "gir1.2-gtk-3.0", "ydotool", "ydotool"]) == \
        ["gtk-layer-shell", "python-gobject", "libstdc++", "SDL2", "gir1.2-gtk-3.0", "ydotool"]


def test_limites_de_cantidad():
    with pytest.raises(LI.Rechazo):
        LI.validar([])
    with pytest.raises(LI.Rechazo):
        LI.validar([f"p{i}" for i in range(LI.MAX_PAQUETES + 1)])


@pytest.mark.parametrize("nombre", ["sudo", "doas", "polkit", "polkit-kde-agent", "pam", "shadow", "SUDO", "Polkit"])
def test_no_toca_el_software_de_privilegios(nombre):
    with pytest.raises(LI.Rechazo):
        LI.validar([nombre])


@pytest.mark.parametrize("texto,gestor,delante", [
    ('ID=arch', "pacman", "--"), ('ID=cachyos\nID_LIKE=arch', "pacman", "--"), ('ID=ubuntu\nID_LIKE=debian', "apt-get", "--"),
    ('ID=fedora', "dnf", None), ('ID=opensuse-tumbleweed\nID_LIKE="suse opensuse"', "zypper", None)])
def test_el_gestor_lo_decide_el_sistema(tmp_path, texto, gestor, delante):
    f = Falso()
    assert LI.instalar(["ydotool"], os_release(tmp_path, texto), f, euid=0) == 0
    cmd, kw = f.llamadas[0]
    assert cmd[0] == gestor and cmd[-1] == "ydotool" and (delante is None or cmd[-2] == delante)
    assert kw["stdin"] == subprocess.DEVNULL and kw["env"]["PATH"].startswith("/usr/local/sbin") and kw["timeout"] == LI.TIEMPO
    assert "HOME" in kw["env"] and len(kw["env"]) <= 6                       # entorno limpio: nada heredado del usuario


def test_apt_no_puede_quitar_paquetes(tmp_path):
    f = Falso()
    LI.instalar(["ydotool"], os_release(tmp_path, "ID=debian"), f, euid=0)
    assert "--no-remove" in f.llamadas[0][0]


def test_distribucion_desconocida_no_hace_nada(tmp_path):
    f = Falso()
    with pytest.raises(LI.Rechazo):
        LI.instalar(["ydotool"], os_release(tmp_path, "ID=nixos"), f, euid=0)
    assert f.llamadas == []


def test_sin_root_no_hace_nada(tmp_path):
    f = Falso()
    with pytest.raises(LI.Rechazo):
        LI.instalar(["ydotool"], os_release(tmp_path, "ID=arch"), f, euid=1000)
    assert f.llamadas == []


def test_un_rechazo_no_llega_nunca_al_gestor(tmp_path):
    f = Falso()
    for malo in MALOS[:12]:
        with pytest.raises(LI.Rechazo):
            LI.instalar([malo], os_release(tmp_path, "ID=arch"), f, euid=0)
    assert f.llamadas == []


def test_main_devuelve_codigos(capsys):
    assert LI.main([]) == 2 and LI.main(["version"]) == 0 and LI.main(["gestor", "extra"]) == 2
    assert LI.main(["instalar", "-Syu"]) == 3
    assert "no válido" in capsys.readouterr().err


def test_solo_biblioteca_estandar():
    import ast
    permitido = {"os", "re", "subprocess", "sys", "syslog"}
    modulos = set()
    for nodo in ast.walk(ast.parse(RUTA.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            modulos |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            modulos.add((nodo.module or "").split(".")[0])
    assert modulos <= permitido, modulos - permitido
