# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina memoria medir [--mios]` (A1, paso 1): ¿qué recuerdos vienen al caso con cada regla de palabras, y cuánto se dejaría sin cubrir?

Hoy un recuerdo cuenta si comparte UNA raíz (`memoria._raices`) con la petición, y eso además desactiva las órdenes directas y las recetas. Aquí se
comparan cuatro reglas sobre una tanda escrita a mano (recuerdos y peticiones inventados, sin nada personal), sin IA ni red y sin cambiar nada:
aciertos, falsos positivos, recuerdos que se pierden, órdenes directas desactivadas sin motivo y cuántos casos no comparten NINGUNA raíz (lo único que
arreglarían unos embeddings). La tanda sirve para comparar las reglas entre sí, no para dimensionar los embeddings.

`--mios` pasa TUS recuerdos por las mismas peticiones y solo da números (ni un texto): cuántas peticiones tocarían algún recuerdo y cuántas órdenes
directas desactivaría cada regla. Solo lee memoria.json; no escribe nada.
"""
import math
import time

from lina.nucleo import directas as DIR
from lina.nucleo import memoria as MEM
from lina.nucleo.idioma import N_, T

# ----- la tanda (inventada): recuerdos y, por petición, cuáles vienen al caso
RECUERDOS = {
    "navegador": "mi navegador favorito es Brave",
    "futbol": "el fútbol lo veo en Movistar Plus",
    "noche": "por la noche prefiero la música baja",
    "jazz": "me gusta el jazz para concentrarme",
    "series": "las series las veo en Netflix con subtítulos en inglés",
    "proton": "para jugar uso Proton experimental en Steam",
    "editor": "mi editor de código es VS Code",
    "capturas": "las capturas de pantalla guárdalas en la carpeta Imágenes",
    "impresora": "mi impresora es la del despacho, no la del salón",
    "apagar": "cuando diga apaga, quiero suspender, no apagar del todo",
    "trabajo": "los documentos de trabajo van en la carpeta Proyectos",
    "auriculares": "el volumen de los auriculares lo prefiero al 40 %",
    "banco": "Firefox lo uso solo para el banco",
    "noticias": "las noticias, mejor en la radio que en vídeo",
    "juego": "mi juego favorito es Hollow Knight",
}

CASOS = [
    # vienen al caso
    ("ponme el partido de esta noche", {"futbol"}),
    ("¿dónde veo el fútbol hoy?", {"futbol"}),
    ("ponme el resumen de la jornada", {"futbol"}),
    ("ponme el Clásico", {"futbol"}),
    ("abre el navegador", {"navegador"}),
    ("busca recetas en el navegador", {"navegador"}),
    ("abre algo para navegar por internet", {"navegador"}),
    ("ponme una serie", {"series"}),
    ("ponme el último capítulo de la serie que veía", {"series"}),
    ("quiero ver una película", {"series"}),
    ("pon los subtítulos", {"series"}),
    ("ponme algo para ver esta noche", {"series"}),
    ("lanza el juego con Proton", {"proton"}),
    ("instala un juego nuevo de Steam", {"proton"}),
    ("el juego va lento", {"proton"}),
    ("configura el mando para jugar", {"proton"}),
    ("juega a algo", {"juego", "proton"}),
    ("¿cómo se llama mi juego favorito?", {"juego"}),
    ("abre mi juego favorito", {"juego"}),
    ("abre el editor de código", {"editor"}),
    ("abre mi editor", {"editor"}),
    ("necesito escribir código", {"editor"}),
    ("vamos a programar un rato", {"editor"}),
    ("haz una captura de pantalla", {"capturas"}),
    ("guarda una captura", {"capturas"}),
    ("haz un pantallazo", {"capturas"}),
    ("manda esto a la impresora", {"impresora"}),
    ("imprime este documento", {"impresora"}),
    ("imprime la foto", {"impresora"}),
    ("apaga el ordenador", {"apagar"}),
    ("apaga el equipo", {"apagar"}),
    ("guarda el informe en mi carpeta de trabajo", {"trabajo"}),
    ("crea un documento nuevo para el trabajo", {"trabajo"}),
    ("baja el volumen de los auriculares", {"auriculares"}),
    ("entra en mi banco", {"banco"}),
    ("entra en la web del banco", {"banco"}),
    ("ponme las noticias", {"noticias"}),
    ("lee las noticias de hoy", {"noticias"}),
    ("ponme el telediario", {"noticias"}),
    ("¿qué ha pasado hoy en el mundo?", {"noticias"}),
    ("pon música para trabajar", {"jazz"}),
    ("pon algo de jazz", {"jazz"}),
    ("quiero escuchar algo mientras estudio", {"jazz"}),
    ("pon música tranquila, que ya es de noche", {"noche"}),
    # no vienen al caso (muchas comparten una palabra con algún recuerdo)
    ("abre Steam", set()),
    ("abre Firefox", set()),
    ("abre Brave", set()),
    ("abre Netflix", set()),
    ("abre VS Code", set()),
    ("pon Hollow Knight", set()),
    ("abre el juego de cartas", set()),
    ("sube el volumen", set()),
    ("pausa la música", set()),
    ("siguiente canción", set()),
    ("conecta los auriculares bluetooth", set()),
    ("apaga la pantalla", set()),
    ("apaga la luz del salón", set()),
    ("pon la radio", set()),
    ("abre la carpeta de descargas", set()),
    ("abre la carpeta Imágenes", set()),
    ("traduce esto al inglés", set()),
    ("busca en internet cómo hacer pan", set()),
    ("programa un recordatorio para mañana", set()),
    ("¿qué hora es?", set()),
    ("sube el brillo", set()),
    ("abre la calculadora", set()),
    ("cierra todas las ventanas", set()),
    ("pon el modo oscuro", set()),
    ("¿cuánto espacio queda en el disco?", set()),
    ("silencia el ordenador", set()),
    ("¿qué tiempo hace mañana?", set()),
    ("busca vuelos baratos", set()),
    ("escribe un correo de felicitación", set()),
    ("suspende el equipo", set()),
]


# ----- las reglas: k = raíces en común, n = raíces de la petición
def _mitad(k, n):
    return k >= max(1, math.ceil(n / 2))


REGLAS = [
    (N_("1 palabra (la de hoy)"), lambda k, n: k >= 1),
    (N_("2 palabras o más"), lambda k, n: k >= 2),
    (N_("la mitad de la petición"), _mitad),
    (N_("mixta (1 si la petición es corta)"), lambda k, n: k >= (1 if n <= 2 else 2)),
]


def _comunes(peticion, raices_recuerdos):
    """(raíces de la petición, {recuerdo: raíces en común})."""
    p = MEM._raices(peticion)
    return p, {r: len(p & raices) for r, raices in raices_recuerdos.items()}


def medir(recuerdos=None, casos=None, directa=DIR.entender):
    """Por regla: aciertos, falsos, perdidos, directas desactivadas sin motivo, directas que ignoran una preferencia y µs por petición. Además, cuántos
    pares que vienen al caso no comparten ninguna raíz (el techo de los embeddings)."""
    recuerdos = RECUERDOS if recuerdos is None else recuerdos
    casos = CASOS if casos is None else casos
    raices = {r: MEM._raices(t) for r, t in recuerdos.items()}
    es_directa = {p: bool(directa(p)) for p, _ in casos}
    resultado = {"relevantes": sum(len(e) for _, e in casos), "sin_raices": 0, "reglas": []}
    for p, esperados in casos:
        _, k = _comunes(p, raices)
        resultado["sin_raices"] += sum(1 for r in esperados if k[r] == 0)
    for nombre, regla in REGLAS:
        r = {"regla": nombre, "aciertos": 0, "falsos": 0, "perdidos": 0, "directas_perdidas": 0, "directas_sin_preferencia": 0}
        t0 = time.perf_counter()
        for p, esperados in casos:
            n, k = _comunes(p, {x: MEM._raices(t) for x, t in recuerdos.items()})     # como relevantes(): las raíces de cada recuerdo, cada vez
            elegidos = {x for x in recuerdos if regla(k[x], len(n))}
            r["aciertos"] += len(elegidos & esperados)
            r["falsos"] += len(elegidos - esperados)
            r["perdidos"] += len(esperados - elegidos)
            if es_directa[p] and elegidos and not esperados:
                r["directas_perdidas"] += 1                  # una orden directa que se hace con la IA sin motivo
            if es_directa[p] and esperados and not elegidos:
                r["directas_sin_preferencia"] += 1           # la directa se hace sin mirar la preferencia que sí venía al caso
        r["us"] = (time.perf_counter() - t0) / max(1, len(casos)) * 1e6
        resultado["reglas"].append(r)
    resultado["directas"] = sum(es_directa.values())
    return resultado


def medir_mios(textos, casos=None, directa=DIR.entender):
    """Con TUS recuerdos (solo sus textos, que no salen de aquí): números y nada más."""
    casos = CASOS if casos is None else casos
    raices = {i: MEM._raices(t) for i, t in enumerate(textos)}
    es_directa = {p: bool(directa(p)) for p, _ in casos}
    resultado = {"recuerdos": len(textos), "raices_media": (sum(len(r) for r in raices.values()) / len(raices)) if raices else 0.0,
                 "cortos": sum(1 for r in raices.values() if len(r) <= 2), "peticiones": len(casos), "directas": sum(es_directa.values()), "reglas": []}
    alcanzados = set()
    for nombre, regla in REGLAS:
        tocadas = desactivadas = 0
        for p, _ in casos:
            n, k = _comunes(p, raices)
            elegidos = {x for x in raices if regla(k[x], len(n))}
            if nombre == REGLAS[0][0]:
                alcanzados |= elegidos
            if elegidos:
                tocadas += 1
                desactivadas += es_directa[p]
        resultado["reglas"].append({"regla": nombre, "tocadas": tocadas, "directas_desactivadas": desactivadas})
    resultado["sin_alcance"] = len(raices) - len(alcanzados)
    return resultado


# ----- lina memoria medir
def _tabla(filas, salida):
    anchos = [max(len(str(f[i])) for f in filas) for i in range(len(filas[0]))]
    for f in filas:
        salida("  " + "  ".join(str(c).ljust(anchos[i]) if i == 0 else str(c).rjust(anchos[i]) for i, c in enumerate(f)))


def principal(argv, salida=print, cargar=None):
    if argv not in ([], ["--mios"]):
        salida(T("Uso:  lina memoria medir   |   lina memoria medir --mios"))
        return 2
    if argv == ["--mios"]:
        textos = [r["texto"] for r in (cargar or MEM._cargar)() if isinstance(r, dict) and isinstance(r.get("texto"), str)]
        if not textos:
            salida(T("No hay nada apuntado: no hay nada que medir con tus recuerdos."))
            return 0
        m = medir_mios(textos)
        salida(T("Tus recuerdos: {n} (de media {r:.1f} raíces cada uno; {c} con 2 o menos). Solo números: no se muestra ningún texto.",
                 n=m["recuerdos"], r=m["raices_media"], c=m["cortos"]))
        salida(T("Peticiones de la tanda: {p}, de ellas {d} órdenes directas.", p=m["peticiones"], d=m["directas"]))
        filas = [(T("regla"), T("peticiones que tocan algún recuerdo"), T("directas desactivadas"))]
        filas += [(T(r["regla"]), r["tocadas"], r["directas_desactivadas"]) for r in m["reglas"]]
        _tabla(filas, salida)
        salida(T("Recuerdos tuyos que ninguna petición de la tanda alcanza ni con 1 palabra: {s} de {n}.", s=m["sin_alcance"], n=m["recuerdos"]))
        return 0
    m = medir()
    salida(T("Tanda inventada: {r} recuerdos, {p} peticiones ({d} órdenes directas), {v} pares que vienen al caso.",
             r=len(RECUERDOS), p=len(CASOS), d=m["directas"], v=m["relevantes"]))
    filas = [(T("regla"), T("aciertos"), T("falsos"), T("perdidos"), T("directas perdidas"), T("directas sin preferencia"), "µs")]
    filas += [(T(r["regla"]), r["aciertos"], r["falsos"], r["perdidos"], r["directas_perdidas"], r["directas_sin_preferencia"], f"{r['us']:.0f}")
              for r in m["reglas"]]
    _tabla(filas, salida)
    salida(T("Pares que vienen al caso sin ninguna palabra en común (solo por significado): {s} de {v} ({pc:.0f} %). Es el techo de lo que añadirían unos embeddings.",
             s=m["sin_raices"], v=m["relevantes"], pc=100 * m["sin_raices"] / max(1, m["relevantes"])))
    return 0
