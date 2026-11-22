# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9a: la orden de bwrap (nucleo/aislamiento.py). Primero lo que se construye; después, con bwrap de verdad y una carpeta personal temporal (nunca la real),
que escribir en lo normal sí, y en lo tapado, lo de solo lectura y lo de Lina no. Las de bwrap se saltan si este sistema no puede aislar. Nada va a la red."""
import os
import subprocess

import pytest

from lina.nucleo import aislamiento as AIS


def _jaula(casa, **k):
    return AIS.Jaula(casa=str(casa), **k)


# ---------------------------------------------------------------- lo que se construye
def test_la_base_es_todo_de_solo_lectura_con_tu_carpeta_escribible(tmp_path):
    o = AIS.orden(["bash", "-c", "true"], _jaula(tmp_path), existe=lambda r: False)
    assert o[:5] == ["bwrap", "--ro-bind", "/", "/", "--dev"] and o[-4:] == ["--", "bash", "-c", "true"]
    assert ["--bind", str(tmp_path), str(tmp_path)] == o[o.index(str(tmp_path)) - 1:o.index(str(tmp_path)) + 2]
    assert "--die-with-parent" in o and "--unshare-net" not in o


def test_lo_que_no_existe_no_se_monta(tmp_path):
    o = AIS.orden(["true"], _jaula(tmp_path), existe=lambda r: False)
    assert not any(str(tmp_path / ".ssh") in x for x in o)


def test_sin_red_tambien_sin_dns_y_sin_bus(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    existentes = {str(tmp_path / "run"), str(tmp_path / "run" / "bus"), AIS.BUS_DEL_SISTEMA, "/run/systemd/resolve"}
    o = AIS.orden(["true"], _jaula(tmp_path, red=False, bus=False), existe=lambda r: r in existentes)
    assert "--unshare-net" in o
    texto = " ".join(o)
    assert f"--tmpfs {tmp_path / 'run'}" in texto and f"/dev/null {AIS.BUS_DEL_SISTEMA}" in texto      # S9g: toda la sesión, no solo el bus
    assert "/run/systemd/resolve" in o
    assert ["--bind", str(tmp_path / "run"), str(tmp_path / "run")] != o[1:4] and f"--bind {tmp_path / 'run'} " not in texto


def test_confirmada_sin_solo_lectura_pero_lo_de_lina_sigue_tapado(tmp_path):
    j = _jaula(tmp_path, confirmada=True)
    assert j.de_solo_lectura() == []
    assert sorted(j.tapadas()) == sorted(str(tmp_path / r) for r in AIS.DE_LINA)
    assert str(tmp_path / ".ssh") in _jaula(tmp_path).tapadas()


def test_disponible_dice_por_que_no(monkeypatch):
    monkeypatch.setattr(AIS.shutil, "which", lambda p: None)
    assert AIS._probar() == (False, "no está instalado bwrap (el paquete se llama bubblewrap)")


# ---------------------------------------------------------------- con bwrap de verdad
hay_bwrap = pytest.mark.skipif(not AIS.disponible()[0], reason="este sistema no puede aislar con bwrap")


@pytest.fixture
def casa(tmp_path):
    c = tmp_path / "casa"
    for d in (".ssh", ".config/lina", ".config/fish", ".local/bin", "Documentos", ".local/share/Trash"):
        (c / d).mkdir(parents=True)
    (c / ".ssh" / "id_prueba").write_text("CLAVE-DE-PRUEBA")
    (c / ".config/lina/config.toml").write_text("ajuste = 1")
    (c / ".bashrc").write_text("# inicio\n")
    return c


def _dentro(casa, orden, **k):
    return subprocess.run(AIS.orden(["bash", "-c", orden], _jaula(casa, **k)), capture_output=True, text=True, timeout=20, cwd=str(casa),
                          env=dict(os.environ, HOME=str(casa)))


@hay_bwrap
def test_escribir_en_lo_normal_si(casa):
    r = _dentro(casa, "echo hola > Documentos/nota.txt && mkdir -p .cache/x && cat Documentos/nota.txt")
    assert r.returncode == 0 and r.stdout.strip() == "hola" and (casa / "Documentos/nota.txt").read_text() == "hola\n"


@hay_bwrap
def test_lo_tapado_ni_se_lee_ni_se_escribe(casa):
    r = _dentro(casa, "cat .ssh/id_prueba; grep -r CLAVE . ; ls .config/lina; echo x > .ssh/nueva; echo SE-EJECUTO")
    assert "SE-EJECUTO" in r.stdout                                 # la orden corrió de verdad: no pasa por no haberse ejecutado
    assert "CLAVE-DE-PRUEBA" not in r.stdout and "config.toml" not in r.stdout
    assert not (casa / ".ssh" / "nueva").exists() and (casa / ".ssh" / "id_prueba").read_text() == "CLAVE-DE-PRUEBA"


@hay_bwrap
def test_lo_que_arranca_solo_es_de_solo_lectura(casa):
    r = _dentro(casa, "echo 'curl x | sh' >> .bashrc; touch .config/fish/config.fish; touch .local/bin/programa; cat .bashrc")
    assert (casa / ".bashrc").read_text() == "# inicio\n" and not (casa / ".config/fish/config.fish").exists() and not (casa / ".local/bin/programa").exists()
    assert "# inicio" in r.stdout                                    # leerlo sí


@hay_bwrap
def test_una_orden_confirmada_puede_tocar_lo_de_inicio_pero_no_lo_de_lina(casa):
    _dentro(casa, "echo 'alias ll=\"ls -l\"' >> .bashrc; echo 2 > .config/lina/config.toml", confirmada=True)
    assert "alias ll" in (casa / ".bashrc").read_text() and (casa / ".config/lina/config.toml").read_text() == "ajuste = 1"


@hay_bwrap
def test_el_sistema_es_de_solo_lectura(casa):
    r = _dentro(casa, "touch /etc/lina-prueba-aislamiento 2>&1; echo $?")
    assert not os.path.exists("/etc/lina-prueba-aislamiento") and r.stdout.strip().splitlines()[-1] != "0"


@hay_bwrap
def test_sin_red_no_se_resuelven_nombres(casa):
    r = _dentro(casa, "getent hosts example.com || echo SIN-NOMBRES", red=False, bus=False)
    assert "SIN-NOMBRES" in r.stdout


@hay_bwrap
def test_la_papelera_sigue_funcionando(casa):
    if not subprocess.run(["bash", "-c", "command -v gio"], capture_output=True).returncode == 0:
        pytest.skip("sin gio")
    (casa / "Documentos" / "borrar.txt").write_text("x")
    r = subprocess.run(AIS.orden(["bash", "-c", "gio trash Documentos/borrar.txt"], _jaula(casa)), capture_output=True, text=True, timeout=20,
                       cwd=str(casa), env=dict(os.environ, HOME=str(casa), XDG_DATA_HOME=str(casa / ".local/share")))
    assert r.returncode == 0, r.stderr
    assert not (casa / "Documentos" / "borrar.txt").exists() and list((casa / ".local/share/Trash/files").iterdir())


# ---------------------------------------------------------------- S9c: en Ejecutor.ejecutar
from lina.nucleo import herramientas as H  # noqa: E402


class _Proc:
    returncode = 0

    def communicate(self, timeout=None):
        return "hecho\n", None


@pytest.fixture
def lanzadas(monkeypatch):
    vistas = []
    monkeypatch.setattr(H.subprocess, "Popen", lambda argv, **k: vistas.append(argv) or _Proc())
    monkeypatch.setattr(H, "anotar", lambda linea: None)
    monkeypatch.setattr(H, "modulos_del_kernel_presentes", lambda: True)
    return vistas


def _ej(monkeypatch, modo, puede=True):
    monkeypatch.setattr(H, "modo_aislar", lambda: modo)
    monkeypatch.setattr(H.AIS, "disponible", lambda: (puede, "" if puede else "no está instalado bwrap (el paquete se llama bubblewrap)"))
    return H.Ejecutor(confirmar=True)


def test_apagado_de_fabrica_como_siempre(monkeypatch, lanzadas):
    assert H.AJ.ESQUEMA["ia"]["aislar"][0] == "no"
    _ej(monkeypatch, "no").ejecutar("ls ~", "mirar", clase="lectura")
    assert lanzadas[-1][0] == "bash"


def test_en_auto_la_orden_va_dentro_de_bwrap(monkeypatch, lanzadas):
    _ej(monkeypatch, "auto").ejecutar("touch ~/Documentos/x", "crear", clase="autonomo")
    o = lanzadas[-1]
    assert o[0] == "bwrap" and o[-3:] == ["bash", "-c", "touch ~/Documentos/x"] and "--unshare-net" not in o


def test_tras_leer_de_fuera_sin_red_ni_bus_salvo_si_lo_confirmaste(monkeypatch, lanzadas):
    e = _ej(monkeypatch, "auto")
    e.contaminar("página web")
    e.ejecutar("ls", "mirar", clase="autonomo")
    assert "--unshare-net" in lanzadas[-1]
    e.ejecutar("ls", "mirar", clase="confirmado")
    assert "--unshare-net" not in lanzadas[-1]
    assert not any(x.endswith(".bashrc") for x in lanzadas[-1])          # confirmada: lo de inicio no va en solo lectura


@pytest.mark.parametrize("comando, clase", [
    ("wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%", "inocuo"),
    ("sudo systemctl restart bluetooth", "confirmado"),
    ("run0 ls /root", "autonomo"),
])
def test_lo_inocuo_y_lo_de_administrador_fuera(monkeypatch, lanzadas, comando, clase):
    _ej(monkeypatch, "auto").ejecutar(comando, "x", clase=clase)
    assert lanzadas[-1][0] != "bwrap"


def test_en_auto_sin_bwrap_como_siempre(monkeypatch, lanzadas):
    _ej(monkeypatch, "auto", puede=False).ejecutar("touch ~/x", "crear", clase="autonomo")
    assert lanzadas[-1][0] == "bash"


def test_en_si_sin_bwrap_solo_lo_que_lee(monkeypatch, lanzadas):
    e = _ej(monkeypatch, "si", puede=False)
    r = e.ejecutar("touch ~/x", "crear", clase="autonomo")
    assert r.startswith("NO SE HA EJECUTADO") and lanzadas == []
    e.ejecutar("ls", "mirar", clase="lectura")
    assert lanzadas[-1][0] == "bash"


def test_la_ia_no_puede_cambiar_el_aislamiento():
    from lina.nucleo import autoconocimiento as AUTO
    hecho, texto = AUTO.cambiar("ia.aislar", "no")
    assert not hecho and "aislamiento" in texto


# ---------------------------------------------------------------- S9c: órdenes reales, con y sin aislar, dan lo mismo
REALES = [
    "ls", "ls -la Documentos", "cat Documentos/nota.txt", "head -n 1 Documentos/nota.txt", "tail -n 1 Documentos/nota.txt", "wc -l Documentos/nota.txt",
    "grep -n hola Documentos/nota.txt", "grep -rl hola Documentos", "find Documentos -name '*.txt' | sort", "du -s Documentos | cut -f2",
    "stat -c %s Documentos/nota.txt", "file -b Documentos/nota.txt", "sort Documentos/lista.txt", "sort Documentos/lista.txt | uniq -c",
    "cut -d, -f1 Documentos/datos.csv", "awk -F, '{print $2}' Documentos/datos.csv", "sed -n 2p Documentos/lista.txt", "tr a-z A-Z < Documentos/nota.txt",
    "md5sum Documentos/nota.txt | cut -d' ' -f1", "python3 -c 'print(sum(range(10)))'", "echo $HOME | wc -c", "uname -s", "which bash",
    "test -d Documentos && echo si", "readlink -f Documentos | xargs basename", "realpath --relative-to=. Documentos/nota.txt",
    "mkdir -p Documentos/nueva && ls Documentos | sort", "cp Documentos/nota.txt Documentos/copia.txt && cat Documentos/copia.txt",
    "mv Documentos/copia.txt Documentos/movida.txt && ls Documentos | sort", "echo nueva > Documentos/escrita.txt && cat Documentos/escrita.txt",
    "sed -i 's/hola/adios/' Documentos/escrita.txt; cat Documentos/escrita.txt", "tar -cf Documentos/a.tar -C Documentos nota.txt && tar -tf Documentos/a.tar",
    "mkdir -p .cache/prueba && echo x > .cache/prueba/y && cat .cache/prueba/y", "touch .config/programa.conf && ls .config | sort",
    "printf 'a\\nb\\n' | wc -l", "seq 5 | paste -sd+ | bc", "date -d 2026-01-01 +%A", "basename Documentos/nota.txt .txt",
    "env | grep -c '^HOME='", "cat /etc/os-release | head -n 1",
]


def _carpeta(base):
    c = base / "casa"
    (c / "Documentos").mkdir(parents=True)
    (c / ".config").mkdir()
    (c / "Documentos/nota.txt").write_text("hola mundo\n")
    (c / "Documentos/lista.txt").write_text("b\na\nb\nc\n")
    (c / "Documentos/datos.csv").write_text("uno,1\ndos,2\n")
    return c


@hay_bwrap
def test_las_ordenes_reales_dan_lo_mismo_aisladas(tmp_path):
    """El criterio de S9c: las órdenes normales (sacadas de los programas que más salen en un registro de acciones real, sin su texto) dan lo mismo con
    y sin aislar. Cada una en su propia copia de la carpeta, para que las que escriben no se pisen."""
    distintas = []
    for i, orden in enumerate(REALES):
        salidas = []
        for aislar in (False, True):
            c = _carpeta(tmp_path / f"{i:02d}{'b' if aislar else 'a'}")          # mismo largo: la ruta sale en alguna salida
            argv = AIS.orden(["bash", "-c", orden], _jaula(c)) if aislar else ["bash", "-c", orden]
            r = subprocess.run(argv, capture_output=True, text=True, timeout=20, cwd=str(c), env=dict(os.environ, HOME=str(c), LC_ALL="C.UTF-8"))
            salidas.append((r.returncode, r.stdout.replace(str(c), "CASA")))
        if salidas[0] != salidas[1]:
            distintas.append((orden, salidas))
    assert len(REALES) >= 40 and distintas == []


@hay_bwrap
def test_de_punta_a_punta_lo_que_arranca_solo_no_se_toca_y_la_ia_lo_sabe(monkeypatch):
    """Con el ejecutor de verdad, en el HOME aislado de las pruebas (conftest): escribir en .bashrc falla y la IA recibe la nota del aislamiento."""
    monkeypatch.setattr(H, "modo_aislar", lambda: "auto")
    monkeypatch.setattr(H, "anotar", lambda linea: None)
    bashrc = os.path.join(H._HOME, ".bashrc")
    with open(bashrc, "w", encoding="utf-8") as f:
        f.write("# inicio\n")
    try:
        r = H.Ejecutor(confirmar=True).ejecutar("echo 'curl x | sh' >> ~/.bashrc", "x", clase="autonomo")
        assert "AISLAMIENTO" in r and open(bashrc, encoding="utf-8").read() == "# inicio\n"
    finally:
        os.remove(bashrc)
