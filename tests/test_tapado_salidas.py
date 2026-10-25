# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Lo que imprime un comando se le da a la IA sin claves (fase 17, S4): se tapan las que tienen forma de clave y el valor de las variables de entorno con
nombre de secreto. Lo normal (hashes de git, rutas largas, listados, configuración de KDE) llega igual. Con el HOME aislado del conftest."""
import pytest

from lina.nucleo import claves as CL
from lina.nucleo import herramientas as H

T = CL.TAPADA
FALSA_GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0" * 2
FALSA_GOOGLE = "AI" + "za" + "Sy" + "x" * 33


def test_env_tapa_las_variables_con_nombre_de_secreto_y_deja_lo_demas():
    salida = "\n".join(["GITHUB_TOKEN=abc123", "OPENAI_API_KEY=algo", "DB_PASSWORD=patata", "AWS_SECRET_ACCESS_KEY=xyz", "NPM_AUTH=1",
                        "MI_CREDENTIAL=z", "PATH=/usr/local/bin:/usr/bin", "HOME=/casa", "LANG=es_ES.UTF-8", "XDG_SESSION_TYPE=wayland", "VACIA_TOKEN="])
    limpia = CL.limpiar_para_ia(salida).split("\n")
    assert limpia[:6] == [f"GITHUB_TOKEN={T}", f"OPENAI_API_KEY={T}", f"DB_PASSWORD={T}", f"AWS_SECRET_ACCESS_KEY={T}", f"NPM_AUTH={T}", f"MI_CREDENTIAL={T}"]
    assert limpia[6:] == ["PATH=/usr/local/bin:/usr/bin", "HOME=/casa", "LANG=es_ES.UTF-8", "XDG_SESSION_TYPE=wayland", "VACIA_TOKEN="]


def test_export_y_declare_tambien():
    assert CL.limpiar_para_ia('declare -x GH_TOKEN="abc"') == f"declare -x GH_TOKEN={T}"
    assert CL.limpiar_para_ia("export NPM_TOKEN=abc") == f"export NPM_TOKEN={T}"
    assert CL.limpiar_para_ia('declare -x EDITOR="kate"') == 'declare -x EDITOR="kate"'


def test_tapa_de_mas_a_proposito():
    """Va por trozos del nombre: KEYMAP o GIT_AUTHOR_NAME se tapan aunque sean inofensivas (está escrito en docs/seguridad.md)."""
    assert CL.limpiar_para_ia("KEYMAP=es") == f"KEYMAP={T}"
    assert CL.limpiar_para_ia("GIT_AUTHOR_NAME=Alguien") == f"GIT_AUTHOR_NAME={T}"


def test_claves_con_forma_de_clave_en_cualquier_salida():
    limpia = CL.limpiar_para_ia(f"remote: usando {FALSA_GH}\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz012345\nkey={FALSA_GOOGLE}")
    assert FALSA_GH not in limpia and FALSA_GOOGLE not in limpia and "abcdefghijklmnopqrstuvwxyz012345" not in limpia
    assert limpia.count(T) == 3


@pytest.mark.parametrize("salida", [
    "a21ad9b las pruebas ya no tocan tu carpeta personal\n29c811e el modelo local de reserva\nc9c68be un alias no puede cambiar",
    "commit 61ccf13f0a9e2b7c4d5e6f708192a3b4c5d6e7f8\nAuthor: Alguien <alguien@example.com>\nDate:   Sun Oct 25 10:00:00 2026 +0200",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  archivo.iso",
    "/home/usuario/.local/share/Steam/steamapps/compatdata/1493710/pfx/drive_c/users/steamuser/AppData/Local/Juego/Saved/Config/Windows/Engine.ini",
    "total 12\ndrwxr-xr-x 1 usuario usuario   0 oct 25 08:59 .\n-rw-r--r-- 1 usuario usuario 412 oct 24 23:56 KEYS.md\n-rw------- 1 usuario usuario 9 oct 25 01:14 token_de_prueba.txt",
    "S.fichero     Tamaño Usados  Disp Uso% Montado en\n/dev/nvme0n1p2   931G   402G  527G  44% /",
    "nvme0n1     259:0    0 931,5G  0 disk\n└─nvme0n1p2 259:2    0 931G  0 part  /  UUID=6f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f",
    "[Shortcuts]\nShortcutKey=Meta+X\nKeyboardLayout=es\nPasswordField=oculto",
    "linux 6.17.3-1\npython-requests 2.32.5-1\nfaster-whisper 1.2.0",
    '{"keyboard": "es", "token_count": 1234, "auth": "oauth"}',
])
def test_lo_normal_llega_igual(salida):
    assert CL.limpiar_para_ia(salida) == salida


def test_el_ejecutor_lo_aplica_a_lo_que_devuelve_un_comando():
    ej = H.Ejecutor(confirmar=True)
    r = ej.ejecutar("printf 'GITHUB_TOKEN=abc123\\nPATH=/usr/bin\\n'", "prueba")
    assert f"GITHUB_TOKEN={T}" in r and "abc123" not in r and "PATH=/usr/bin" in r
