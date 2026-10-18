# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Los modelos que Lina necesita en el disco: el de voz a texto (Whisper) y la voz de Piper.

Se descargan una vez (con `lina modelos`, que ejecuta el instalador) y después todo funciona sin internet. Whisper se baja con la librería
faster-whisper, que comprueba la integridad de cada archivo contra la huella que publica Hugging Face; las voces las comprueba voz/voces.py.
"""
from lina.nucleo import ajustes as AJ
from lina.voz import voces as VOC
from lina.nucleo.idioma import T

MODELO_WHISPER = "small"                    # voz a texto, en la CPU


def whisper_listo(descargar=None):
    """True si el modelo de Whisper ya está en el disco (no descarga nada)."""
    try:
        descargar = descargar or _descargar
        descargar(MODELO_WHISPER, local_files_only=True)
        return True
    except Exception:
        return False


def _descargar(nombre, **k):
    from faster_whisper.utils import download_model
    return download_model(nombre, **k)


def asegurar_whisper(log=print, descargar=None):
    """Deja Whisper listo. True si lo está (ya estaba o se ha bajado)."""
    descargar = descargar or _descargar
    if whisper_listo(descargar):
        return True
    log(f"Whisper: descargando el modelo «{MODELO_WHISPER}» (unos 500 MB, solo esta vez)…")
    try:
        descargar(MODELO_WHISPER)
    except Exception as e:
        log(f"Whisper: no he podido descargarlo ({type(e).__name__}: {str(e)[:120]}).")
        return False
    log("Whisper: listo.")
    return True


def estado(descargar=None):
    """{'whisper': bool, 'voz': nombre|None, 'voz_integra': True|False|None}: lo que hay ahora mismo."""
    elegida = AJ.solo_lectura().get("voz", "voz")                  # sin crear config.toml: ver el estado no cambia nada
    ok = VOC.instalada(elegida)
    return {"whisper": whisper_listo(descargar), "voz": elegida if ok else None, "voz_integra": VOC.verificar(elegida)[0] if ok else False}


def asegurar_todo(log=print, descargar=None, simular=False):
    """Whisper y la voz elegida. Devuelve (todo_listo, [problemas])."""
    problemas = []
    if simular:
        log(f"[simulación] descargaría Whisper «{MODELO_WHISPER}» y la voz elegida en tu configuración")
        return True, problemas
    if not asegurar_whisper(log, descargar):
        problemas.append("Whisper")
    if not VOC.preparar(log=log):
        problemas.append("la voz")
    return not problemas, problemas


def principal(argv):
    """lina modelos            descarga lo que falte (Whisper y la voz elegida)
    lina modelos estado     dice qué hay"""
    if argv[:1] == ["estado"]:
        e = estado()
        print(T("Whisper ({modelo}): {estado}", modelo=MODELO_WHISPER, estado=T("listo") if e["whisper"] else T("sin descargar")))
        print(T("Voz: {v1}", v1=e['voz'] or T('sin descargar')) + ("" if e["voz_integra"] in (True, None) or not e["voz"] else T("  ¡ARCHIVO ALTERADO!")))
        return 0
    todo, problemas = asegurar_todo()
    if not todo:
        print(T("Faltan: ") + ", ".join(problemas) + T(". Comprueba la conexión y repite:  lina modelos"))
        return 1
    return 0
