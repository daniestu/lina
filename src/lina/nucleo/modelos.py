# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Los modelos que Lina necesita en el disco: el de voz a texto (Whisper) y la voz de Piper.

Se descargan una vez (con `lina modelos`, que ejecuta el instalador) y después todo funciona sin internet. Whisper se baja con la librería
faster-whisper, que comprueba la integridad de cada archivo contra la huella que publica Hugging Face; las voces las comprueba voz/voces.py.
"""

from lina.nucleo import ajustes as AJ
from lina.nucleo import cuda as CUDA
from lina.voz import voces as VOC
from lina.nucleo.idioma import T

MODELO_WHISPER = "small"                    # voz a texto en la CPU: lo que se instala siempre y a lo que se vuelve si la tarjeta falla
MODELO_GPU = "large-v3-turbo"               # con una NVIDIA lista: más preciso y, en la tarjeta, más rápido (medido: 14/15 frente a 12/15, 0,09 s frente a 0,6 s; con pesos int8_float16 gasta ~1 GB de VRAM y acierta igual que con float16, que gasta ~2,2 GB)


def whisper_listo(descargar=None, modelo=None):
    """True si el modelo de Whisper ya está en el disco (no descarga nada)."""
    try:
        descargar = descargar or _descargar
        descargar(modelo or MODELO_WHISPER, local_files_only=True)
        return True
    except Exception:
        return False


def _descargar(nombre, **k):
    from faster_whisper.utils import download_model
    return download_model(nombre, **k)


def _cuda_usable():
    """¿faster-whisper puede usar la tarjeta? (con las librerías de NVIDIA del entorno de Lina cargadas, si las hay)."""
    try:
        CUDA.cargar_librerias()
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def elegir_whisper(cuda_usable=None, descargar=None, ajustes=None):
    """→ (modelo, procesador, cálculo, motivo, falta_descargar). `voz.reconocimiento_*` en «auto»: la tarjeta con el modelo grande si está todo listo (librerías
    de NVIDIA y modelo en el disco); si no, `small` en la CPU como siempre. Nunca descarga ni instala nada por su cuenta."""
    aj = ajustes or AJ.solo_lectura()
    modelo = str(aj.get("voz", "reconocimiento_modelo") or "auto")
    proc = str(aj.get("voz", "reconocimiento_procesador") or "auto")
    if proc == "cpu":
        return (MODELO_WHISPER if modelo == "auto" else modelo), "cpu", "int8", "elegido en tus ajustes", None
    usable = _cuda_usable() if cuda_usable is None else cuda_usable
    if not usable:
        motivo = "pides la tarjeta pero no la puedo usar (¿faltan las librerías de NVIDIA? prueba  lina modelos gpu)" if proc == "cuda" else "sin tarjeta NVIDIA lista"
        return (MODELO_WHISPER if modelo == "auto" else modelo), "cpu", "int8", motivo, None
    elegido = MODELO_GPU if modelo == "auto" else modelo
    if not whisper_listo(descargar, elegido):
        return MODELO_WHISPER, "cpu", "int8", f"la tarjeta está lista pero falta bajar «{elegido}» (prueba  lina modelos gpu)", elegido
    return elegido, "cuda", "int8_float16", "tarjeta NVIDIA lista", None


VRAM_WHISPER_MB = {"int8_float16": 1100, "float16": 2300}     # lo que ocupa Whisper en la tarjeta (medido con large-v3-turbo; con margen)
_en_tarjeta = {"mb": 0}


def vram_whisper_mb():
    """MB de VRAM que ocupa el Whisper cargado (0 si está en la CPU): cuenta para el tope de VRAM de Lina (ia.tope_vram_mb)."""
    return _en_tarjeta["mb"]


def cargar_whisper(log=print, fabrica=None, elegir=None):
    """Carga Whisper como toca. Si la tarjeta falla al cargar, vuelve a `small` en la CPU y lo cuenta: poder hablar con Lina pesa más que ir rápido."""
    if fabrica is None:
        from faster_whisper import WhisperModel as fabrica
    modelo, proc, calculo, motivo, _ = (elegir or elegir_whisper)()
    log(f"Cargando Whisper ({modelo}, {'tarjeta gráfica' if proc == 'cuda' else 'CPU'}): {motivo}...")
    _en_tarjeta["mb"] = 0
    try:
        cargado = fabrica(modelo, device=proc, compute_type=calculo)
        if proc == "cuda":
            _en_tarjeta["mb"] = VRAM_WHISPER_MB.get(calculo, max(VRAM_WHISPER_MB.values()))
        return cargado
    except Exception as e:
        if (modelo, proc) == (MODELO_WHISPER, "cpu"):
            raise
        log(f"Whisper: no he podido cargar «{modelo}» en {proc} ({type(e).__name__}: {str(e)[:120]}); uso «{MODELO_WHISPER}» en la CPU.")
        return fabrica(MODELO_WHISPER, device="cpu", compute_type="int8")


def asegurar_gpu(log=print, entrada=input, descargar=None, instalar=None):
    """`lina modelos gpu`: deja lista la tarjeta NVIDIA para la voz (librerías CUDA en el entorno de Lina + el modelo grande), pidiendo permiso antes."""
    if not CUDA.hay_nvidia():
        log(T("No veo ninguna tarjeta NVIDIA (no encuentro nvidia-smi); Lina seguirá usando la CPU."))
        return False
    pendiente = []
    if not CUDA.instaladas():
        pendiente.append(T("las librerías CUDA de NVIDIA (unos 700 MB, solo en el entorno de Lina)"))
    if not whisper_listo(descargar, MODELO_GPU):
        pendiente.append(T("el modelo «{modelo}» (unos 1600 MB)", modelo=MODELO_GPU))
    if pendiente:
        log(T("Para usar la tarjeta hay que bajar: {que}.", que=" y ".join(pendiente)))
        if entrada(T("¿Sigo? [s/N] ")).strip().lower() not in ("s", "si", "sí", "y", "yes"):
            log(T("Vale, no toco nada."))
            return False
        if not CUDA.instaladas() and not (instalar or CUDA.instalar)(log):
            log(T("No he podido instalar las librerías."))
            return False
        if not whisper_listo(descargar, MODELO_GPU):
            try:
                (descargar or _descargar)(MODELO_GPU)
            except Exception as e:
                log(T("No he podido descargar el modelo ({error}).", error=f"{type(e).__name__}: {str(e)[:120]}"))
                return False
    if not _cuda_usable():
        log(T("Todo está bajado pero faster-whisper no ve la tarjeta; Lina seguirá en la CPU."))
        return False
    log(T("Listo: Lina usará la tarjeta para entenderte cuando se reinicie."))
    return True


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
    lina modelos estado     dice qué hay
    lina modelos gpu        deja lista tu tarjeta NVIDIA para entenderte mejor (pregunta antes de bajar nada)"""
    if argv[:1] == ["gpu"]:
        return 0 if asegurar_gpu(print) else 1
    if argv[:1] == ["estado"]:
        e = estado()
        print(T("Whisper ({modelo}): {estado}", modelo=MODELO_WHISPER, estado=T("listo") if e["whisper"] else T("sin descargar")))
        modelo, proc, _, motivo, _f = elegir_whisper()
        print(T("Reconocimiento que se usará: {modelo} en {proc} ({motivo})", modelo=modelo, proc=proc, motivo=motivo))
        print(T("Voz: {v1}", v1=e['voz'] or T('sin descargar')) + ("" if e["voz_integra"] in (True, None) or not e["voz"] else T("  ¡ARCHIVO ALTERADO!")))
        return 0
    todo, problemas = asegurar_todo()
    if not todo:
        print(T("Faltan: ") + ", ".join(problemas) + T(". Comprueba la conexión y repite:  lina modelos"))
        return 1
    return 0
