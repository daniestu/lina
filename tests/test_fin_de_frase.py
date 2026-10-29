# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V3a: el detector de fin de frase del atajo (con señales sintéticas: silencio, voz, pausas, el pitido de «te escucho», la espera sin voz) y la medida
`lina probar-voz silencio` (con un Whisper falso y grabaciones en tmp_path). Sin micrófono, sin GPU y sin tus grabaciones."""
import numpy as np
import pytest

from lina.nucleo import probar_silencio as PS
from lina.nucleo import probar_voz as PV
from lina.voz import fin_de_frase as FDF

F = FDF.FRECUENCIA


def silencio(s, nivel=0.002, semilla=0):
    return (np.random.default_rng(semilla).standard_normal(int(s * F)) * nivel).astype(np.float32)


def voz(s, nivel=0.1):
    t = np.arange(int(s * F)) / F
    return (np.sin(2 * np.pi * 220 * t) * nivel * np.sqrt(2)).astype(np.float32)


def pitido(s=0.15, frecuencia=880, nivel=0.3):
    t = np.arange(int(s * F)) / F
    return (np.sin(2 * np.pi * frecuencia * t) * nivel).astype(np.float32)


def termina(*trozos, **op):
    return FDF.donde_termina(np.concatenate(trozos), **op)


# ---------------------------------------------------------------- el detector
def test_corta_tras_el_silencio_pedido():
    fin, corte, espera = termina(silencio(0.5), voz(1.5), silencio(3), silencio_fin=1.0)
    assert fin == FDF.FIN and espera == pytest.approx(1.0, abs=0.04)
    assert corte / F == pytest.approx(0.5 + 1.5 + 1.0, abs=0.06)


def test_una_pausa_mas_corta_que_el_silencio_no_corta_la_frase():
    fin, corte, _ = termina(silencio(0.5), voz(1), silencio(0.7), voz(1), silencio(3), silencio_fin=1.0)
    assert fin == FDF.FIN and corte / F > 0.5 + 1 + 0.7 + 1             # corta después de la segunda parte
    fin, corte, _ = termina(silencio(0.5), voz(1), silencio(1.3), voz(1), silencio(3), silencio_fin=1.0)
    assert corte / F < 0.5 + 1 + 1.3                                    # con una pausa más larga, corta en la pausa


def test_el_pitido_del_principio_no_cuenta_como_voz():
    fin, _, _ = termina(pitido(), silencio(7), silencio_fin=1.0, espera_inicial=6.0)
    assert fin == FDF.NADA                                              # ni corta tras el pitido ni se lo toma por una frase
    fin, corte, _ = termina(pitido(), silencio(0.4), voz(1), silencio(3), silencio_fin=1.0)
    assert fin == FDF.FIN and corte / F > 0.15 + 0.4 + 1


def test_el_pitido_no_sube_el_ruido_de_fondo():
    d = FDF.FinDeFrase()
    for b in FDF.trocear(pitido(0.3, nivel=0.5)):
        d.alimentar(b)
    assert d.suelo == pytest.approx(0.003)


def test_sin_voz_a_tiempo_dice_nada():
    fin, corte, _ = termina(silencio(8), espera_inicial=2.0)
    assert fin == FDF.NADA and corte / F == pytest.approx(0.3 + 2.0, abs=0.06)


def test_un_golpe_corto_no_es_una_frase():
    fin, corte, _ = termina(silencio(0.5), voz(0.12, nivel=0.3), silencio(1.5), voz(1), silencio(3), silencio_fin=1.0)
    assert fin == FDF.FIN and corte / F > 0.5 + 0.12 + 1.5 + 1


def test_no_corta_por_longitud():
    fin, _, _ = termina(silencio(0.5), voz(40), silencio_fin=1.0)
    assert fin is None                                                  # un dictado largo con el atajo vale: se termina pulsando


def test_con_ruido_de_fondo_moderado_aprende_su_nivel():
    audio = silencio(10, nivel=0.008, semilla=1)                        # por debajo del umbral mínimo (0,012): lo aprende como fondo
    audio[int(1.5 * F):int(3 * F)] += voz(1.5, nivel=0.15)
    fin, corte, _ = FDF.donde_termina(audio, silencio_fin=1.0)
    assert fin == FDF.FIN and corte / F == pytest.approx(3 + 1.0, abs=0.15)


def test_limite_conocido_con_ruido_fuerte_desde_el_principio_nunca_corta():
    """Igual que el manos libres: si desde el primer instante el fondo pasa del umbral mínimo, lo toma por voz y no aprende el fondo, así que no oye el
    silencio. Con el atajo no es grave (se termina pulsando, como hoy), pero es lo que explica los «nunca corta» de la tanda con música (V3a)."""
    audio = silencio(10, nivel=0.02, semilla=1)
    audio[int(1.5 * F):int(3 * F)] += voz(1.5, nivel=0.15)
    assert FDF.donde_termina(audio, silencio_fin=1.0)[0] is None


# ---------------------------------------------------------------- la medida
def test_la_cola_es_el_ruido_de_fondo_de_la_grabacion():
    audio = np.concatenate([silencio(0.5, nivel=0.004), voz(1)])
    cola = PS.cola_de_fondo(audio, 2.0)
    assert len(cola) >= 2.0 * F
    assert float(np.sqrt(np.mean(cola * cola))) < 0.01                  # de los bloques bajos, no de la voz
    assert np.array_equal(cola, PS.cola_de_fondo(audio, 2.0))           # siempre la misma (semilla fija)


def test_medir_tanda_cuenta_cortes_y_solo_transcribe_lo_que_se_corta():
    entera = np.concatenate([silencio(0.5), voz(1), silencio(1.3), voz(1), silencio(0.2)])   # una pausa larga a media frase
    seguida = np.concatenate([silencio(0.5), voz(2), silencio(0.2)])
    oidos = []

    def transcribir(audio):
        oidos.append(len(audio))
        return "abre firefox" if len(audio) > 3 * F else "abre"
    res, ejemplos = PS.medir_tanda([("Abre Firefox", entera), ("Pon música", seguida)], transcribir, valores=(1.0, 1.5))
    assert res[1.0]["cortadas"] == 1 and res[1.0]["antes"] == 1 and ejemplos[0][:2] == (1.0, "Abre Firefox")
    assert res[1.5]["cortadas"] == 0 and res[1.5]["antes"] == 0         # con 1,5 s la pausa ya no corta
    assert all(r["frases"] == 2 and r["nunca"] == 0 and r["sin_voz"] == 0 for r in res.values())
    assert len(oidos) == 2                                              # la completa una vez y la cortada; lo que corta en la cola no se transcribe
    assert res[1.5]["frente_a_pulsar"][1] == pytest.approx(1.5 - 0.2, abs=0.06)


def test_una_orden_directa_que_se_entiende_igual_no_cuenta_como_cortada():
    assert PS.igual("Sube el volumen", "sube el volumen.")
    assert not PS.igual("Abre Firefox", "Abre")


def test_principal_con_grabaciones_falsas(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path)
    for i in range(3):
        PV.guardar_wav(tmp_path / f"frase{i + 1:02d}.wav", np.concatenate([silencio(0.4), voz(1), silencio(0.2)]))
    salida = []
    assert PS.principal(["1.0"], salida.append, cargar=lambda calculo: (lambda a, pista=None: "pon música", None)) == 0
    texto = "\n".join(salida)
    assert "cola sintética" in texto and "pitido" in texto and "1.0 s" in texto
    assert (tmp_path / PS.INFORME).exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["frase01.wav", "frase02.wav", "frase03.wav", PS.INFORME]   # no toca las grabaciones


def test_valores_fuera_de_rango_y_sin_grabaciones(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "CARPETA", tmp_path / "no-hay")
    salida = []
    assert PS.principal(["9"], salida.append) == 2
    assert PS.principal([], salida.append, cargar=lambda c: (lambda a, pista=None: "", None)) == 1 and "No hay grabaciones" in salida[-1]
