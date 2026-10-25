# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Credenciales (fase 17, S4): lo que guarda tokens se bloquea siempre; los historiales se leen solo con tu confirmación; y lo normal sigue pasando.
Con el HOME aislado del conftest: ~ es la casa temporal de las pruebas."""
from pathlib import Path

import pytest

from lina.nucleo import herramientas as H

CASA = str(Path.home())

CREDENCIALES = [
    ".config/gh/hosts.yml",
    ".docker/config.json",
    ".config/containers/auth.json",
    ".kube/config",
    ".git-credentials",
    ".config/git/credentials",
    ".config/google-chrome/Default/Cookies",
    ".config/chromium/Default/Network/Cookies",
    ".config/BraveSoftware/Brave-Browser/Default/Cookies",
    ".config/BraveSoftware/Brave-Browser/Default/Web Data",
    ".config/BraveSoftware/Brave-Browser/Local State",
    ".config/vivaldi/Default/Cookies",
    ".config/microsoft-edge/Default/Web Data",
    ".config/opera/Cookies",
    ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies",
    ".config/rclone/rclone.conf",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".terraform.d/credentials.tfrc.json",
    ".config/gcloud/credentials.db",
    ".azure/accessTokens.json",
    ".config/hub",
    ".local/share/keyrings/login.keyring",
]

HISTORIALES = [".bash_history", ".zsh_history", ".zhistory", ".local/share/fish/fish_history", ".python_history", ".psql_history",
               ".mysql_history", ".sqlite_history", ".node_repl_history", ".config/BraveSoftware/Brave-Browser/Default/History",
               ".config/google-chrome/Default/History"]


def _formas(ruta):
    """La misma ruta escrita como lo haría la IA: con ~, con $HOME y absoluta (dentro de la casa de pruebas)."""
    citada = f'"{ruta}"' if " " in ruta else ruta
    return [f"~/{citada}", f"$HOME/{citada}", f"{CASA}/{citada}" if " " not in ruta else f'"{CASA}/{ruta}"']


@pytest.mark.parametrize("ruta", CREDENCIALES)
def test_las_credenciales_se_bloquean(ruta):
    for r in _formas(ruta):
        for comando in (f"cat {r}", f"cp {r} {CASA}/Documentos/copia", f"grep -r token {r}", f"base64 {r}"):
            clase, motivo = H.clasificar(comando)
            assert clase == "bloqueado", comando
            assert "en su terminal" in motivo, motivo


@pytest.mark.parametrize("comando", [
    "gh auth token", "gh auth status -t", "gh auth status --show-token", "docker-credential-secretservice list",
    "kubectl config view --raw", "git credential fill", "git -C ~/proyecto credential fill", "git credential-store get",
    "pass show correo/gmail", "pass otp banco", "pass correo/gmail", "sudo pass show x",
    r"cat ~/.config/BraveSoftware/Brave-Browser/Default/Web\ Data", "find ~/.config/BraveSoftware -name Cookies",
    "cat ~/.config/BraveSoftware/*/*/Cookies", "cat .npmrc",
])
def test_las_ordenes_que_imprimen_secretos_se_bloquean(comando):
    assert H.clasificar(comando)[0] == "bloqueado", comando


@pytest.mark.parametrize("ruta", HISTORIALES)
def test_los_historiales_piden_confirmacion(ruta):
    for r in _formas(ruta):
        for comando in (f"cat {r}", f"tail -n 50 {r}", f"grep mount {r}"):
            clase, motivo = H.clasificar(comando)
            assert clase == "critico", comando
            assert "se enviará a la IA" in motivo, motivo


@pytest.mark.parametrize("comando", [
    "gh pr list", "gh auth status", "docker ps", "kubectl get pods", "git log --oneline -5", "git status",
    "cat ~/.config/gh/config.yml", "ls ~/.config/BraveSoftware", "ls ~/.config/google-chrome",
    "curl -s https://portal.azure.com", "cat ~/Documentos/notas.txt", "bash -c 'history | tail'", "echo bypass",
    "xdg-open https://www.opera.com", "cat ~/.config/kwinrc",
])
def test_lo_normal_sigue_pasando(comando):
    assert H.clasificar(comando)[0] not in ("bloqueado", "critico"), comando


def test_abrir_brave_sigue_siendo_abrir():
    assert H.clasificar("brave")[0] not in ("bloqueado", "critico")


@pytest.mark.parametrize("comando", ["grep pass archivo", "grep pass ~/Documentos/notas.txt", "echo pass", "ls | grep pass", "ls|grep pass x",
                                     "cat notas | grep -i pass"])
def test_pass_como_palabra_suelta_no_se_bloquea(comando):
    assert H.clasificar(comando)[0] == "lectura", comando


@pytest.mark.parametrize("comando", ["true && pass x", "(pass x)", "$(pass x)", "echo $(pass show x)", "ls | pass x"])
def test_pass_como_programa_si(comando):
    assert H.clasificar(comando)[0] == "bloqueado", comando
