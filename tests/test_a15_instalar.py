# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A15: instalar por voz. Caso real (2026-11-20): paru no pudo bajar python-click (404, lista de paquetes desactualizada) y Lina solo dijo «ha fallado».
El motivo lo saca el código de la salida (en inglés: las instalaciones van con LC_ALL=C), la salida queda en el registro salvo en modo privado, la
propuesta de actualizar solo se hace con «sí» por el atajo, la confirmación del AUR dice qué más trae y paru va sin preguntas. Sin red ni sistema reales."""
import sys
from unittest.mock import MagicMock

import pytest

from lina.nucleo import aur as AUR
from lina.nucleo import fallos_instalacion as FI
from lina.nucleo import herramientas as H

PARU_404 = """:: Resolving dependencies...
:: Calculating conflicts...
Repo (12) ninja-1.13.1-1  python-click-8.5.0-1  python-tqdm-4.67.1-2  meson-1.9.1-1 ...
AUR (2)   caffeine-ng-4.2.0-3  python-ewmh-0.1.6-6
:: Proceed with installation? [Y/n]
:: Retrieving packages...
error: failed retrieving file 'python-click-8.5.0-1-any.pkg.tar.zst' from mirror.example.org : The requested URL returned error: 404
error: failed retrieving file 'python-click-8.5.0-1-any.pkg.tar.zst' from archlinux.example.net : The requested URL returned error: 404
warning: failed to retrieve some files
error: failed to commit transaction (failed to retrieve some files)
Errors occurred, no packages were upgraded.
error: installing repo packages
"""
PACMAN_ES = "error: no se pudo obtener el archivo «python-filelock-4.0.1-1-any.pkg.tar.zst» desde espejo.ejemplo : The requested URL returned error: 404\n"
APT_404 = ("Err:1 http://archive.ubuntu.com/ubuntu noble-updates/main amd64 vlc-bin amd64 3.0.20-3build6\n  404  Not Found [IP: 192.0.2.1 80]\n"
           "E: Failed to fetch http://archive.ubuntu.com/ubuntu/pool/main/v/vlc/vlc-bin_3.0.20-3build6_amd64.deb  404  Not Found\n"
           "E: Unable to fetch some archives, maybe run apt-get update or try with --fix-missing?\n")


# ---------------------------------------------------------------- (a) el motivo, por la salida
@pytest.mark.parametrize("salida, clave, paquete", [
    (PARU_404, "desactualizada", "python-click 8.5.0-1"),
    (PACMAN_ES, "desactualizada", "python-filelock 4.0.1-1"),
    (APT_404, "desactualizada", "vlc-bin 3.0.20-3build6"),
    ("error: target not found: caffeine-ng\n", "no_existe", "caffeine-ng"),
    ("E: Unable to locate package caffeine\n", "no_existe", "caffeine"),
    ("No match for argument: caffeine\nError: Unable to find a match: caffeine\n", "no_existe", "caffeine"),
    ("error: failed to init transaction (unable to lock database)\nerror: could not lock database: File exists\n", "bloqueada", ""),
    ("E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 1234 (apt)\n", "bloqueada", ""),
    ("error: Partition /var too full: 51234 blocks needed, 1024 blocks free\nerror: not enough free disk space\n", "espacio", ""),
    ("error: failed to commit transaction (conflicting files)\nfoo: /usr/bin/foo exists in filesystem\n", "conflicto", ""),
    ("error: failed to prepare transaction (could not satisfy dependencies)\n:: unable to satisfy dependency 'libx>=2' required by foo\n",
     "dependencias", ""),
    ("error: python-click: signature from \"Dev <dev@example.org>\" is unknown trust\n:: File is corrupted (invalid or corrupted package (PGP signature)).\n",
     "firma", ""),
    ("==> ERROR: A failure occurred in build().\n    Aborting...\nerror: failed to build 'caffeine-ng-4.2.0-3':\n", "compilacion", "'caffeine-ng-4.2.0-3':"),
])
def test_reconoce_cada_fallo_por_la_salida(salida, clave, paquete):
    hallado = FI.motivo(salida)
    assert hallado and hallado[0] == clave
    if clave in ("desactualizada", "no_existe"):
        assert hallado[2] == paquete


def test_lo_que_no_reconoce_no_lo_adivina():
    assert FI.motivo("algo raro ha pasado\n") is None


@pytest.mark.parametrize("comando, gestor", [
    ("paru -S --needed --noconfirm --skipreview caffeine-ng", "paru"), ("yay -S foo", "yay"), ("sudo pacman -S --noconfirm vlc", "pacman"),
    ("sudo apt-get install -y vlc", "apt-get"), ("sudo dnf install vlc", "dnf"), ("sudo zypper in vlc", "zypper"), ("flatpak install -y flathub x", "flatpak"),
    ("sudo pacman -Syu --noconfirm && paru -S caffeine-ng", "pacman"),
    ("pacman -Ss caffeine", None), ("paru -Si caffeine-ng", None), ("apt search vlc", None), ("ls", None),
])
def test_sabe_que_ordenes_son_instalaciones(comando, gestor):
    assert FI.gestor(comando) == gestor


def test_el_ayudante_de_root_cuenta_como_el_gestor_del_sistema(monkeypatch):
    from lina.nucleo import plataforma as PL
    monkeypatch.setattr(PL, "familia_actual", lambda: "arch")
    assert FI.gestor("sudo -n /usr/lib/lina/lina-instalar instalar vlc") == "pacman"


def test_actualizar_es_siempre_completo():
    for g in ("pacman", "paru", "yay"):
        assert FI.orden_de_actualizar(g) == "sudo pacman -Syu --noconfirm"
    assert FI.orden_de_actualizar("apt-get") == "sudo apt-get update" and FI.orden_de_actualizar("flatpak") is None


def test_las_instalaciones_van_en_ingles():
    entorno = H.Ejecutor._entorno(instalacion=True)
    assert entorno["LC_ALL"] == "C" and "LANGUAGE" not in entorno
    assert H.Ejecutor._entorno()["LC_ALL"] == "C.UTF-8"


# ---------------------------------------------------------------- (a), (b) y (c) al fallar
@pytest.fixture
def ej(monkeypatch):
    anotado = []
    monkeypatch.setattr(H, "anotar", anotado.append)
    monkeypatch.setattr(H, "notificar", lambda *a: None)
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    e.anotado = anotado
    return e


def _proc(salida, rc=1):
    p = MagicMock()
    p.communicate.return_value = (salida, None)
    p.returncode = rc
    return p


def test_en_segundo_plano_dice_el_motivo_y_propone_actualizar(ej, monkeypatch):
    lanzar = MagicMock()
    monkeypatch.setattr(H.subprocess, "Popen", lanzar)
    ej._vigilar(_proc(PARU_404), "paru -S --needed --noconfirm --skipreview caffeine-ng", "instalar Caffeine desde el AUR")
    dicho = ej.avisar.call_args[0][0]
    assert dicho.startswith("Ha fallado instalar Caffeine desde el AUR: no se ha podido descargar python-click 8.5.0-1")
    assert "lista de paquetes del sistema está desactualizada" in dicho and "¿Actualizo el sistema" in dicho and "atajo" in dicho
    [p] = ej.pendientes
    assert p["comando"] == "sudo pacman -Syu --noconfirm && paru -S --needed --noconfirm --skipreview caffeine-ng" and "funcion" not in p
    lanzar.assert_not_called()                                     # nada se ejecuta solo
    cola = [a for a in ej.anotado if a.startswith("[salida-del-fallo]")]
    assert cola and "python-click-8.5.0-1-any.pkg.tar.zst" in cola[0]


def test_en_modo_privado_no_se_guarda_la_salida(ej):
    ej.en_privado = lambda: True
    ej._vigilar(_proc(PARU_404), "paru -S caffeine-ng", "instalar Caffeine")
    assert not any(a.startswith("[salida-del-fallo]") for a in ej.anotado) and "python-click" in ej.avisar.call_args[0][0]


def test_la_salida_guardada_es_solo_la_cola(ej):
    ej._vigilar(_proc("\n".join(f"línea {i}" for i in range(500)) + "\nerror: target not found: x"), "sudo pacman -S x", "instalar x")
    [cola] = [a for a in ej.anotado if a.startswith("[salida-del-fallo]")]
    assert "línea 0\n" not in cola and "línea 499" in cola and len(cola) < FI.MAX_COLA + 400


def test_otras_ordenes_que_fallan_no_guardan_su_salida(ej):
    ej._vigilar(_proc("token=secreto\nerror"), "./mi-script.sh", "ejecutar mi script")
    assert not any(a.startswith("[salida-del-fallo]") for a in ej.anotado)
    assert ej.avisar.call_args[0][0].startswith("Ha fallado una tarea: ejecutar mi script.") and not ej.pendientes


def test_un_paquete_que_no_existe_no_propone_actualizar(ej):
    ej._vigilar(_proc("error: target not found: caffeine-ng\n"), "sudo pacman -S caffeine-ng", "instalar Caffeine")
    assert ej.avisar.call_args[0][0] == "Ha fallado instalar Caffeine: caffeine-ng no está en los repositorios." and not ej.pendientes


def test_lo_que_no_reconoce_lo_resume_la_ia_o_dice_lo_de_siempre(ej):
    ej.explicar_fallo = MagicMock(return_value="el servidor de paquetes ha cortado la conexión")
    ej._vigilar(_proc("algo raro\n"), "sudo pacman -S vlc", "instalar VLC")
    assert ej.avisar.call_args[0][0] == "Ha fallado instalar VLC: el servidor de paquetes ha cortado la conexión."
    ej.explicar_fallo = MagicMock(return_value=None)
    ej._vigilar(_proc("algo raro\n"), "sudo pacman -S vlc", "instalar VLC")
    assert ej.avisar.call_args[0][0].startswith("Ha fallado una tarea: instalar VLC.")


def test_al_momento_la_ia_recibe_el_motivo_y_la_propuesta(ej, monkeypatch):
    monkeypatch.setattr(H.subprocess, "Popen", lambda *a, **k: _proc(PARU_404))
    monkeypatch.setattr(H, "modulos_del_kernel_presentes", lambda: True)
    r = ej.ejecutar("paru -S --needed --noconfirm --skipreview caffeine-ng", "instalar Caffeine")
    assert "POR QUÉ HA FALLADO" in r and "python-click 8.5.0-1" in r and "PREPARADO actualizar el sistema" in r
    assert ej.pendientes[0]["comando"].startswith("sudo pacman -Syu --noconfirm && ")


@pytest.fixture
def lina(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[{"comando": "sudo pacman -Syu --noconfirm && paru -S caffeine-ng", "motivo": "actualizar", "razon": "x"}])
    a.ejecutor.caducado.return_value = False
    a.ejecutor.exige_cantidad.return_value = False
    a.historial, a.origen_voz_libre, a.origen_texto = [], False, False
    return a


@pytest.mark.parametrize("origen", ["origen_voz_libre", "origen_texto"])
def test_la_propuesta_de_actualizar_no_se_confirma_por_manos_libres_ni_por_lina_di(lina, origen):
    setattr(lina, origen, True)
    lina.resolver_pendientes("Sí.")
    lina.ejecutor.confirmar_pendientes.assert_not_called()


def test_con_el_atajo_si_se_confirma(lina):
    lina.ejecutor.confirmar_pendientes.return_value = "$ sudo pacman -Syu…\ncódigo de salida: 0"
    lina.resolver_pendientes("Sí.")
    lina.ejecutor.confirmar_pendientes.assert_called_once()


# ---------------------------------------------------------------- (d) y (e): el AUR
class Http:
    """El AUR simulado: caffeine-ng trae python-ewmh del AUR y python-click de los repositorios; «python-xlib-virtual» lo dan tres paquetes."""
    INFO = {"caffeine-ng": {"Name": "caffeine-ng", "Depends": ["python-click>=8", "python-ewmh", "python-xlib-virtual"], "MakeDepends": ["meson"]},
            "python-ewmh": {"Name": "python-ewmh", "Depends": ["python-xlib"]}}
    DAN = [{"Name": "xlib-a", "NumVotes": 3}, {"Name": "xlib-b", "NumVotes": 40}, {"Name": "xlib-c", "NumVotes": 7}]

    def __init__(self):
        self.pedidas = []

    def get(self, url, params=None, timeout=None):
        self.pedidas.append((url, params))
        r = MagicMock()
        if url.endswith("/info"):
            r.json.return_value = {"results": [self.INFO[n] for n in params["arg[]"] if n in self.INFO]}
        else:
            r.json.return_value = {"results": self.DAN if "python-xlib-virtual" in url else []}
        return r


REPOS = {"python-click", "meson", "python-xlib"}


def test_dice_lo_que_trae_del_aur_y_el_proveedor_que_usara():
    http = Http()
    trae = AUR.que_trae(["caffeine-ng"], http=http, en_repos=lambda d: d in REPOS)
    assert trae == {"aur": ["python-ewmh", "xlib-b"], "elegidos": {"python-xlib-virtual": ("xlib-b", 3)}, "error": ""}
    assert AUR.frase(trae) == ("Trae también del AUR: python-ewmh, xlib-b. Para python-xlib-virtual hay 3 paquetes que lo dan; usaré xlib-b, "
                               "el más votado.")
    assert all("aur.archlinux.org" in u for u, _ in http.pedidas)


def test_sin_dependencias_del_aur_no_dice_nada_y_sin_red_lo_dice():
    trae = AUR.que_trae(["python-ewmh"], http=Http(), en_repos=lambda d: True)
    assert trae["aur"] == [] and AUR.frase(trae) == ""
    roto = MagicMock()
    roto.get.side_effect = OSError("sin red")
    assert AUR.frase(AUR.que_trae(["caffeine-ng"], http=roto)) == "No he podido mirar en el AUR qué más trae."


@pytest.mark.parametrize("comando, esperado", [
    ("paru -S --noconfirm --needed caffeine-ng", "paru -S --skipreview --noconfirm --needed caffeine-ng"),
    ("paru -S caffeine-ng", "paru -S --needed --noconfirm --skipreview caffeine-ng"),
    ("yay -S caffeine-ng", "yay -S --needed --noconfirm --answerdiff None --answerclean None --answeredit None caffeine-ng"),
    ("paru -Ss caffeine", "paru -Ss caffeine"),
    ("sudo pacman -S vlc", "sudo pacman -S vlc"),
])
def test_paru_y_yay_van_sin_preguntas(comando, esperado):
    assert AUR.sin_preguntas(comando) == esperado


def test_el_proveedor_elegido_va_en_la_orden():
    trae = {"aur": ["xlib-b"], "elegidos": {"python-xlib-virtual": ("xlib-b", 3)}, "error": ""}
    assert AUR.sin_preguntas("paru -S caffeine-ng", trae).endswith("caffeine-ng xlib-b")


def test_la_confirmacion_del_aur_lleva_lo_que_trae(ej, monkeypatch):
    monkeypatch.setattr(AUR, "que_trae", lambda p: {"aur": ["python-ewmh"], "elegidos": {}, "error": ""})
    monkeypatch.setattr(H, "clasificar", lambda c: ("critico", "instala software de fuera de las fuentes de confianza"))
    r = ej.herramienta({"comando": "paru -S --noconfirm --needed caffeine-ng", "motivo": "instalar Caffeine desde el AUR"})
    assert "Trae también del AUR: python-ewmh." in r and r.startswith(H.MENSAJE_PREPARADO)
    [p] = ej.pendientes
    assert p["comando"] == "paru -S --skipreview --noconfirm --needed caffeine-ng" and p["aviso_aur"] == "Trae también del AUR: python-ewmh."


def test_si_la_ia_no_lo_dice_lo_anade_el_codigo(lina):
    lina.ejecutor.pendientes = [{"comando": "paru -S caffeine-ng", "aviso_aur": "Trae también del AUR: python-ewmh."}]
    assert lina._con_lo_que_trae_el_aur("Voy a instalar Caffeine desde el AUR, ¿lo hago?").endswith("Trae también del AUR: python-ewmh.")
    dicho = "Voy a instalar Caffeine desde el AUR, que trae también python-ewmh. ¿Lo hago?"
    assert lina._con_lo_que_trae_el_aur(dicho) == dicho
