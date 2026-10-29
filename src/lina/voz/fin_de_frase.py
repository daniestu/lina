# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fin de frase por silencio para el atajo (V3): una pulsación en vez de dos.

Es el mismo detector por volumen que usa el manos libres (`manos_libres.Segmentador`: umbral que se adapta al ruido de fondo, 3 bloques fuertes para
empezar, y la voz sigue mientras el volumen no baje del 70 % del umbral), con tres diferencias pensadas para el atajo:
  · ignora los primeros 300 ms, donde suena el pitido de «te escucho» (no cuenta como voz ni sube el ruido de fondo);
  · no corta por longitud: un dictado largo con el atajo es válido, y siempre puedes terminarlo pulsando;
  · si en `espera_inicial` segundos no oye voz, lo dice («nada»), para no quedarse grabando para siempre.
No graba ni toca el micrófono: se le dan bloques y dice cuándo terminar. Así se puede medir con grabaciones (lina probar-voz silencio).
"""
import numpy as np

FRECUENCIA = 16000
BLOQUE = 480                       # 30 ms, como el manos libres
SEG_BLOQUE = BLOQUE / FRECUENCIA

FIN, NADA = "fin", "nada"


class FinDeFrase:
    def __init__(self, silencio_fin=1.2, umbral_min=0.012, ignorar_inicio=0.3, espera_inicial=6.0, min_voz=0.25):
        self.umbral_min = umbral_min
        self.bloques_silencio = max(1, round(silencio_fin / SEG_BLOQUE))
        self.bloques_ignorados = max(0, round(ignorar_inicio / SEG_BLOQUE))
        self.bloques_espera = max(1, round(espera_inicial / SEG_BLOQUE))
        self.min_voz = max(1, round(min_voz / SEG_BLOQUE))
        self.suelo = 0.003
        self.n = 0                     # bloques recibidos
        self.ultimo_con_voz = None     # índice del último bloque con voz de la frase en curso
        self._fuera_de_voz()

    def _fuera_de_voz(self):
        self.en_voz = False
        self.fuertes = 0
        self.silencio = 0
        self.voz = 0

    @property
    def umbral(self):
        return max(self.umbral_min, self.suelo * 3.0)

    def alimentar(self, bloque):
        """Un bloque de audio (float32). Devuelve FIN cuando has terminado de hablar, NADA si no has dicho nada a tiempo, o None mientras tanto."""
        b = np.asarray(bloque, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(b * b))) if len(b) else 0.0
        self.n += 1
        if self.n <= self.bloques_ignorados:           # el pitido de «te escucho»
            return None
        if not self.en_voz:
            if rms >= self.umbral:
                self.fuertes += 1
                if self.fuertes >= 3:
                    self.en_voz, self.voz, self.silencio = True, self.fuertes, 0
                    self.ultimo_con_voz = self.n
            else:
                self.suelo = 0.98 * self.suelo + 0.02 * rms
                self.fuertes = 0
            if not self.en_voz and self.ultimo_con_voz is None and self.n >= self.bloques_ignorados + self.bloques_espera:
                return NADA
            return None
        if rms >= self.umbral * 0.7:
            self.silencio = 0
            self.voz += 1
            self.ultimo_con_voz = self.n
        else:
            self.silencio += 1
        if self.silencio >= self.bloques_silencio:
            if self.voz >= self.min_voz:
                return FIN
            self._fuera_de_voz()                       # un golpe o un ruido corto: no era una frase, sigue escuchando
            self.ultimo_con_voz = None
        return None

    def espera(self):
        """Segundos desde el último bloque con voz hasta ahora (lo que se ha esperado al silencio)."""
        return 0.0 if self.ultimo_con_voz is None else (self.n - self.ultimo_con_voz) * SEG_BLOQUE


def trocear(audio):
    """El audio en bloques de 30 ms (el último, si queda corto, se descarta como hace el micrófono)."""
    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    return [a[i:i + BLOQUE] for i in range(0, len(a) - BLOQUE + 1, BLOQUE)]


def donde_termina(audio, **opciones):
    """(resultado, muestra donde corta, espera en s) al pasar una grabación por el detector. Resultado None si nunca termina."""
    d = FinDeFrase(**opciones)
    for i, b in enumerate(trocear(audio)):
        r = d.alimentar(b)
        if r:
            return r, (i + 1) * BLOQUE, d.espera()
    return None, len(audio), d.espera()
