# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Lo que dejó pasar el clasificador en la prueba en vivo: leer a lo ancho una carpeta que incluye claves o los datos de Lina. Se comprueba sin ejecutar nada: solo se clasifica el texto.
Es una capa sobre bash, no una barrera (ver S9 en el plan). `Path.home()` es la casa temporal de las pruebas."""
from pathlib import Path

import pytest

from lina.nucleo import herramientas as H

CASA = str(Path.home())


def _clase(comando):
    return H.clasificar(comando)[0]


@pytest.mark.parametrize("comando", [
    "grep -rn clave ~", "grep -rn fuente ~/", "grep -r x $HOME", "grep -r x ${HOME}", 'grep -r x "$HOME"', "grep -r x ~/.config", "grep -r x ~/.config/", "grep -r x ~/.local",
    "grep -r clave ~/.local/state", "grep -r x ~/.local/share", f"grep -rn x {CASA}", f"grep -rn x {CASA}/", "grep -rn x /home", "grep -rn x /", "grep -rn x ~ /etc 2>/dev/null",
    "grep -rn x ~ /etc 2>/dev/null | head -n 30", "grep -ri x ~ /etc /usr/local", "grep -Rl x ~", "grep -lR x ~", "grep -nr x ~", "grep --recursive x ~", "grep --dereference-recursive x ~",
    "grep --recursive x ~/", "egrep -r x ~", "fgrep -r x ~", "grep -r 'dos palabras' ~", 'grep -rn "dos palabras" ~/.config', "grep -e x -r ~", "grep -rn x ~ --include=*.toml",
    "grep -r x", "sudo grep -r x ~",
    "rg fuente ~", "rg fuente ~/.config", "rg --hidden x ~", "rg -n x ~/", "rg x", "ag x ~", "ack x ~",
    "cat ~/.config/*/*", "cat ~/.config/l*/*", "head ~/.local/state/*/*", "tail ~/.local/share/*/*", 'cat ~/.ss*/*', "strings ~/.config/*/*", "grep x ~/.config/*/*", "cat ~/.*/lina/*",
    "cd ~ && grep -rn x .", "cd ~/.config && grep -r x .", "cd ~/.config; rg x", "cd && grep -r x .", "cd $HOME && rg x .", "cd ~/.config && cat */*",
    "tar czf - ~/.config", "tar czf /tmp/a.tgz ~", "tar -czf - ~/.local", "tar --create -f - ~/.config", "cp -r ~/.config /tmp/x", "cp -a ~ /tmp/x", "cp -R ~/.local/ /tmp/x",
    "rsync -a ~/ /tmp/x", "rsync -r ~/.config /tmp/x", "zip -r /tmp/a.zip ~/.config",
    "find ~ -type f | xargs grep x", "find ~/.config -type f | xargs cat", "find ~/.config -type f -exec cat {} +", "find ~ -name '*.toml' -exec cat {} \\;", "find . -type f -exec head {} +",
    'bash -c "grep -r x ~"', "sh -c 'rg x ~'",
])
def test_leer_a_lo_ancho_se_bloquea(comando):
    assert _clase(comando) == "bloqueado", comando


@pytest.mark.parametrize("casa, comando", [
    ("/var/home/ana", "grep -rn x /home"), ("/var/home/ana", "grep -rn x /home/"), ("/var/home/ana", "grep -rn x /home/*"), ("/var/home/ana", "tar czf - /home"),
    ("/var/home/ana", "cp -r /home /tmp/x"), ("/var/home/ana", "cat /home/*/.ssh/*"), ("/var/home/ana", "grep -rn x ~"),
    ("/root", "grep -rn x /home"), ("/root", "grep -rn x /root"), ("/root", "grep -rn x ~"), ("/root", "tar czf - ~"),
])
def test_con_la_casa_fuera_de_home_tambien_se_bloquea(monkeypatch, casa, comando):
    monkeypatch.setenv("HOME", casa)
    assert _clase(comando) == "bloqueado", comando


@pytest.mark.parametrize("comando", ["ls /home", "grep -n x /home/notas.txt"])
def test_con_la_casa_fuera_de_home_lo_que_no_recorre_sigue_libre(monkeypatch, comando):
    monkeypatch.setenv("HOME", "/var/home/ana")
    assert _clase(comando) == "lectura", comando


def test_el_motivo_le_dice_a_la_ia_que_acote():
    assert "carpeta concreta" in H.clasificar("grep -rn clave ~")[1]


@pytest.mark.parametrize("comando", [
    "grep -r x ~/Documentos", "grep -rn x ~/Documentos/", 'grep -r "dos palabras" ~/Documentos', "rg x ~/Documentos", "rg --hidden x ~/Descargas", "grep -rn x /etc", "grep -r x /usr/share/doc",
    "grep x ~/.bashrc", "grep -n x ~/nota.txt", "cat ~/.config/kdeglobals", "cat ~/nota.txt", "cat ~/*.txt", "head ~/*", "ls ~/.config", "ls -R ~/.config", "ls -la ~",
    "find ~ -iname '*.pdf'", "find ~/.config -type f", 'find ~ -iname "*extendo*"', "find ~/Documentos -type f -exec file {} +", "du -sh ~/.config", "grep -c x ~/nota.txt",
    "cd ~/Documentos && grep -r x .",
])
def test_lo_acotado_sigue_igual(comando):
    assert _clase(comando) != "bloqueado", comando


@pytest.mark.parametrize("comando", ["cp -r ~/Documentos /tmp/x", "tar czf /tmp/a.tgz ~/Documentos", "rsync -a ~/Documentos/ /tmp/x", "cp ~/nota.txt /tmp/x"])
def test_copiar_algo_concreto_no_se_bloquea(comando):
    assert _clase(comando) != "bloqueado", comando


@pytest.mark.parametrize("comando", ["cat ~/.config/lina/config.toml", "grep -R x ~/.config/lina", "cat ~/.local/state/lina/llamadas_ia.jsonl", "cat ~/.ssh/id_ed25519"])
def test_lo_directo_sigue_bloqueado(comando):
    assert _clase(comando) == "bloqueado"


# ---------------------------------------------------------------- journalctl: sin filtrar lleva el registro de Lina
@pytest.mark.parametrize("comando", ["journalctl", "journalctl -n 50", "journalctl -b", "journalctl --user", "journalctl --user -n 50", "journalctl --user --since today", "journalctl -xe",
                                     "journalctl --since today | grep x", "journalctl -g clave", "sudo journalctl -n 50", "journalctl -p info", "journalctl -p debug -n 5", "journalctl -p err..info",
                                     "journalctl --priority=notice", "journalctl -o json -n 5", "journalctl -u lina", "journalctl --user-unit=lina -n 5", "journalctl -t lina -n 5",
                                     "journalctl --identifier=lina"])
def test_sin_filtrar_pide_confirmacion(comando):
    clase, motivo = H.clasificar(comando)
    assert clase == "critico" and "Lina" in motivo, comando


@pytest.mark.parametrize("comando", ["journalctl -u NetworkManager -n 20", "journalctl --user -u pipewire -n 20", "journalctl --user-unit=pipewire -n 5", "journalctl --unit=sshd", "journalctl -uNetworkManager",
                                     "journalctl -k", "journalctl --dmesg -n 20", "journalctl -k -b -1", "journalctl -t kernel", "journalctl --identifier=sudo", "journalctl -p err -b", "journalctl -p warning",
                                     "journalctl -p 0..4", "journalctl -p err..warning", "journalctl -p3", "journalctl --priority=crit", "journalctl -p err | grep x", "journalctl --disk-usage",
                                     "journalctl --list-boots"])
def test_con_filtro_sigue_libre(comando):
    assert _clase(comando) == "lectura", comando


def test_no_afecta_a_otros_comandos():
    from lina.nucleo import clasificador as CLA
    assert CLA.lectura_sensible("ls ~/Documentos") is None and CLA.lectura_sensible("grep journalctl notas.txt") is None
