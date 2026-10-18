# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Decisiones sobre cómo cerrar una petición: qué cuenta como trabajo real, y con qué frase se describe lo que se aprende.

Son funciones puras (sin audio ni red) para poder probarlas solas.
"""
import re

from lina.nucleo import comandos as C

# Herramientas que solo preparan el trabajo (cargar más herramientas, pensar a fondo): por sí solas no hacen ni comprueban nada en el equipo.
HERRAMIENTAS_META = {"mas_herramientas", "pensar_a_fondo"}


def solo_herramientas_meta(acciones):
    """True si en la petición solo se llamó a herramientas «meta»: se cargó material pero no se hizo ni se leyó nada del equipo."""
    return bool(acciones) and all(a[0] in HERRAMIENTAS_META for a in acciones)


_SEGUIMIENTO = re.compile(r"^(?:no|nada|sigue|todavia|aun|eso|otra vez|ahora|gracias|vale|has|ya|si|pero|perfecto|bien|genial)\b")


def es_seguimiento(texto):
    """¿Es una frase corta que reacciona a lo anterior («No lo has hecho», «Ahora sí, gracias») y no una petición nueva?"""
    t = C.normalizar(texto)
    return len(t.split()) <= 8 and bool(_SEGUIMIENTO.match(t))


def peticion_de_receta(historial, actual):
    """La petición que describe de verdad lo que se apunta en una receta: si lo último que dijiste es un seguimiento o una queja, la anterior."""
    if not es_seguimiento(actual):
        return actual
    for h in reversed(historial or []):
        if h.get("rol") == "user" and not es_seguimiento(h.get("texto", "")):
            return h["texto"]
    return actual
