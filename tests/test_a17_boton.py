# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A17: activar Lina con un botón o una combinación de cualquier dispositivo que no sea un teclado. Todo con dispositivos simulados: un /sys falso
(nombre, fabricante, modelo y botones) y tuberías (FIFO) en lugar de /dev/input; nunca se abre un dispositivo de verdad."""
import os
import struct
import threading
import time
from pathlib import Path

import pytest

from lina.nucleo import boton as BOT

L3, R3, A, BTN_MODE = 317, 318, 304, 316
LETRAS_Y_ESPACIO = sorted(BOT.LETRAS) + [57]


def _mapa(codigos):
    """El mapa de bits como lo escribe el kernel en capabilities/key: palabras en hexadecimal, la más alta primero."""
    palabras = [0] * (max(codigos) // BOT.BITS + 1)
    for c in codigos:
        palabras[c // BOT.BITS] |= 1 << (c % BOT.BITS)
    return " ".join(f"{p:x}" for p in reversed(palabras))


@pytest.fixture
def sistema(tmp_path):
    """Un /sys y un /dev de prueba. `sistema.poner(n, nombre, fab, mod, codigos)` crea eventN con su FIFO."""
    sysfs, dev = tmp_path / "sys", tmp_path / "dev"
    sysfs.mkdir()
    dev.mkdir()

    class S:
        def poner(self, n, nombre, fab, mod, codigos):
            d = sysfs / f"event{n}" / "device"
            (d / "id").mkdir(parents=True)
            (d / "capabilities").mkdir()
            (d / "name").write_text(nombre + "\n")
            (d / "id" / "vendor").write_text(fab + "\n")
            (d / "id" / "product").write_text(mod + "\n")
            (d / "capabilities" / "key").write_text(_mapa(codigos) + "\n")
            os.mkfifo(dev / f"event{n}")
            return str(dev / f"event{n}")
    s = S()
    s.sysfs, s.dev = sysfs, dev
    s.mando = s.poner(3, "Mando de prueba", "1234", "abcd", [A, 305, 307, 308, 310, 311, 314, 315, BTN_MODE, L3, R3])
    s.teclado = s.poner(5, "Teclado de prueba", "0001", "0002", LETRAS_Y_ESPACIO)
    return s


def _pulsar(ruta, eventos, antes=0.15):
    """Escribe eventos de botón (y su SYN) en el FIFO del dispositivo, como haría el kernel."""
    time.sleep(antes)
    fd = os.open(ruta, os.O_WRONLY)
    for codigo, valor in eventos:
        os.write(fd, BOT.EVENTO.pack(0, 0, BOT.EV_KEY, codigo, valor) + BOT.EVENTO.pack(0, 0, 0, 0, 0))
        time.sleep(0.02)
    return fd


# ---------------------------------------------------------------- lo que se sabe sin abrir nada
def test_por_sys_se_distingue_un_mando_de_un_teclado_sin_abrirlos(sistema, monkeypatch):
    abiertos = []
    monkeypatch.setattr(BOT, "abrir", lambda ruta: abiertos.append(ruta))
    ds = {d["nombre"]: d for d in BOT.dispositivos(sistema.sysfs, sistema.dev)}
    assert ds["Mando de prueba"]["teclado"] is False and {L3, R3} <= ds["Mando de prueba"]["teclas"]
    assert ds["Teclado de prueba"]["teclado"] is True
    assert ds["Mando de prueba"]["fabricante"] == "1234" and ds["Mando de prueba"]["legible"] is True
    assert abiertos == []


def test_el_ajuste_va_y_vuelve_y_lo_que_no_tiene_su_forma_no_vale():
    texto = BOT.escribir_ajuste("1234", "abcd", "Mando: de prueba", [R3, L3])
    assert texto == "1234:abcd Mando  de prueba: 317+318"
    assert BOT.leer_ajuste(texto) == ("1234", "abcd", "Mando  de prueba", (L3, R3))
    for malo in ("", "lo que sea", "1234:abcd Mando: tecla", "1234:abcd Mando: 1+2+3+4+5"):
        assert BOT.leer_ajuste(malo) is None


def test_la_combinacion_se_dispara_una_vez_y_solo_mira_sus_botones():
    c = BOT.Combinacion([L3, R3])
    assert not c.ver(A, 1) and not c.ver(L3, 1) and not c.ver(L3, 2)
    assert c.ver(R3, 1) is True
    assert not c.ver(R3, 0) and not c.ver(R3, 1)                 # sin soltarlo todo, no se repite
    c.ver(L3, 0)
    c.ver(R3, 0)
    assert not c.ver(L3, 1) and c.ver(R3, 1) is True


# ---------------------------------------------------------------- Lina en marcha
def _vigilar(sistema, ajuste, al_pulsar, log):
    parar = threading.Event()
    hilo = threading.Thread(target=BOT.vigilar, args=(al_pulsar,), kwargs={"ajuste": ajuste, "log": log.append, "sysfs": sistema.sysfs,
                                                                           "dev": sistema.dev, "parar": parar, "vuelta": 0.05}, daemon=True)
    hilo.start()
    return parar, hilo


def test_lina_se_activa_con_la_combinacion_y_el_registro_no_dice_que_se_pulso(sistema):
    pulsado, log = [], []
    ajuste = BOT.escribir_ajuste("1234", "abcd", "Mando de prueba", [L3, R3])
    parar, hilo = _vigilar(sistema, lambda: ajuste, lambda: pulsado.append(1), log)
    fd = _pulsar(sistema.mando, [(A, 1), (A, 0), (L3, 1), (R3, 1), (R3, 0), (L3, 0), (L3, 1)])
    time.sleep(0.3)
    parar.set()
    hilo.join(2)
    os.close(fd)
    assert pulsado == [1]
    assert log.count("Botón de activación pulsado") == 1
    assert not any(str(A) in m or "317" in m or "318" in m for m in log)      # nunca qué se pulsó


def test_apagado_de_fabrica_no_abre_nada(sistema, monkeypatch):
    abiertos = []
    monkeypatch.setattr(BOT, "abrir", lambda ruta: abiertos.append(ruta) or os.open(ruta, os.O_RDONLY | os.O_NONBLOCK))
    parar, hilo = _vigilar(sistema, lambda: "", lambda: None, [])
    time.sleep(0.2)
    parar.set()
    hilo.join(2)
    assert abiertos == []


def test_nunca_abre_un_teclado_aunque_el_ajuste_lo_nombre(sistema, monkeypatch):
    abiertos, log = [], []
    monkeypatch.setattr(BOT, "abrir", lambda ruta: abiertos.append(ruta) or os.open(ruta, os.O_RDONLY | os.O_NONBLOCK))
    ajuste = BOT.escribir_ajuste("0001", "0002", "Teclado de prueba", [57])
    parar, hilo = _vigilar(sistema, lambda: ajuste, lambda: None, log)
    time.sleep(0.2)
    parar.set()
    hilo.join(2)
    assert abiertos == [] and "Botón de activación: teclado" in log


def test_sin_permiso_lo_dice_y_no_pide_nada(sistema):
    if os.geteuid() == 0:
        pytest.skip("como root todo se puede leer")
    os.chmod(sistema.mando, 0)
    ajuste = BOT.leer_ajuste(BOT.escribir_ajuste("1234", "abcd", "Mando de prueba", [L3, R3]))
    assert BOT.buscar(ajuste, sistema.sysfs, sistema.dev)[1] == "sin_permiso"
    texto = BOT.texto_estado("sin_permiso", ajuste)
    assert "no pide permisos" in texto and "input" not in texto and "sudo" not in texto


def test_no_conectado_y_sin_esos_botones(sistema):
    otro = BOT.leer_ajuste(BOT.escribir_ajuste("9999", "9999", "Otro mando", [L3]))
    assert BOT.buscar(otro, sistema.sysfs, sistema.dev)[1] == "no_conectado"
    raro = BOT.leer_ajuste(BOT.escribir_ajuste("1234", "abcd", "Mando de prueba", [999]))
    assert BOT.buscar(raro, sistema.sysfs, sistema.dev)[1] == "sin_boton"


def test_el_codigo_nunca_se_queda_el_dispositivo():
    """Ni EVIOCGRAB ni ioctl: el botón llega también al juego y el mando conserva la vibración."""
    fuente = Path(BOT.__file__).read_text(encoding="utf-8")
    assert "import fcntl" not in fuente and "ioctl(" not in fuente and "O_RDONLY" in fuente and "O_RDWR" not in fuente and "O_WRONLY" not in fuente


# ---------------------------------------------------------------- el asistente
def test_aprender_apunta_la_combinacion_sin_abrir_el_teclado(sistema, monkeypatch):
    abiertos = []
    real = BOT.abrir
    monkeypatch.setattr(BOT, "abrir", lambda ruta: abiertos.append(ruta) or real(ruta))
    salida = []
    fd = [None]
    hilo = threading.Thread(target=lambda: fd.__setitem__(0, _pulsar(sistema.mando, [(L3, 1), (R3, 1), (R3, 0), (L3, 0)], antes=0.3)))
    hilo.start()
    nuevo = BOT.aprender(salida.append, lambda pregunta: "s", sistema.sysfs, sistema.dev, espera=5)
    hilo.join()
    os.close(fd[0])
    assert nuevo == "1234:abcd Mando de prueba: 317+318"
    assert abiertos == [sistema.mando]
    assert any("BTN_THUMBL (L3) + BTN_THUMBR (R3)" in s for s in salida) and any("llegará también" in s for s in salida)


def test_aprender_sin_tu_si_no_cambia_nada(sistema):
    fd = [None]
    hilo = threading.Thread(target=lambda: fd.__setitem__(0, _pulsar(sistema.mando, [(A, 1), (A, 0)], antes=0.3)))
    hilo.start()
    assert BOT.aprender(lambda s: None, lambda pregunta: "n", sistema.sysfs, sistema.dev, espera=5) is None
    hilo.join()
    os.close(fd[0])


def test_aprender_sin_pulsar_nada(sistema):
    salida = []
    assert BOT.aprender(salida.append, lambda p: "s", sistema.sysfs, sistema.dev, espera=0.3) is None
    assert salida[-1] == "No he visto ningún botón. No cambio nada."


class Ajustes:
    def __init__(self):
        self.valores = {("activacion", "boton"): ""}

    def get(self, s, k):
        return self.valores[(s, k)]

    def establecer(self, s, k, v):
        self.valores[(s, k)] = v


def test_lina_boton_aprender_y_quitar(sistema, monkeypatch):
    aj = Ajustes()
    monkeypatch.setattr(BOT, "aprender", lambda *a, **k: "1234:abcd Mando de prueba: 317+318")
    assert BOT.principal(["aprender"], lambda s: None, ajustes=aj, sysfs=sistema.sysfs, dev=sistema.dev) == 0
    salida = []
    BOT.principal([], salida.append, ajustes=aj, sysfs=sistema.sysfs, dev=sistema.dev)
    assert "Conectado y se puede leer" in salida[0]
    BOT.principal(["quitar"], lambda s: None, ajustes=aj)
    assert aj.get("activacion", "boton") == ""


# ---------------------------------------------------------------- doctor e IA
def test_doctor_dice_como_esta_y_nada_si_esta_apagado():
    from test_doctor import Todo
    from lina.nucleo import doctor as D
    ajuste = BOT.leer_ajuste("1234:abcd Mando de prueba: 317+318")

    class ConBoton(Todo):
        def __init__(self, estado):
            self.e = estado

        def boton(self):
            return self.e
    filas = [f for f in D.comprobar(ConBoton(("listo", ajuste))) if f[1] == "Botón para activar a Lina"]
    assert filas and filas[0][0] == D.OK and "Conectado" in filas[0][2]
    filas = [f for f in D.comprobar(ConBoton(("teclado", ajuste))) if f[1] == "Botón para activar a Lina"]
    assert filas[0][0] == D.AVISO and filas[0][3] == "lina boton aprender"
    assert not [f for f in D.comprobar(ConBoton(("apagado", None))) if f[1] == "Botón para activar a Lina"]


def test_la_ia_no_puede_cambiar_el_boton():
    from lina.nucleo import autoconocimiento as AUT
    for clave in ("activacion.boton", "activacion.boton_home"):
        hecho, texto = AUT.cambiar(clave, "1234:abcd Mando: 304" if clave.endswith("boton") else "false")
        assert hecho is False and "solo el usuario" in texto
