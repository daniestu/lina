"""`lina privacidad`: qué sale del equipo y el consentimiento para enviar capturas de pantalla. Solo lo decide el usuario, en una terminal."""
import sys

from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT
from lina.nucleo import idioma as IDI
from lina.nucleo.idioma import N_, T

MANUAL = RUT.PAQUETE / "datos" / "ayuda" / "privacidad.md"
FRASES = {"si": N_("Permitido: enviaré capturas de tu pantalla cuando hagan falta (nunca en modo privado ni con ventanas sensibles)."),
          "no": N_("Anotado: no enviaré nunca capturas de tu pantalla."),
          "preguntar": N_("Vuelve a quedar sin decidir: no se enviará ninguna captura hasta que lo decidas.")}
ALIAS = {"sí": "si", "s": "si", "yes": "si", "y": "si", "n": "no"}


def estado(aj=None):
    return (aj or AJ.actuales(log=lambda m: None)).get("privacidad", "capturas")


def principal(argv, entrada=input, salida=print, ajustes=None, es_terminal=None):
    aj = ajustes or AJ.actuales(log=lambda m: None)
    terminal = sys.stdin.isatty() if es_terminal is None else es_terminal
    if argv and argv[0] in ("ayuda", "-h", "--help"):
        salida(T("lina privacidad          explica qué sale del equipo y te pregunta por las capturas\nlina privacidad si|no   lo decide sin preguntar"))
        return 0
    if argv and argv[0] != "estado":
        eleccion = ALIAS.get(argv[0].lower(), argv[0].lower())
        if eleccion not in FRASES:
            salida(T("Opciones: si · no · preguntar (o sin nada para que te lo explique)."))
            return 2
        if not terminal:
            salida(T("Esto lo decides tú, en una terminal."))
            return 2
        aj.establecer("privacidad", "capturas", eleccion)
        salida(T(FRASES[eleccion]))
        return 0
    manual = MANUAL.with_name(f"privacidad.{IDI.actual()}.md")
    if not manual.is_file():
        manual = MANUAL
    salida(manual.read_text(encoding="utf-8") if manual.is_file() else T("Falta el manual de privacidad."))
    actual = estado(aj)
    salida(T("\nAhora mismo, capturas de pantalla: {actual}.", actual=actual))
    if not terminal or argv:
        return 0
    try:
        r = entrada(T("\n¿Permites que Lina envíe capturas de tu pantalla a la IA cuando haga falta? [s]í / [n]o / Intro para dejarlo como está: ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0
    r = ALIAS.get(r, r)
    if r in ("si", "no"):
        aj.establecer("privacidad", "capturas", r)
        salida(T(FRASES[r]))
    else:
        salida(T("Sin cambios."))
    return 0
