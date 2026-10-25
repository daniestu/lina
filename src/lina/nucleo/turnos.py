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


# Órdenes que piden HACER algo en el equipo (no una respuesta): con ellas, informar no es cumplir.
_ACCION_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:pon|ponme|ponlo|ponla|ponmelo|ponmela|abre|abreme|reproduce|reproduceme|"
                        r"enciende|apaga|cierra|lanza|inicia|arranca|instala|descarga|activa|desactiva|conecta|desconecta|quiero ver|dejame ver)\b")
_ACCION_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|open|turn on|turn off|start|launch|install|download|enable|disable|"
                        r"connect|disconnect|i want to watch|let me watch)\b")
# Herramientas que solo informan (buscan, leen, miran): no hacen nada en el equipo.
HERRAMIENTAS_DE_INFORMAR = HERRAMIENTAS_META | {"buscar_web", "leer_web", "buscar_youtube", "mirar_pantalla", "ver_pantalla", "buscar_ajuste_kde",
                                                "buscar_clave_en_binarios", "observar_config", "ver_diario", "ver_recetas", "ver_juegos", "ver_gasto",
                                                "mis_ajustes", "ver_papelera", "usar_receta"}


def pide_accion(texto):
    """¿La frase pide hacer algo («ponme el partido», «abre Steam») y no solo saber algo («¿a qué hora es el partido?»)?"""
    from lina.nucleo import idioma as IDI
    t = C.normalizar(texto)
    return bool((_ACCION_EN if IDI.actual() == "en" else _ACCION_ES).match(t))


def solo_se_informo(acciones, es_lectura):
    """True si en la petición solo se buscó, leyó o miró (ningún comando que cambie o abra algo). `es_lectura(comando)` dice si un comando solo lee."""
    if not acciones:
        return True
    for nombre, args, _ in acciones:
        if nombre in HERRAMIENTAS_DE_INFORMAR:
            continue
        if nombre == "ejecutar_comando" and es_lectura(str((args or {}).get("comando", ""))):
            continue
        return False
    return True


# Órdenes de PONER algo para verlo u oírlo: abrir solo la portada de la plataforma no es ponerlo.
_CONTENIDO_ES = re.compile(r"^(?:(?:oye|vale|venga|por favor|puedes|me puedes|podrias)\s+)*(?:pon|ponme|ponlo|ponla|ponmelo|ponmela|reproduce|reproduceme|"
                           r"quiero ver|dejame ver)\b")
_CONTENIDO_EN = re.compile(r"^(?:(?:hey|ok|please|can you|could you)\s+)*(?:put on|put|play|i want to watch|let me watch)\b")
_URL = re.compile(r"https?://[^\s'\"]+")


def pide_contenido(texto):
    """¿Pide que le PONGAS algo (un partido, una serie, un vídeo), y no solo abrir un programa o una web?"""
    from lina.nucleo import idioma as IDI
    return bool((_CONTENIDO_EN if IDI.actual() == "en" else _CONTENIDO_ES).match(C.normalizar(texto)))


def solo_portadas(acciones, es_lectura):
    """La portada que se abrió (p. ej. «www.movistarplus.es») si, aparte de buscar y leer, lo único que se hizo fue abrir portadas de webs (sin ruta ni
    parámetros); None si se abrió una página concreta, se hizo otra cosa o no se abrió nada."""
    from urllib.parse import urlparse
    portada = None
    for nombre, args, _ in acciones or []:
        if nombre in HERRAMIENTAS_DE_INFORMAR:
            continue
        comando = str((args or {}).get("comando", "")) if nombre == "ejecutar_comando" else ""
        if nombre == "ejecutar_comando" and es_lectura(comando):
            continue
        urls = _URL.findall(comando)
        if not urls or len(comando.split()) > 1 + len(urls):
            return None
        for u in urls:
            p = urlparse(u)
            if p.path not in ("", "/") or p.query or p.fragment:
                return None
            portada = p.netloc
    return portada
