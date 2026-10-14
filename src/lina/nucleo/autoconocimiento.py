"""Lina se conoce a sí misma: su documentación, sus comandos y sus ajustes, a mano para consultar y para cambiar sin gastar búsquedas.

La IA decide qué hacer con esto (nada de frases fijas). Este módulo solo le da:
  · ayuda(tema): sus manuales (los mismos de docs/), la lista de comandos de la terminal, todos los ajustes con su valor actual y las voces.
  · cambiar(...): cambiar un ajuste, con las mismas protecciones de siempre. Lo que da más permisos o más gasto solo se hace si el usuario
    ha pulsado el atajo (no por «Oye Lina») y no se ha leído nada de fuera en esta petición. Las claves y el tope de gasto no se tocan desde aquí.
"""
from pathlib import Path

from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT

CARPETA = RUT.PAQUETE / "datos" / "ayuda"
# Lo que la IA nunca cambia por su cuenta: dinero y claves (los cambia el usuario con su voz o en la terminal)
INTOCABLES = {("gasto", "tope_mensual_eur"), ("gasto", "eur_por_usd"), ("gasto", "avisos_porcentaje"), ("privacidad", "almacen_claves")}


def manuales():
    return sorted(p.stem for p in CARPETA.glob("*.md")) if CARPETA.is_dir() else []


def _ajustes_con_valores(aj):
    filas = []
    for seccion, claves in AJ.ESQUEMA.items():
        filas.append(f"[{seccion}] {AJ.TITULOS[seccion]}")
        for clave, (defecto, tipo, restr, nota) in claves.items():
            limites = f" (de {restr[0]} a {restr[1]})" if tipo in ("int", "float") and restr else (f" (opciones: {', '.join(restr)})" if tipo == "opcion" else "")
            filas.append(f"  {seccion}.{clave} = {AJ.a_toml(aj.get(seccion, clave))}{limites} · {nota}")
    return "\n".join(filas)


def _voces():
    from lina.voz import voces
    actual = voces.voz_elegida()
    lineas = []
    for nombre, ficha in voces.CATALOGO[voces.IDIOMA].items():
        lineas.append(f"  {'*' if nombre == actual else ' '} {nombre}: {ficha['descripcion']} "
                      f"[{'instalada' if voces.instalada(nombre) else 'se descarga al elegirla'}]")
    return ("Voces (* = la actual). Aquí NO consta si cada una es de hombre o de mujer: no lo inventes, haz que el usuario las oiga "
            "(accion=probar_voz) y que decida él:\n" + "\n".join(lineas))


def ayuda(tema=None, aj=None):
    """Texto de consulta. Sin tema: comandos, ajustes con su valor, voces y qué manuales hay. Con tema: ese manual entero."""
    aj = aj or AJ.actuales(log=lambda m: None)
    tema = str(tema or "").strip().lower().removesuffix(".md")
    if tema:
        ruta = CARPETA / f"{tema}.md"
        if tema in manuales():
            return ruta.read_text(encoding="utf-8")
        return f"No hay manual «{tema}». Hay: {', '.join(manuales()) or 'ninguno'}."
    from lina import __main__ as principal
    return "\n\n".join([
        "COMANDOS DE LA TERMINAL (el usuario los escribe; tú usas la herramienta mis_ajustes, que hace lo mismo):\n" + principal.AYUDA.strip()
        + "\n\n" + AJ.AYUDA,
        "AJUSTES Y SU VALOR AHORA:\n" + _ajustes_con_valores(aj),
        _voces(),
        f"Manuales completos (accion=ayuda, tema=NOMBRE): {', '.join(manuales())}.",
    ])


def cambiar(clave, valor, voz_libre=False, contaminado=False, aj=None):
    """Cambia un ajuste. Devuelve (hecho, texto para la IA)."""
    aj = aj or AJ.actuales(log=lambda m: None)
    n = AJ._nombre_completo(str(clave or ""))
    if not n:
        return False, f"No existe el ajuste «{clave}». Mira los que hay con accion=ayuda."
    if n in INTOCABLES:
        return False, ("Eso no lo cambias tú: el dinero y las claves los cambia solo el usuario. Dile que lo haga por voz con el atajo "
                       "(«sube el tope de gasto a N euros») o en la terminal con «lina config poner» o «lina clave».")
    try:
        nuevo = AJ.validar(n[0], n[1], valor)
    except ValueError as e:
        return False, f"No vale: {n[0]}.{n[1]} {e}."
    if AJ.cambio_sensible(n[0], n[1], nuevo, aj):
        if voz_libre:
            return False, ("Eso da más permisos y por seguridad solo se cambia si el usuario pulsa el atajo y lo pide él, no con «Oye Lina» "
                           "(podría haberlo dicho otra voz). Díselo en una frase.")
        if contaminado:
            return False, "En esta petición has leído contenido de fuera, así que no cambio nada que dé más permisos. Díselo y que lo pida de nuevo."
    antes = aj.get(n[0], n[1])
    aj.establecer(n[0], n[1], nuevo)
    return True, f"Hecho: {n[0]}.{n[1]} pasa de {AJ.a_toml(antes)} a {AJ.a_toml(nuevo)}."
