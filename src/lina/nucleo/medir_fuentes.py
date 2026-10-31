# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina fuentes medir [--lanzar]` (A11): ¿el modelo ligero elegiría bien la fuente por significado? Se mide ANTES de activar `usar_fuente`.

Pasa una tanda escrita a mano por el modelo rápido con las instrucciones y herramientas de verdad, más `usar_fuente` con dos fuentes de ejemplo, y mira solo su primer turno: no ejecuta
ninguna herramienta, no busca, no lee ninguna web y no toca tus fuentes. Va siempre con la clave gratuita. Sin --lanzar no llama a la IA: solo dice qué haría y resume lo que haya medido.

Dos errores: no usarla cuando debía (leve) y usarla cuando no debía o con el id equivocado (grave). El criterio de la fila A11 se escribió antes de medir. Los casos «gris» son ambiguos de
verdad: se miden y se enseñan aparte, pero no cuentan en el criterio. El progreso se guarda: si se acaba el cupo, se continúa después."""
import json
import time

from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import N_, T

ARCHIVO = RUT.ESTADO / "medida_fuentes.jsonl"
REPETICIONES = 3                   # el modelo no siempre responde igual
PAUSA_SEG = 4.0                    # para no chocar con el límite por minuto de la clave gratuita
JUEGO = "No Man's Sky"
MAX_GRAVE = 0.02                   # criterio de A11, escrito antes de medir
MAX_NO_LA_USA = 0.10
FUENTES = [{"id": "f1", "tema": "recetas de refinería de No Man's Sky"}, {"id": "f2", "tema": "recetas de pociones de The Witcher 3"}]

GRUPOS = {
    "A": (N_("dice receta o refinería"), "f1", [
        "¿Cuál es la receta de refinería del cromo?", "Dame la receta de refinería del carbono condensado.", "¿Qué receta de refinería da oro?",
        "Receta de refinería para sacar ferrita pura.", "¿Qué recetas hay en la refinería de No Man's Sky?", "¿Cómo uso la refinería para sacar sodio?",
        "Dime recetas de refinería con oxígeno.", "¿Qué metes en la refinería para conseguir cobalto?", "Recetas de refinería para conseguir nanitos.",
        "¿Qué receta de refinería usa ferrita y carbono?"]),
    "B": (N_("solo por significado"), "f1", [
        "¿Cómo refino el ferrito?", "¿Qué sale si refino ferrita?", "¿Cómo convierto ferrita en ferrita pura?", "¿Cómo saco carbono condensado del carbono?",
        "¿Qué pasa si mezclo ferrita y oxígeno?", "¿Cómo paso cobre a metal cromático?", "¿Con qué combino el sodio para sacar más?", "¿Cómo obtengo oro a partir de otros materiales?",
        "¿Cómo multiplico el oxígeno?", "Quiero sacar más carbono del que tengo, ¿cómo?", "¿Cómo purifico la ferrita?", "¿Qué hago para concentrar el carbono?",
        "¿Cómo transformo el uranio en otra cosa?", "¿Para qué sirve meter silicato en la refinería portátil?", "¿Puedo sacar cobalto iónico del cobalto?",
        "¿Cuánta ferrita pura sale de cien de ferrita?", "¿Qué combinaciones de minerales dan más beneficio al refinar?"]),
    "W": (N_("como lo podría oír Whisper"), "f1", [
        "¿Cómo refi no el ferrito?", "¿Cómo refino el ferrico?", "¿Qué sale si refino ferita?", "¿Cómo saco carbono con densado del carbono?", "¿Qué receta de refi nería da cromo?"]),
    "C": (N_("mismo juego, otro tema"), None, [
        "¿Cómo gano dinero fácil en No Man's Sky?", "¿Cómo consigo nanitos rápido?", "¿Dónde consigo ferrito?", "¿Dónde encuentro oro?", "¿Cómo mejoro la nave?",
        "¿Cómo consigo un carguero gratis?", "¿Cuál es el mejor multiherramienta?", "¿Cómo construyo una base?", "¿Cómo domestico animales?", "¿Qué hago contra los centinelas?",
        "¿Cómo llego al centro de la galaxia?", "¿Cómo fabrico un hipermotor?", "¿Qué planos necesito para el exotraje?", "Dame una receta de cocina con el procesador de nutrientes.",
        "¿Qué recetas de cocina dan más dinero?", "¿Dónde vendo la ferrita pura?", "¿Cómo construyo una refinería en mi base?", "¿Cuál es la última actualización de No Man's Sky?",
        "¿Merece la pena el pase de temporada?"]),
    "D": (N_("otro juego"), None, [
        "¿Cómo refino hierro en Satisfactory?", "Receta de la poción de curación en Skyrim.", "¿Cómo se funde hierro en Minecraft?", "¿Qué recetas de crafteo hay en Stardew Valley?",
        "¿Cómo gano dinero en GTA Online?", "¿Cómo refino petróleo en Factorio?", "¿Cuál es el mejor arma en Elden Ring?", "¿Cómo mejoro la espada en Skyrim?",
        "¿Cómo saco carbón en Terraria?", "¿Qué es lo mejor para empezar en Hollow Knight?"]),
    "E": (N_("otra cosa"), None, [
        "¿Qué hora es?", "Receta de tortilla de patatas.", "¿Cómo se refina el petróleo?", "¿Qué es una refinería?", "¿Cómo hago pan en casa?", "¿Qué tiempo hace mañana?",
        "¿Cuántos años tiene el universo?", "¿Cómo se purifica el agua?", "¿Qué es la ferrita en un imán?", "Dime un dato curioso."]),
    "F": (N_("debe elegir la otra fuente"), "f2", [
        "¿Cómo hago la poción Golondrina en The Witcher 3?", "¿Qué ingredientes lleva el aceite contra necrófagos?", "¿Qué necesito para la poción Trueno?",
        "Receta de la decocción de Ekimmara."]),
    "gris": (N_("ambiguas: no cuentan en el criterio"), None, [
        "¿Cómo convierto el cloro en sal?", "¿Cómo se fabrica ferrita magnetizada?", "¿Cómo mezclo dos minerales en el juego para obtener otro?", "¿Para qué sirve el carbono condensado?",
        "¿Cómo mejoro la Golondrina a su versión superior?"]),
}
CON_JUEGO = ("B", "C", "gris")     # se repiten con el juego abierto: es donde más ayuda y donde más riesgo hay de usarla de más


def casos():
    """[(grupo, frase, ¿con el juego abierto?)]."""
    salida = [(g, f, False) for g, (_, _, frases) in GRUPOS.items() for f in frases]
    return salida + [(g, f, True) for g in CON_JUEGO for f in GRUPOS[g][2]]


def _clave(grupo, frase, juego, vuelta):
    return f"{grupo}|{frase}|{int(juego)}|{vuelta}"


def clasificar(respuesta):
    """Lo que hizo el modelo en su primer turno: el id que eligió, «id_malo», «buscar_web», «otra» (otra herramienta) o «responde» (contestó sin herramientas)."""
    llamadas = getattr(respuesta, "llamadas", None) or []
    for ll in llamadas:
        if ll.nombre == "usar_fuente":
            ident = str((ll.args or {}).get("id", ""))
            return ident if ident in {f["id"] for f in FUENTES} else "id_malo"
    if any(ll.nombre == "buscar_web" for ll in llamadas):
        return "buscar_web"
    return "otra" if llamadas else "responde"


def leer(archivo=None):
    try:
        lineas = (archivo or ARCHIVO).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    salida = []
    for l in lineas:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if isinstance(d, dict) and all(k in d for k in ("grupo", "frase", "juego", "vuelta", "hizo")):
            salida.append(d)
    return salida


def medir(preguntar, archivo=None, salida=print, dormir=time.sleep, pausa=PAUSA_SEG):
    """Pasa lo que falte de la tanda. `preguntar(frase, juego)` → Respuesta o ErrorIA. Devuelve «hecho», o «cupo» si hay que seguir en otro momento."""
    from lina.nucleo import proveedores as PROV
    archivo = archivo or ARCHIVO
    hechas = {_clave(r["grupo"], r["frase"], r["juego"], r["vuelta"]) for r in leer(archivo)}
    pendientes = [(g, f, j, v) for g, f, j in casos() for v in range(REPETICIONES) if _clave(g, f, j, v) not in hechas]
    RUT.asegurar(archivo.parent)
    for n, (grupo, frase, juego, vuelta) in enumerate(pendientes):
        r = preguntar(frase, juego)
        if isinstance(r, PROV.ErrorIA):
            if r.tipo in ("cuota", "auth"):
                salida(T("Parada: {motivo}. Quedan {n} llamadas; se sigue con la misma orden cuando haya cupo.", motivo=r.resumen[:120], n=len(pendientes) - n))
                return "cupo"
            salida(T("Una llamada ha fallado ({motivo}): se repetirá al continuar.", motivo=r.resumen[:120]))
        else:
            with open(archivo, "a", encoding="utf-8") as f:
                f.write(json.dumps({"grupo": grupo, "frase": frase, "juego": juego, "vuelta": vuelta, "hizo": clasificar(r)}, ensure_ascii=False) + "\n")
        if (n + 1) % 25 == 0:
            salida(T("  {n} de {total}…", n=n + 1, total=len(pendientes)))
        dormir(pausa)
    return "hecho"


def resumir(registros):
    """Los números, sin los grises: aciertos, «no la usa» (y qué hizo en su lugar) y graves (de más o id equivocado), en total y dentro del mismo juego."""
    r = {"total": 0, "debian": 0, "no_la_usa": 0, "memoria": 0, "buscar": 0, "graves": 0, "de_mas": 0, "id_mal": 0, "juego_total": 0, "juego_graves": 0, "por_grupo": {}, "gris": {}, "fallos": {}}
    for x in registros:
        grupo, hizo = x["grupo"], x["hizo"]
        if grupo == "gris":
            r["gris"].setdefault(x["frase"], {}).setdefault(hizo, 0)
            r["gris"][x["frase"]][hizo] += 1
            continue
        if grupo not in GRUPOS:
            continue
        esperado = GRUPOS[grupo][1]
        usada = hizo if hizo in {f["id"] for f in FUENTES} or hizo == "id_malo" else None
        r["total"] += 1
        g = r["por_grupo"].setdefault(grupo, {"n": 0, "bien": 0})
        g["n"] += 1
        bien = usada == esperado
        g["bien"] += bien
        if esperado:
            r["debian"] += 1
        if grupo == "C":
            r["juego_total"] += 1
        if bien:
            continue
        if esperado and usada is None:
            r["no_la_usa"] += 1
            r["memoria"] += hizo in ("responde", "otra")
            r["buscar"] += hizo == "buscar_web"
            tipo = "no_la_usa"
        else:
            r["graves"] += 1
            r["de_mas" if not esperado else "id_mal"] += 1
            r["juego_graves"] += grupo == "C"
            tipo = "grave"
        clave = (tipo, x["frase"])
        r["fallos"][clave] = r["fallos"].get(clave, 0) + 1
    return r


def decision(r):
    """Lo que toca según el criterio de A11. None si la tanda no está completa."""
    if r["total"] < sum(1 for g, _, _ in casos() if g != "gris") * REPETICIONES:
        return None
    grave = r["graves"] / r["total"] > MAX_GRAVE or (r["juego_total"] and r["juego_graves"] / r["juego_total"] > MAX_GRAVE)
    if grave:
        return "R3"
    return "R2" if r["debian"] and r["no_la_usa"] / r["debian"] > MAX_NO_LA_USA else "sola"


DECISIONES = {"sola": N_("se activa usar_fuente sola"), "R2": N_("el fallo grave está bien, pero no la usa demasiadas veces: toca un paso previo con el modelo ligero (R2)"),
              "R3": N_("demasiados fallos graves: no se activa así; toca comprobar el tema al usarla (R3) y volver a medir")}


def _pc(a, b):
    return f"{100 * a / b:.1f} %" if b else "-"


def informe(registros, salida=print):
    r = resumir(registros)
    salida(T("Medido: {n} respuestas ({g} ambiguas, aparte).", n=r["total"], g=sum(sum(v.values()) for v in r["gris"].values())))
    for g, (nombre, _, _) in GRUPOS.items():
        if g in r["por_grupo"]:
            d = r["por_grupo"][g]
            salida(f"  {g}  {T(nombre)}: {d['bien']}/{d['n']} ({_pc(d['bien'], d['n'])})")
    salida(T("Fallos graves (usarla cuando no debía o con el id equivocado): {n} de {t} ({pc}); de más {m}, id equivocado {i}.",
             n=r["graves"], t=r["total"], pc=_pc(r["graves"], r["total"]), m=r["de_mas"], i=r["id_mal"]))
    salida(T("Dentro del mismo juego: {n} de {t} ({pc}).", n=r["juego_graves"], t=r["juego_total"], pc=_pc(r["juego_graves"], r["juego_total"])))
    salida(T("No la usa cuando debía: {n} de {t} ({pc}); contestó sin buscar {m}, búsqueda general {b}.",
             n=r["no_la_usa"], t=r["debian"], pc=_pc(r["no_la_usa"], r["debian"]), m=r["memoria"], b=r["buscar"]))
    for (tipo, frase), n in sorted(r["fallos"].items(), key=lambda x: (x[0][0], -x[1])):
        salida(f"  [{T('grave') if tipo == 'grave' else T('no la usa')}] ×{n}  {frase}")
    if r["gris"]:
        salida(T("Ambiguas (no cuentan):"))
        for frase, hizo in r["gris"].items():
            salida(f"  {frase}  " + ", ".join(f"{k} ×{v}" for k, v in sorted(hizo.items())))
    d = decision(r)
    salida(T("Decisión: {d}.", d=T(DECISIONES[d])) if d else T("La tanda está incompleta: todavía no se puede decidir."))


def _preguntar_de_verdad():
    """La función que pregunta al modelo rápido con lo mismo que recibiría en una petición: siempre la clave gratuita de Gemini. (función, «») o (None, motivo)."""
    from lina.nucleo import claves as CL
    from lina.nucleo import fuentes as FUE
    from lina.nucleo import grupos as G
    from lina.nucleo import herramientas as H
    from lina.nucleo import ia as IA
    from lina.nucleo import ia_activa as IAC
    from lina.nucleo.constantes import instrucciones
    ia = IAC.actual()
    clave = CL.obtener("gemini")
    if ia.nombre != "gemini" or not clave:
        return None, T("Esta medida necesita Gemini con su clave gratuita.")
    modelo = IAC.modelos("rapido")[0]
    usar = FUE.declaracion_usar_fuente(FUENTES)

    def preguntar(frase, juego):
        grupos = G.elegir(frase)
        herramientas = [usar] + IA.declaraciones_de_busqueda() + G.herramientas(H.DECLARACIONES, grupos)
        sistema = G.sistema(instrucciones(), H.hechos_sistema(), G.ordenar(grupos))
        texto = (f"Contexto: videojuego «{JUEGO}». Pregunta: {frase}" if juego else frase) + ("\n[SISTEMA: esta petición NO lleva captura de pantalla: no sabes lo que hay en ella.]")
        with IA.motivo_llamada("medida"):
            return IA._turno_medido(ia.proveedor, clave, modelo, sistema, [{"rol": "user", "texto": texto}], herramientas=herramientas,
                                    nivel=IA.nivel_razonamiento(modelo, "rapido"), timeout=20)
    return preguntar, ""


def principal(argv, salida=print, preguntar=None, archivo=None, dormir=time.sleep):
    if [a for a in argv if a != "--lanzar"]:
        salida(T("Uso:  lina fuentes medir [--lanzar]"))
        return 2
    archivo = archivo or ARCHIVO
    registros = leer(archivo)
    total = len(casos()) * REPETICIONES
    if "--lanzar" not in argv:
        salida(T("Tanda: {f} frases × {r} = {t} llamadas al modelo ligero con la clave gratuita, sin ejecutar nada. Hechas: {h}. Para lanzarla:  lina fuentes medir --lanzar",
                 f=len(casos()), r=REPETICIONES, t=total, h=len(registros)))
        if registros:
            informe(registros, salida)
        return 0
    if preguntar is None:
        preguntar, motivo = _preguntar_de_verdad()
        if preguntar is None:
            salida(motivo)
            return 1
    fin = medir(preguntar, archivo, salida, dormir)
    informe(leer(archivo), salida)
    return 0 if fin == "hecho" else 3
