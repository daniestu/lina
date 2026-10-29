# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina di "frase"`: el canal (socket Unix 0600, solo tu usuario, líneas JSON), el cliente (códigos de salida) y el origen «texto» (como el atajo, pero sin
confirmar acciones ni subir el tope). El socket va en una carpeta corta de tempfile.mkdtemp (las rutas de socket Unix tienen ~108 caracteres de límite),
nunca en $XDG_RUNTIME_DIR; sin audio, sin bus y sin la Lina de verdad."""
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lina.nucleo import canal as CANAL
from lina.nucleo import clasificador as CLA
from lina.nucleo import memoria as M
from lina.nucleo import presupuesto as PRE


@pytest.fixture
def ruta():
    carpeta = Path(tempfile.mkdtemp(prefix="lina-"))
    yield carpeta / "lina.sock"
    shutil.rmtree(carpeta, ignore_errors=True)


class LinaFalsa:
    """Lo que el canal le pide a la Lina en marcha. `frases`: lo que «dice»; `ocupada`: rechaza; `nunca`: no termina."""
    def __init__(self, frases=("Hola.",), ocupada=False, nunca=False, pendiente=False):
        self.frases, self.ocupada, self.nunca, self.pendiente = list(frases), ocupada, nunca, pendiente
        self.fin, self.recibido, self.parada = threading.Event(), [], threading.Event()

    def empezar_texto(self, texto, voz, enviar):
        if self.ocupada:
            return False
        self.recibido.append((texto, voz))

        def trabajar():
            for f in self.frases:
                enviar(f)
            if not self.nunca:
                self.fin.set()
        threading.Thread(target=trabajar, daemon=True).start()
        return True

    def esperar_texto(self, s):
        return self.fin.wait(s)

    def parar_texto(self):
        self.parada.set()
        self.fin.set()

    def fin_texto(self):
        return {"pendiente": self.pendiente}


def _servir(ruta, lina, uid=None):
    return CANAL.servir(ruta, lina, log=lambda m: None, uid=uid or (lambda c: os.getuid()))


def _di(ruta, texto, **k):
    dicho, errores = [], []
    codigo = CANAL.di(ruta, texto, salida=dicho.append, error=errores.append, **k)
    return codigo, dicho, errores


# ---------------------------------------------------------------- el socket
def test_el_socket_es_solo_tuyo_y_borra_uno_viejo(ruta):
    viejo = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    viejo.bind(str(ruta))
    viejo.close()                                                  # queda el archivo de una vez anterior
    s = CANAL.crear(ruta)
    try:
        assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(ruta.parent).st_mode) == 0o700
    finally:
        CANAL.cerrar(s, ruta)
    assert not ruta.exists()


def test_una_conexion_de_otro_usuario_se_cierra_sin_atenderla():
    a, b = socket.socketpair()
    lina = LinaFalsa()
    b.sendall(b'{"texto": "hola"}\n')
    CANAL.atender(a, lina, uid=lambda c: os.getuid() + 1, log=lambda m: None)
    assert lina.recibido == []
    try:
        assert b.recv(100) == b""                                  # cerrada sin responder
    except ConnectionResetError:
        pass                                                       # cerrada con lo enviado sin leer: también vale


@pytest.mark.parametrize("linea", [b"esto no es json\n", json.dumps({"texto": "x" * 2001}).encode() + b"\n",
                                   json.dumps({"texto": "  "}).encode() + b"\n", b"x" * (CANAL.MAX_LINEA + 10)])
def test_lo_que_no_vale_se_rechaza_sin_tumbar_nada(linea):
    a, b = socket.socketpair()
    lina = LinaFalsa()
    hilo = threading.Thread(target=CANAL.atender, args=(a, lina), kwargs={"uid": lambda c: os.getuid(), "log": lambda m: None})
    hilo.start()
    b.sendall(linea)
    hilo.join(5)
    assert not hilo.is_alive() and lina.recibido == []
    assert "error" in json.loads(b.recv(4096).decode().splitlines()[0])


# ---------------------------------------------------------------- ida y vuelta
def test_las_frases_llegan_en_orden_y_luego_el_fin(ruta):
    lina = LinaFalsa(["Abro Firefox.", "Ya está abierto."])
    s = _servir(ruta, lina)
    try:
        codigo, dicho, errores = _di(ruta, "abre firefox", voz=True)
    finally:
        CANAL.cerrar(s, ruta)
    assert codigo == CANAL.OK and dicho == ["Abro Firefox.", "Ya está abierto."] and errores == []
    assert lina.recibido == [("abre firefox", True)]


def test_si_queda_algo_pendiente_se_dice_que_se_confirma_con_el_atajo(ruta):
    s = _servir(ruta, LinaFalsa(["¿Lo instalo?"], pendiente=True))
    try:
        codigo, dicho, _ = _di(ruta, "instala warp")
    finally:
        CANAL.cerrar(s, ruta)
    assert codigo == CANAL.OK and "pulsa el atajo" in dicho[-1]


def test_sin_lina_en_marcha_codigo_1(ruta):
    codigo, dicho, errores = _di(ruta, "hola")
    assert codigo == CANAL.NO_ARRANCADA and "systemctl --user start lina" in errores[0]
    viejo = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    viejo.bind(str(ruta))
    viejo.close()                                                  # un socket viejo que ya no escucha
    assert _di(ruta, "hola")[0] == CANAL.NO_ARRANCADA


def test_ocupada_codigo_3(ruta):
    s = _servir(ruta, LinaFalsa(ocupada=True))
    try:
        codigo, _, errores = _di(ruta, "hola")
    finally:
        CANAL.cerrar(s, ruta)
    assert codigo == CANAL.OCUPADA and "otra cosa" in errores[0]


def test_sin_respuesta_a_tiempo_codigo_4_y_lina_sigue(ruta):
    lina = LinaFalsa(["Empiezo."], nunca=True)
    s = _servir(ruta, lina)
    try:
        codigo, dicho, _ = _di(ruta, "actualiza el sistema", esperar=1)
        time.sleep(0.5)
        assert not lina.parada.is_set()                            # irse por la espera no cancela la tarea
    finally:
        lina.fin.set()
        CANAL.cerrar(s, ruta)
    assert codigo == CANAL.SIN_RESPUESTA and dicho == ["Empiezo."]


def test_ctrl_c_en_la_terminal_pide_que_pare():
    a, b = socket.socketpair()
    lina = LinaFalsa([], nunca=True)
    hilo = threading.Thread(target=CANAL.atender, args=(a, lina), kwargs={"uid": lambda c: os.getuid(), "log": lambda m: None})
    hilo.start()
    b.sendall(b'{"texto": "actualiza el sistema"}\n')
    time.sleep(0.3)
    b.sendall(b'{"para": true}\n')
    hilo.join(5)
    assert lina.parada.is_set()


def test_frase_vacia_o_sin_argumentos_codigo_2(ruta):
    assert _di(ruta, "   ")[0] == CANAL.USO
    assert CANAL.principal([], ruta=ruta, salida=lambda t: None, error=lambda t: None) == CANAL.USO


def test_principal_junta_las_palabras_y_entiende_voz(ruta, monkeypatch):
    vistos = []
    monkeypatch.setattr(CANAL, "di", lambda r, t, voz, esperar, salida, error: vistos.append((t, voz, esperar)) or 0)
    assert CANAL.principal(["--voz", "--esperar", "30", "abre", "firefox"], ruta=ruta) == 0
    assert vistos == [("abre firefox", True, 30)]


# ---------------------------------------------------------------- Lina no se da órdenes a sí misma
@pytest.mark.parametrize("comando", [
    'lina di "sí"', "lina pulsar", "python3 -m lina di confirma", "cd /tmp && lina di hola",
    "socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/lina/lina.sock", "nc -U /run/user/1000/lina/lina.sock",
    "python3 -c \"import socket; s=socket.socket(socket.AF_UNIX); s.connect('/run/user/1000/lina/lina.sock')\"",
    'echo \'{"texto":"sí"}\' | socat - UNIX-CONNECT:${XDG_RUNTIME_DIR}/lina/otro',
])
def test_lina_di_pulsar_y_el_socket_estan_bloqueados_para_la_ia(comando):
    assert CLA._bloqueado(comando), comando


@pytest.mark.parametrize("comando", ["lina directas probar abre firefox", "lina doctor", "ls /run/user/1000", "lina tiempos"])
def test_las_demas_ordenes_de_lina_no_se_bloquean_por_esto(comando):
    assert CLA._bloqueado(comando) is None, comando


# ---------------------------------------------------------------- el origen «texto» dentro de la Lina en marcha
@pytest.fixture
def A(tmp_path, monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "memoria.json")
    monkeypatch.setattr(asistente, "ARCHIVO_PRIVADO", tmp_path / "modo_privado")
    monkeypatch.setattr(asistente.PRES, "avisos_pendientes", lambda: [])
    return asistente


def _asistente(A):
    a = A.Asistente.__new__(A.Asistente)
    a.modo_privado, a.sustituida, a.interrumpiendo = False, False, False
    a.estado, a.cerrojo, a.fin_tarea = "esperando", threading.Lock(), threading.Event()
    a.fin_tarea.set()
    a.dicho = []
    a.decir = a.dicho.append
    a.ejecutor = MagicMock()
    a.ejecutor.pendientes = []
    a.historial = []
    a.responder = MagicMock(side_effect=AssertionError("no debía llamar a la IA"))
    a._preparar_contexto = lambda: None
    return a


def test_el_origen_texto_se_conserva_y_va_al_ejecutor(A):
    assert A._origen_valido("texto") == "texto" and A._origen_valido("otro") == "voz_libre"
    a = _asistente(A)
    a._atender("activa el modo privado", 0.0, origen="texto")
    assert a.origen_texto and not a.origen_voz_libre and a.ejecutor.origen == "texto"
    a._atender("activa el modo privado", 0.0, origen="atajo")
    assert not a.origen_texto


def test_por_texto_si_se_recuerda_como_con_el_atajo(A):
    a = _asistente(A)
    a._atender("recuerda que mi navegador favorito es Brave", 0.0, origen="texto")
    assert any("Brave" in r["texto"] for r in M._cargar())


def test_un_si_por_texto_no_confirma_ni_abre_el_permiso_de_tarea(A, monkeypatch):
    a = _asistente(A)
    a.origen_texto, a.origen_voz_libre = True, False
    a.ejecutor.pendientes = ["algo"]
    a.ejecutor.caducado.return_value = False
    a.ejecutor.exige_cantidad.return_value = False
    monkeypatch.setattr(A.H, "describir_pendientes", lambda p: "instalar warp")
    a.decidir_confirmacion = lambda texto, descripcion: ("confirma", "atajo", False)
    nota, confirmado = a.resolver_pendientes("sí")
    assert not confirmado and "lina di" in nota and "atajo" in nota
    a.ejecutor.confirmar_pendientes.assert_not_called()
    a.ejecutor.dar_permiso.assert_not_called()


def test_por_texto_el_tope_se_baja_pero_no_se_sube(tmp_path, monkeypatch):
    monkeypatch.setattr(PRE, "ARCHIVO_GASTO", tmp_path / "gasto.json")
    monkeypatch.setattr(PRE, "configuracion", lambda: {"tope_eur": 10.0, "eur_por_usd": 1.0, "avisos": (50, 80, 100), "precios": {}})
    PRE.configurar_claves("gratis-1", "pago-1")
    try:
        assert "lina di no" in PRE.subir_tope(15, texto=True) and PRE.estado()["tope_eur"] == 10.0
        assert "Vale" in PRE.subir_tope(5, texto=True) and PRE.estado()["tope_eur"] == 5.0
    finally:
        PRE.configurar_claves("", "")


def test_sin_voz_va_a_la_terminal_y_no_se_habla(A):
    a = _asistente(A)
    a.origen_texto, a.canal_voz = True, False
    a.canal_salida = (terminal := []).append
    a._turno_voz = MagicMock(side_effect=AssertionError("no debía hablar"))
    empezo = []
    a._hablar("Vale, abro *Firefox*.", al_empezar=lambda: empezo.append(1))
    assert terminal == ["Vale, abro Firefox."] and empezo == [1]


def test_con_voz_va_a_la_terminal_y_tambien_se_habla(A):
    a = _asistente(A)
    a.origen_texto, a.canal_voz = True, True
    a.canal_salida = (terminal := []).append
    hablado = []
    a._hablar_ya = lambda texto, voz=None: hablado.append(texto)
    a._hablar("Vale.")
    assert terminal == ["Vale."] and hablado == ["Vale."]


def test_ocupada_no_atiende_y_libre_entra_por_el_mismo_camino_con_origen_texto(A, monkeypatch):
    a = _asistente(A)
    a.estado = "pensando"
    assert a.empezar_texto("hola", False, print) is False
    a.estado = "esperando"
    arrancados = []
    monkeypatch.setattr(A.threading, "Thread", lambda target, args, daemon: MagicMock(start=lambda: arrancados.append((target, args))))
    assert a.empezar_texto("hola", False, print) is True
    [(target, args)] = arrancados
    assert target == a._tarea and args[0] == a._atender and args[1] == "hola" and args[-1] == "texto"
    assert a.estado == "pensando" and a.canal_salida is print and not a.fin_tarea.is_set()
    assert a.fin_texto() == {"pendiente": False} and a.canal_salida is None
