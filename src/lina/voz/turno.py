# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Turno de voz: Lina habla de una en una, en el orden en que se pidió.

Varios hilos quieren hablar a la vez (la respuesta, los avisos de «lo pienso a fondo», lo que contesta mientras trabaja, los avisos de segundo plano).
Sin turno se pisaban: dos voces a la vez, un audio sobrescrito por otro y, peor, la caché de voz guardando una frase con el audio de otra. Con el turno,
cada frase espera a que termine la anterior. «Cállate» descarta además lo que estaba esperando en ese momento (la «generación» cambia), y nadie espera
para siempre: tras un tope, la frase se salta.
"""
import threading
import time

TURNO, TOPE, DESCARTADA, CADUCADA = "turno", "tope", "descartada", "caducada"


class TurnoDeVoz:
    def __init__(self, reloj=time.monotonic):
        self._c = threading.Condition()
        self._cola = []                 # quienes esperan, en orden de llegada
        self._hablando = False
        self._generacion = 0
        self._reloj = reloj

    def pedir(self, espera_max, vigente=None):
        """Espera el turno. → TURNO (hay que llamar a soltar() al terminar), TOPE (se esperó demasiado), DESCARTADA (alguien mandó callar mientras
        esperaba) o CADUCADA (al llegarle el turno, `vigente()` dijo que ya no tiene sentido decirlo)."""
        with self._c:
            yo = object()
            generacion = self._generacion
            self._cola.append(yo)
            limite = self._reloj() + espera_max
            try:
                while self._hablando or self._cola[0] is not yo:
                    if self._generacion != generacion:
                        return DESCARTADA
                    restante = limite - self._reloj()
                    if restante <= 0:
                        return TOPE
                    self._c.wait(min(restante, 0.5))
                if self._generacion != generacion:
                    return DESCARTADA
                if vigente is not None and not vigente():
                    return CADUCADA
                self._hablando = True
                return TURNO
            finally:
                self._cola.remove(yo)
                self._c.notify_all()

    def soltar(self):
        with self._c:
            self._hablando = False
            self._c.notify_all()

    def callar(self):
        """Lo que estaba esperando turno ya no se dice (lo que suena lo corta quien llama, parando el reproductor)."""
        with self._c:
            self._generacion += 1
            self._c.notify_all()
