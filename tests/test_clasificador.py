# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""La clasificación de comandos (nucleo/clasificador.py y clasificar() de herramientas.py)."""
from lina.nucleo import herramientas as H


def test_abrir_un_programa_conocido_con_un_enlace_se_clasifica_como_lanzar():
    # Antes de la fase 6 una segunda función con el mismo nombre tapaba a la buena y esta clase nunca se alcanzaba.
    assert H.clasificar("firefox https://example.com")[0] == "lanzar"
    assert H.clasificar("xdg-open https://example.com")[0] == "lanzar"


def test_lanzar_no_se_cuela_con_argumentos_raros():
    assert H.clasificar("firefox https://example.com; rm -rf ~")[0] != "lanzar"
    assert H.clasificar("firefox --no-remote https://example.com")[0] != "lanzar"
    assert H.clasificar("programa-que-no-existe-xyz https://example.com")[0] != "lanzar"


def test_el_motivo_de_abrir_se_reconoce_sin_acentos():
    assert H._motivo_es_abrir("Abrir Firefox")
    assert H._motivo_es_abrir("lanza steam")
    assert not H._motivo_es_abrir("limpiar la caché")


# ---------------------------------------------------------------- las cookies del navegador son credenciales (bloqueo duro)
import pytest  # noqa: E402


@pytest.mark.parametrize("comando", [
    'yt-dlp --cookies-from-browser firefox "ytsearch1:Jaleo La Fuga" --get-url 2>&1 | head -n 20',             # lo que hizo la IA (registro real)
    'mkdir -p ~/.config/yt-dlp && echo "--cookies-from-browser firefox" > ~/.config/yt-dlp/config',             # y lo dejó permanente
    "yt-dlp --cookies-from-browser chrome https://www.youtube.com/watch?v=x",
    "gallery-dl --cookies-from-browser firefox https://example.com/album",
    "mpv --ytdl-raw-options=cookies-from-browser=firefox https://www.youtube.com/watch?v=x",
    "python3 -c \"import yt_dlp; yt_dlp.YoutubeDL({'cookiesfrombrowser': ('firefox',)})\"",
    "python3 -c 'import browser_cookie3; print(browser_cookie3.firefox())'",
])
def test_leer_las_cookies_del_navegador_por_otro_programa_esta_bloqueado(comando):
    clase, motivo = H.clasificar(comando)
    assert clase == "bloqueado" and "credenciales" in motivo, comando


@pytest.mark.parametrize("comando", ['yt-dlp "ytsearch1:Jaleo La Fuga" --print title', "yt-dlp --cookies ~/Descargas/cookies-youtube.txt https://www.youtube.com/watch?v=x"])
def test_yt_dlp_sin_cookies_del_navegador_no_se_bloquea(comando):
    assert H.clasificar(comando)[0] != "bloqueado", comando
