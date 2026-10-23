# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-voz`: mide qué entiende cada Whisper de TU voz y de TU micrófono, para elegir con números y no a ojo.

Graba unas frases que tú lees (se guardan en tu equipo y se pueden borrar), las pasa por varias combinaciones de motor, modelo y procesador, y enseña
cuántas acertó cada una, cuánto tardó y cuánta memoria de vídeo gastó. No cambia ningún ajuste de Lina: solo mide.
Las combinaciones que no se pueden usar aquí (sin tarjeta gráfica, sin la librería) se saltan diciendo por qué."""
import difflib
import gc
import shutil
import subprocess
import time
import wave

from lina.nucleo import comandos as C
from lina.nucleo import cuda as CUDA
from lina.nucleo import idioma as IDI
from lina.nucleo import rutas as RUT
from lina.nucleo.idioma import T

FRECUENCIA = 16000
CARPETA = RUT.DATOS / "prueba-voz"

FRASES = {
    "es": ["Pon música", "Pausa", "Reanuda la música", "Siguiente canción", "Sube el volumen", "Baja el volumen", "Silencia el sonido",
           "Abre Firefox", "Abre Dolphin", "¿Qué hora es?", "Cierra esta ventana", "Conecta los auriculares", "¿Cómo va la gráfica?",
           "Recuerda que mi navegador favorito es Brave", "Busca recetas de tortilla de patatas"],
    "en": ["Play music", "Pause", "Resume the music", "Next song", "Turn the volume up", "Turn the volume down", "Mute the sound",
           "Open Firefox", "Open Dolphin", "What time is it?", "Close this window", "Connect the headphones", "How is the graphics card doing?",
           "Remember that my favourite browser is Brave", "Search for omelette recipes"],
}

# (motor, modelo, procesador, cálculo, sale en la prueba corta). El primero es lo que Lina usa hoy.
COMBINACIONES = [
    ("faster-whisper", "small", "cpu", "int8", True),
    ("faster-whisper", "large-v3-turbo", "cuda", "float16", True),
    ("faster-whisper", "large-v3-turbo", "cpu", "int8", True),
    ("whisper", "turbo", "cuda", "float16", True),
    ("faster-whisper", "medium", "cpu", "int8", False),
    ("faster-whisper", "medium", "cuda", "float16", False),
    ("whisper", "small", "cuda", "float16", False),
    ("whisper", "medium", "cuda", "float16", False),
]
TAMANOS_MB = {"small": 500, "medium": 1500, "large-v3-turbo": 1600, "turbo": 1600}


def frases():
    return FRASES.get(IDI.actual()) or FRASES["es"]


# ======================= grabaciones =======================
def ruta_audio(i):
    return CARPETA / f"frase{i + 1:02d}.wav"


def guardar_wav(ruta, audio):
    import numpy as np
    datos = (np.clip(np.asarray(audio, dtype="float32"), -1, 1) * 32767).astype("int16")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FRECUENCIA)
        w.writeframes(datos.tobytes())


def leer_wav(ruta):
    import numpy as np
    with wave.open(str(ruta), "rb") as w:
        crudo = w.readframes(w.getnframes())
    return np.frombuffer(crudo, dtype="int16").astype("float32") / 32768.0


def grabar_una(entrada=input, salida=print):
    """Enter para empezar y Enter para terminar. Devuelve el audio (float32, mono, 16 kHz)."""
    import numpy as np
    import sounddevice as sd
    trozos = []
    entrada(T("   Pulsa Enter, di la frase y pulsa Enter otra vez… "))
    with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32", callback=lambda d, n, t, s: trozos.append(d.copy())):
        entrada(T("   🎙  Grabando… (Enter para terminar) "))
    return np.concatenate(trozos).reshape(-1) if trozos else np.zeros(0, dtype="float32")


def grabar_todas(regrabar=False, grabar=grabar_una, salida=print, entrada=input):
    """Graba las frases que faltan (o todas con regrabar). Devuelve cuántas grabaciones hay."""
    lista = frases()
    for i, frase in enumerate(lista):
        if ruta_audio(i).exists() and not regrabar:
            continue
        while True:
            salida(T("\nFrase {n} de {total}:  «{frase}»", n=i + 1, total=len(lista), frase=frase))
            audio = grabar(entrada=entrada, salida=salida)
            if len(audio) < FRECUENCIA * 0.3:
                salida(T("   No he oído nada; repítela."))
                continue
            guardar_wav(ruta_audio(i), audio)
            break
    return sum(1 for i in range(len(lista)) if ruta_audio(i).exists())


# ======================= comparar =======================
def parecido(esperada, oida):
    """0 a 1: cuánto se parece lo que oyó a lo que dijiste (sin mayúsculas, tildes ni signos)."""
    a, b = C.normalizar(esperada), C.normalizar(oida)
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


def acierta(esperada, oida):
    return C.normalizar(esperada) == C.normalizar(oida)


def resumir(esperadas, resultados):
    """resultados = [(texto, segundos)] en el orden de las frases → números para la tabla."""
    n = len(esperadas)
    aciertos = sum(1 for e, (t, _) in zip(esperadas, resultados) if acierta(e, t))
    similitud = sum(parecido(e, t) for e, (t, _) in zip(esperadas, resultados)) / max(1, n)
    tiempos = [s for _, s in resultados]
    return {"aciertos": aciertos, "total": n, "similitud": similitud,
            "media_s": sum(tiempos) / max(1, len(tiempos)), "max_s": max(tiempos) if tiempos else 0.0}


# ======================= motores =======================
def _vram_mb():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.split()[0]) if r.returncode == 0 and r.stdout.split() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _cuda_faster():
    import ctranslate2
    return ctranslate2.get_cuda_device_count() > 0


def _cuda_whisper():
    import torch
    return bool(torch.cuda.is_available())


def cargar(motor, modelo, procesador, calculo):
    """→ función `transcribir(audio, idioma, pista) -> texto`. Falla con una excepción que se cuenta, nunca se traga."""
    if motor == "faster-whisper":
        from faster_whisper import WhisperModel
        if procesador == "cuda":
            CUDA.cargar_librerias()                                        # si están en el entorno de Lina; si no, falla con su motivo
        if procesador == "cuda" and not _cuda_faster():
            raise RuntimeError(T("no hay tarjeta gráfica que use faster-whisper"))
        m = WhisperModel(modelo, device=procesador, compute_type=calculo)

        def transcribir(audio, idioma, pista):
            segmentos, _ = m.transcribe(audio, language=idioma, vad_filter=True, initial_prompt=pista or None)
            return " ".join(s.text for s in segmentos).strip()
        return transcribir
    import whisper
    if procesador == "cuda" and not _cuda_whisper():
        raise RuntimeError(T("PyTorch no ve ninguna tarjeta gráfica"))
    m = whisper.load_model(modelo, device=procesador)

    def transcribir(audio, idioma, pista):
        return m.transcribe(audio, language=idioma, initial_prompt=pista or None, fp16=(procesador == "cuda"))["text"].strip()
    return transcribir


def _pista():
    try:
        from lina.nucleo.asistente import prompt_whisper
        return prompt_whisper()
    except Exception:
        return ""


def medir_una(combinacion, audios, esperadas, cargador=cargar, pista="", reloj=time.time, vram=_vram_mb, salida=print):
    """→ dict con los números, o {"error": …} si esa combinación no se puede usar aquí."""
    motor, modelo, procesador, calculo = combinacion[:4]
    antes = vram() if procesador == "cuda" else None
    try:
        t0 = reloj()
        transcribir = cargador(motor, modelo, procesador, calculo)
        carga = reloj() - t0
        transcribir(audios[0], IDI.actual(), pista)                      # la primera vez siempre es más lenta (calentar no cuenta)
        resultados = []
        for audio in audios:
            t0 = reloj()
            texto = transcribir(audio, IDI.actual(), pista)
            resultados.append((texto, reloj() - t0))
        despues = vram() if procesador == "cuda" else None
    except Exception as e:                                                # sin librería, sin tarjeta, sin red para bajar el modelo…
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    finally:
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
    r = resumir(esperadas, resultados)
    r.update(carga_s=carga, textos=[t for t, _ in resultados],
             vram_mb=(despues - antes) if antes is not None and despues is not None else None)
    return r


def elegir(completo=False):
    return [c for c in COMBINACIONES if completo or c[4]]


def etiqueta(c):
    return f"{c[0]} · {c[1]} · {c[2]}" + (f" ({c[3]})" if c[3] else "")


def informe(esperadas, medidas):
    """El texto de la tabla y, debajo, lo que falló en cada combinación."""
    lineas = [T("RESULTADOS  (frases: {n}). «Aciertos» = idéntica a lo que dijiste, sin contar mayúsculas ni tildes.", n=len(esperadas)), ""]
    lineas.append(f"{'':<52}{T('aciertos'):>10}{T('parecido'):>10}{T('media'):>9}{T('máx.'):>8}{T('carga'):>8}{T('VRAM'):>9}")
    for comb, r in medidas:
        if "error" in r:
            lineas.append(f"{etiqueta(comb):<52}{T('no disponible')}: {r['error']}")
            continue
        vram = f"{r['vram_mb']} MB" if r.get("vram_mb") is not None else "-"
        lineas.append(f"{etiqueta(comb):<52}{r['aciertos']:>6}/{r['total']:<3}{r['similitud'] * 100:>8.0f} %{r['media_s']:>7.2f} s{r['max_s']:>6.2f} s{r['carga_s']:>6.1f} s{vram:>9}")
    lineas += ["", T("DÓNDE FALLA CADA UNA  (lo que dijiste → lo que oyó)")]
    for comb, r in medidas:
        if "error" in r:
            continue
        malas = [(e, t) for e, t in zip(esperadas, r["textos"]) if not acierta(e, t)]
        lineas.append(f"\n{etiqueta(comb)}: " + (T("ninguna") if not malas else ""))
        lineas += [f"   «{e}» → «{t}»" for e, t in malas]
    return "\n".join(lineas)


def instalar_cuda(salida=print):
    return CUDA.instalar(salida=salida)


def principal(argv, salida=print, entrada=input, grabar=grabar_una, cargador=cargar):
    if argv[:1] == ["grande"]:
        from lina.nucleo import probar_voz_grande
        return probar_voz_grande.principal(argv[1:], salida=salida, entrada=entrada, grabar=grabar)
    if argv[:1] == ["mas"]:
        from lina.nucleo import probar_voz_mas
        return probar_voz_mas.principal(argv[1:], salida=salida, entrada=entrada)
    if "borrar" in argv:
        if CARPETA.exists():
            shutil.rmtree(CARPETA, ignore_errors=True)
        salida(T("Borradas las grabaciones de la prueba."))
        return 0
    if any(a in ("-h", "--help", "ayuda") for a in argv):
        salida(T("Uso:  lina probar-voz [--completo] [--regrabar]   |   lina probar-voz borrar"))
        return 0
    completo, regrabar = "--completo" in argv, "--regrabar" in argv
    lista = frases()
    salida(T("Voy a pedirte {n} frases cortas, una a una, y luego las pasaré por varios Whisper para ver cuál te entiende mejor. No cambia nada de Lina. "
             "Las grabaciones se quedan en {ruta} (se borran con  lina probar-voz borrar).", n=len(lista), ruta=CARPETA))
    try:
        hechas = grabar_todas(regrabar, grabar=grabar, salida=salida, entrada=entrada)
    except (ImportError, OSError) as e:
        salida(T("No puedo grabar: {error}", error=e))
        return 1
    if hechas < len(lista):
        return 1
    elegidas = elegir(completo)
    grandes = sorted({c[1] for c in elegidas if TAMANOS_MB.get(c[1], 0) > 600})
    if grandes:
        total = sum(TAMANOS_MB[m] for m in grandes)
        salida(T("\nPara medir hay que bajar, si no los tienes ya, estos modelos: {modelos} (unos {mb} MB en total). Los motores o tarjetas que no existan aquí se saltan.",
                 modelos=", ".join(grandes), mb=total))
        if entrada(T("¿Sigo? [s/N] ")).strip().lower() not in ("s", "si", "sí", "y", "yes"):
            salida(T("Vale, no mido nada. Tus grabaciones siguen guardadas."))
            return 0
    if any(c[2] == "cuda" and c[0] == "faster-whisper" for c in elegidas) and CUDA.hay_nvidia() and not CUDA.instaladas():
        salida(T("\nPara usar tu tarjeta NVIDIA con faster-whisper faltan las librerías CUDA (cuBLAS y cuDNN, unos 700 MB). Se instalarían solo en el entorno de Lina con pip; no tocan el sistema."))
        if entrada(T("¿Las instalo? [s/N] ")).strip().lower() in ("s", "si", "sí", "y", "yes"):
            salida(T("Instalando…"))
            salida(T("Hecho.") if instalar_cuda(salida) else T("No he podido instalarlas; esas filas saldrán como no disponibles."))
    audios = [leer_wav(ruta_audio(i)) for i in range(len(lista))]
    pista = _pista()
    medidas = []
    for comb in elegidas:
        salida(T("Midiendo {que}…", que=etiqueta(comb)))
        medidas.append((comb, medir_una(comb, audios, lista, cargador=cargador, pista=pista)))
    texto = informe(lista, medidas)
    salida("\n" + texto)
    try:
        (CARPETA / "informe.txt").write_text(texto + "\n", encoding="utf-8")
        salida(T("\nGuardado en {ruta}", ruta=CARPETA / "informe.txt"))
    except OSError:
        pass
    return 0
