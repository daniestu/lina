# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Un «sí» vale para toda la tarea: tras confirmar una instalación, los reintentos (otro nombre, otra fuente, actualizar el sistema) y activar su servicio ya
no vuelven a preguntar. Discos, arranque, cuentas, dinero, código libre con sudo y lo descargado siguen preguntando; tras leer algo de fuera solo pasa lo que
nombra lo mismo; el permiso caduca, se retira con otra petición y no existe en modo prudente. Con el HOME aislado del conftest; nada se ejecuta de verdad."""
import copy
import time

import pytest

from lina.nucleo import herramientas as H
from lina.nucleo import plataforma as PL

INSTALAR = "sudo paru -S --noconfirm cloudflare-warp"


@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor(confirmar=True)
    e.ejecutados, e.dicho = [], []
    e.avisar = e.dicho.append
    monkeypatch.setattr(e, "_con_red", lambda comando, motivo, clase: e.ejecutados.append((comando, clase)) or "código de salida: 0\nhecho")
    monkeypatch.setattr(H, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(H, "recordar_confiables", lambda nombres: [])       # confirmar un paquete del AUR lo apuntaría como de confianza
    monkeypatch.setattr(H, "_aur_todo_confiable", lambda base, args: False)
    return e


def _confirmar(e, comando=INSTALAR):
    assert e.herramienta({"comando": comando, "motivo": "instalar WARP"}).startswith("PREPARADO")
    e.confirmar_pendientes()


def _pide_confirmacion(e, comando):
    return e.herramienta({"comando": comando, "motivo": "paso"}).startswith("PREPARADO")


def test_sin_permiso_cada_intento_pregunta(ej):
    assert _pide_confirmacion(ej, INSTALAR)
    assert ej.permiso is None


def test_un_si_cubre_los_reintentos_y_el_servicio_de_lo_instalado(ej):
    _confirmar(ej)
    assert ej.permiso and ej.permiso["secciones"] == {"software_de_fuera"}
    for comando in ("sudo paru -S --noconfirm cloudflare-warp-bin", "sudo paru -Syu --noconfirm", "sudo systemctl enable --now warp-svc",
                    "sudo paru -S spotify"):                         # sin haber leído nada de fuera, otro paquete de fuera es la misma clase de paso
        assert not _pide_confirmacion(ej, comando), comando
    assert [c for c, _ in ej.ejecutados][1:] == ["sudo paru -S --noconfirm cloudflare-warp-bin", "sudo paru -Syu --noconfirm",
                                                 "sudo systemctl enable --now warp-svc", "sudo paru -S spotify"]
    assert not ej.pendientes
    assert any("actualizar todo el sistema" in d for d in ej.dicho)


def test_el_servicio_de_otra_cosa_sigue_preguntando(ej):
    _confirmar(ej)
    assert _pide_confirmacion(ej, "sudo systemctl enable --now sshd-ajeno")


@pytest.mark.parametrize("comando", [
    "sudo modprobe nft_reject nft_reject_inet",                      # arranque / kernel
    "sudo pacman -S linux-headers",
    "sudo mount /dev/sdb1 /mnt",                                     # discos
    "sudo ssh-keygen -t ed25519 -f /root/clave",                     # cuentas y credenciales
    "sudo python3 -c 'print(1)'",                                    # código libre con sudo
    "sudo pacman -U ~/Descargas/warp.pkg.tar.zst",                   # paquete suelto
    "~/Descargas/instalar-warp.run",                                 # ejecutar lo descargado
    "sudo paru -S warp && sudo mount /dev/sdb1 /mnt",                # un trozo de lo que siempre se pregunta basta
])
def test_lo_que_se_confirma_siempre_sigue_preguntando(ej, monkeypatch, comando):
    monkeypatch.setattr(H, "modulos_del_kernel_presentes", lambda: True)
    _confirmar(ej)
    assert _pide_confirmacion(ej, comando)


def test_confirmar_algo_de_lo_que_siempre_se_pregunta_no_da_permiso(ej):
    _confirmar(ej, "sudo mount /dev/sdb1 /mnt")
    assert ej.permiso is None
    assert _pide_confirmacion(ej, "sudo mount /dev/sdb2 /mnt")


def test_tras_leer_algo_de_fuera_solo_pasa_lo_de_la_tarea(ej):
    _confirmar(ej)
    ej.contaminar("búsqueda en internet")
    assert ej.permiso["web"]
    assert not _pide_confirmacion(ej, "sudo paru -S --noconfirm cloudflare-warp-bin")
    assert not _pide_confirmacion(ej, "sudo paru -Syu --noconfirm")
    assert _pide_confirmacion(ej, "sudo paru -S spotify")


def test_lo_preparado_tras_leer_la_web_ya_viene_marcado(ej):
    ej.contaminar("búsqueda en internet")
    _confirmar(ej)
    ej.nueva_tarea()                                                 # el «sí» llega en otra frase: la tarea nueva empieza limpia, el permiso no
    assert ej.permiso["web"] and not ej.contaminado
    assert _pide_confirmacion(ej, "sudo paru -S spotify")


def test_el_permiso_caduca_y_se_retira(ej, monkeypatch):
    monkeypatch.setattr(H, "modulos_del_kernel_presentes", lambda: True)
    _confirmar(ej)
    ej.permiso["hasta"] = time.time() - 1
    assert _pide_confirmacion(ej, "sudo paru -S cloudflare-warp-bin")
    ej.cancelar()
    _confirmar(ej)
    ej.retirar_permiso()
    assert _pide_confirmacion(ej, "sudo paru -S cloudflare-warp-bin")
    ej.cancelar()
    _confirmar(ej)
    ej.herramienta({"comando": "sudo modprobe nft_reject", "motivo": "túnel"})   # queda pendiente (arranque)…
    ej.cancelar(rechazar=True)                                       # …y decirle que NO también retira el permiso
    assert ej.permiso is None


def test_en_modo_prudente_no_hay_permiso(ej, monkeypatch):
    prudente = copy.deepcopy(H._politica())
    prudente["modo"] = "prudente"
    monkeypatch.setattr(H, "_politica", lambda: prudente)
    _confirmar(ej)
    assert ej.permiso is None
    assert _pide_confirmacion(ej, "sudo paru -S cloudflare-warp-bin")


def test_con_contrasena_un_si_vale_para_los_siguientes(ej, monkeypatch):
    monkeypatch.setattr(H.PRIV, "pide_contrasena", lambda comando, paquetes: comando.startswith("sudo"))
    _confirmar(ej, "sudo systemctl restart warp-svc")
    assert ej.permiso["secciones"] == {"contrasena"}
    assert not _pide_confirmacion(ej, "sudo systemctl restart warp-svc --no-block")
    assert _pide_confirmacion(ej, "sudo mount /dev/sdb1 /mnt")


def test_lo_cubierto_no_se_apunta_como_paquete_de_confianza(ej, monkeypatch):
    apuntados = []
    monkeypatch.setattr(H, "recordar_confiables", lambda nombres: apuntados.extend(nombres) or [])
    _confirmar(ej)
    ej.herramienta({"comando": "sudo paru -S cloudflare-warp-bin", "motivo": "otro nombre"})
    assert "cloudflare-warp-bin" not in apuntados


def test_cargar_modulos_con_el_kernel_cambiado_no_se_prepara(ej, monkeypatch, tmp_path):
    (tmp_path / "7.9.0-otro").mkdir()
    monkeypatch.setattr(H, "DIR_MODULOS", tmp_path)
    assert not H.modulos_del_kernel_presentes()
    r = ej.herramienta({"comando": "sudo modprobe nft_reject", "motivo": "túnel"})
    assert r == H.AVISO_KERNEL_CAMBIADO and not ej.pendientes
    assert _pide_confirmacion(ej, "sudo modprobe -r nft_reject")    # quitar uno sí se puede (y se pregunta, como siempre)


def test_modulos_presentes_si_esta_el_del_kernel_en_marcha(monkeypatch, tmp_path):
    (tmp_path / H.platform.release()).mkdir()
    monkeypatch.setattr(H, "DIR_MODULOS", tmp_path)
    assert H.modulos_del_kernel_presentes()
    monkeypatch.setattr(H, "DIR_MODULOS", tmp_path / "no-existe")     # un sistema sin esa carpeta: no se sabe, no se avisa
    assert H.modulos_del_kernel_presentes()


def test_un_comando_que_cambia_el_kernel_avisa(monkeypatch):
    estados = iter([True, False])
    monkeypatch.setattr(H, "modulos_del_kernel_presentes", lambda: next(estados))
    r = H.Ejecutor(confirmar=True).ejecutar("true", "actualizar")
    assert "se ha actualizado el kernel" in r


@pytest.mark.parametrize("comando,todo", [
    ("sudo pacman -Sy -u --noconfirm cloudflare-warp-bin", True), ("sudo pacman -Syu", True), ("yay -S -u", True),
    ("sudo pacman -S foo", False), ("pacman -Qu", False), ("paru -Ss warp", False), ("sudo pacman -S --needed foo", False),
])
def test_actualizacion_completa_con_letras_sueltas(comando, todo):
    assert PL.es_actualizacion_completa(comando) is todo


def test_objetivo_de():
    assert H.objetivo_de("sudo paru -S --noconfirm cloudflare-warp-bin") == {"cloudflare", "warp"}
    assert H.objetivo_de("sudo systemctl enable --now warp-svc") == {"warp"}
    assert H.objetivo_de("sudo paru -Syu --noconfirm") == set()


def test_el_asistente_le_dice_a_la_ia_que_siga_sin_preguntar(ej, monkeypatch):
    import sys
    from unittest.mock import MagicMock
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor, a.historial, a.origen_voz_libre = ej, [], False
    a.decidir_confirmacion = lambda texto, descripcion: ("confirma", "atajo", False)
    ej.herramienta({"comando": INSTALAR, "motivo": "instalar WARP"})
    nota, confirmado = a.resolver_pendientes("sí")
    assert confirmado and "TODA la tarea" in nota and ej.permiso
    ej.herramienta({"comando": "sudo mount /dev/sdb1 /mnt", "motivo": "montar"})
    nota, confirmado = a.resolver_pendientes("sí")
    assert confirmado and "TODA la tarea" not in nota and ej.permiso is None     # lo de discos no deja permiso
