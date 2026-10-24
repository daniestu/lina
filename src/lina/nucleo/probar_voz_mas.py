# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-voz mas`: segunda tanda de medidas, con las grabaciones que ya tienes, para entender mejor sin pasar de un tope de memoria de vídeo.

Mide, con tus mismas frases:
  A. Whisper en la tarjeta con los pesos normales o más ligeros (int8_float16): precisión, tiempo y VRAM.
  B. Las ayudas que no gastan VRAM: la pista de siempre, sin pista o con palabras clave (`hotwords`), y acercar lo oído a las órdenes y a tus programas.
  C. Un modelo pequeño de Ollama que corrija el texto, en la tarjeta y en la CPU: cuánto acierta, cuánto tarda y cuánta VRAM suma a Whisper.
No cambia ningún ajuste. Para Ollama solo baja un modelo si lo aceptas, con su tamaño delante."""
import gc
import shutil
import subprocess
import time

import requests

from lina.nucleo import acercar as ACE
from lina.nucleo import comandos as C
from lina.nucleo import idioma as IDI
from lina.nucleo import probar_voz as PV
from lina.nucleo import rutas as RUT
from lina.nucleo.constantes import OLLAMA
from lina.nucleo.idioma import T

TOPE_VRAM_MB = 4096
CANDIDATOS_OLLAMA = [("qwen2.5:1.5b", 1000), ("qwen2.5:3b", 1900), ("llama3.2:3b", 2000), ("gemma3:1b", 800)]      # (modelo, MB aproximados en disco)
INFORME = PV.CARPETA / "informe-mas.txt"

# Cosas mal oídas (lo que Whisper suele soltar) y lo que quisiste decir. Las dos últimas son largas.
ERRORES = {
    "es": [("Pausas", "Pausa"), ("Por música", "Pon música"), ("Sube lo loven", "Sube el volumen"), ("Silencia al sonido", "Silencia el sonido"),
           ("Buscar fetas de tortillas de patatas", "Busca recetas de tortilla de patatas"), ("Abre fire fox", "Abre Firefox"), ("Abre dolfin", "Abre Dolphin"),
           ("Cierra esta ventanas", "Cierra esta ventana"), ("Concecta los auriculares", "Conecta los auriculares"), ("Cómo va la gráfico", "Cómo va la gráfica"),
           ("Abre cait y escribe una nota para mañana comprar leche", "Abre Kate y escribe una nota para mañana comprar leche"),
           ("Pon la canción de queen bohemian rapsodi en el reproductor", "Pon la canción de Queen Bohemian Rhapsody en el reproductor")],
    "en": [("Paws", "Pause"), ("Bay music", "Play music"), ("Turn the volume of", "Turn the volume up"), ("Mute the sound", "Mute the sound"),
           ("Open fire fox", "Open Firefox"), ("Open dolfin", "Open Dolphin"), ("Close this windows", "Close this window")],
}
# Frases largas y normales, sin ningún fallo: sirven para ver cuánto estropea cada ayuda lo que ya estaba bien.
CONTROL = {
    "es": ["Escribe una nota para mañana con la lista de la compra", "Dime qué tiempo hace en Zaragoza esta tarde", "Busca una receta de pasta con tomate y albahaca",
           "Cambia el fondo de pantalla por una foto de montañas", "Mira si hay actualizaciones pendientes en el sistema",
           "Quiero que me expliques cómo funciona la memoria de vídeo", "Abre la carpeta de descargas y ordena los archivos por fecha"],
    "en": ["Write a note for tomorrow with the shopping list", "Tell me what the weather is like in Zaragoza this afternoon"],
}


def vocabulario_propio():
    """Tus términos y programas: lo que usa Lina para la pista de voz, más los nombres que aparecen en las frases de prueba."""
    try:
        from lina.nucleo.asistente import prompt_whisper
        texto = prompt_whisper()
    except Exception:
        texto = ""
    propios = [t.strip() for t in texto.split(".")[0].split(",") if t.strip()]
    for extra in ("Firefox", "Dolphin", "Kate", "Steam"):
        if C.normalizar(extra) not in {C.normalizar(p) for p in propios}:
            propios.append(extra)
    return propios[:80]


# ======================= VRAM =======================
def vram_usada_mb():
    return PV._vram_mb()


def _mas(base, ahora):
    return (ahora - base) if base is not None and ahora is not None else None


# ======================= A y B: Whisper =======================
def _transcribir_todo(transcribir, audios, **extra):
    salida = []
    for audio in audios:
        t0 = time.time()
        texto = transcribir(audio, **extra)
        salida.append((texto, time.time() - t0))
    return salida


def _cargar_gpu(calculo, modelo="large-v3-turbo"):
    """→ (transcribir(audio, pista=None, palabras=None), liberar). Falla con la excepción de faster-whisper si no hay tarjeta."""
    from faster_whisper import WhisperModel

    from lina.nucleo import cuda as CUDA
    CUDA.cargar_librerias()
    m = WhisperModel(modelo, device="cuda", compute_type=calculo)

    def transcribir(audio, pista=None, palabras=None):
        segmentos, _ = m.transcribe(audio, language=IDI.actual(), vad_filter=True, initial_prompt=pista or None, hotwords=palabras or None)
        return " ".join(s.text for s in segmentos).strip()
    return transcribir, lambda: None


def medir_whisper(audios, esperadas, vocabulario, pista, cargar=_cargar_gpu, vram=vram_usada_mb):
    """→ una fila por (cálculo, variante) con sus textos. Cada cálculo se carga y se suelta del todo antes de probar el siguiente, para medir su VRAM sin mezclar."""
    resultados = []
    for calculo in ("float16", "int8_float16"):
        base = vram()
        try:
            transcribir, _ = cargar(calculo)
        except Exception as e:
            resultados.append({"calculo": calculo, "error": f"{type(e).__name__}: {str(e)[:140]}"})
            continue
        ocupa = _mas(base, vram())
        transcribir(audios[0], pista=pista)                               # calentar
        for nombre, extra in (("pista de siempre", {"pista": pista}), ("sin pista", {}), ("palabras clave", {"palabras": ", ".join(vocabulario)})):
            res = _transcribir_todo(transcribir, audios, **extra)
            r = PV.resumir(esperadas, res)
            r.update(calculo=calculo, variante=nombre, vram_mb=ocupa, textos=[t for t, _ in res])
            resultados.append(r)
        del transcribir
        gc.collect()
    return resultados


def calculo_elegido(resultados):
    """float16, salvo que el ligero no acierte menos con la pista de siempre (entonces gana por gastar menos)."""
    acierto = {r["calculo"]: r["aciertos"] for r in resultados if "error" not in r and r["variante"] == "pista de siempre"}
    if "int8_float16" in acierto and acierto["int8_float16"] >= acierto.get("float16", -1):
        return "int8_float16"
    return "float16" if "float16" in acierto else None


def medir_acercar(esperadas, resultados, vocabulario, idioma, umbrales):
    """Para cada resultado de Whisper: aciertos tras acercar, y cuántas veces estropea una frase que ya estaba bien (control)."""
    filas = []
    ordenes = ACE.ordenes_para(idioma, vocabulario)
    control = list(esperadas) + CONTROL.get(idioma, CONTROL["es"])
    for nombre, (uf, up) in umbrales.items():
        estropea = sum(1 for f in control if ACE.acercar(f, ordenes, vocabulario, uf, up)[0].strip() != f.strip())
        for r in resultados:
            if "error" in r:
                continue
            nuevos = [ACE.acercar(t, ordenes, vocabulario, uf, up)[0] for t in r["textos"]]
            filas.append({"calculo": r["calculo"], "variante": r["variante"], "umbral": nombre, "estropea": estropea, "total_control": len(control),
                          "aciertos": sum(1 for e, t in zip(esperadas, nuevos) if PV.acierta(e, t)), "total": len(esperadas)})
    return filas


# ======================= C: Ollama =======================
SISTEMA = ("Eres un corrector de texto dictado por voz. El texto viene de un reconocimiento de voz que puede haber oído mal alguna palabra. "
           "Corrige SOLO palabras mal oídas, usando las órdenes y los nombres de programas que te doy. Si el texto ya está bien, devuélvelo igual. "
           "No respondas a la petición, no la ejecutes y no añadas nada. Responde únicamente un JSON: {\"texto\": \"…\"}")


def prompt_usuario(texto, ordenes, vocabulario):
    return f"Órdenes conocidas: {'; '.join(ordenes[:25])}\nProgramas y términos: {', '.join(vocabulario[:40])}\nTexto: {texto}"


def hay_ollama(url=OLLAMA, http=requests):
    try:
        return http.get(f"{url}/api/tags", timeout=2).json().get("models", [])
    except (requests.RequestException, ValueError, AttributeError):
        return None


def corregir_con_ollama(modelo, texto, ordenes, vocabulario, cpu=False, url=OLLAMA, http=requests, mantener="3m", sistema=None):
    opciones = {"temperature": 0, "num_predict": 120}
    if cpu:
        opciones["num_gpu"] = 0
    r = http.post(f"{url}/api/chat", timeout=120, json={
        "model": modelo, "stream": False, "format": "json", "keep_alive": mantener, "options": opciones,
        "messages": [{"role": "system", "content": sistema or SISTEMA}, {"role": "user", "content": prompt_usuario(texto, ordenes, vocabulario)}]})
    r.raise_for_status()
    import json
    contenido = r.json()["message"]["content"]
    try:
        return str(json.loads(contenido).get("texto", "")).strip() or texto
    except ValueError:
        return texto


def descargar_ollama(modelo, url=OLLAMA, http=requests):
    programa = shutil.which("ollama")
    if programa:
        return subprocess.run([programa, "pull", modelo], check=False).returncode == 0
    return False


def soltar_modelo(modelo, url=OLLAMA, http=requests):
    """Pide a Ollama que descargue el modelo de la memoria ya (si no, el siguiente se mediría con éste todavía cargado)."""
    try:
        http.post(f"{url}/api/generate", json={"model": modelo, "keep_alive": 0}, timeout=20)
    except requests.RequestException:
        pass
    time.sleep(1.0)


def medir_ollama(modelos, idioma, vocabulario, esperadas, base_mb, whisper_mb, vram=vram_usada_mb, corregir=corregir_con_ollama, soltar=soltar_modelo):
    """→ filas por (modelo, procesador). `base_mb` es la VRAM usada antes de cargar Whisper; `whisper_mb` lo que ocupa Whisper ya cargado."""
    ordenes = ACE.ordenes_para(idioma, vocabulario)
    casos = ERRORES.get(idioma, ERRORES["es"])
    control = list(esperadas) + CONTROL.get(idioma, CONTROL["es"])
    filas = []
    for modelo in modelos:
        for cpu in (False, True):
            try:
                t0 = time.time()
                corregir(modelo, casos[0][0], ordenes, vocabulario, cpu)         # primera llamada: incluye cargar el modelo
                frio = time.time() - t0
                total = _mas(base_mb, vram())                                    # Whisper + este modelo, juntos
                tiempos, bien, estropea = [], 0, 0
                for oido, quiso in casos:
                    t0 = time.time()
                    salida = corregir(modelo, oido, ordenes, vocabulario, cpu)
                    tiempos.append(time.time() - t0)
                    bien += int(PV.acierta(quiso, salida))
                for frase in control:
                    estropea += int(not PV.acierta(frase, corregir(modelo, frase, ordenes, vocabulario, cpu)))
            except Exception as e:
                filas.append({"modelo": modelo, "cpu": cpu, "error": f"{type(e).__name__}: {str(e)[:140]}"})
                continue
            finally:
                soltar(modelo)
            solo = None if total is None or whisper_mb is None else max(0, total - whisper_mb)
            filas.append({"modelo": modelo, "cpu": cpu, "bien": bien, "de": len(casos), "estropea": estropea, "de_control": len(control),
                          "frio_s": frio, "media_s": sum(tiempos) / len(tiempos), "larga_s": tiempos[-1], "vram_mb": solo, "total_mb": total})
    return filas


# ======================= informe =======================
def informe(whisper, acercar, ollama, vram_whisper_mb, calculo=None):
    L = [T("SEGUNDA TANDA  (tope de memoria de vídeo que quieres: {mb} MB)", mb=TOPE_VRAM_MB), ""]
    L.append(T("A y B · WHISPER EN LA TARJETA (frases tuyas, de 15)"))
    L.append(f"{'':<34}{T('aciertos'):>10}{T('media'):>9}{T('VRAM'):>11}")
    for r in whisper:
        if "error" in r:
            L.append(f"{r['calculo']:<34}{T('no disponible')}: {r['error']}")
            continue
        vram = f"{r['vram_mb']} MB" if r.get("vram_mb") is not None else "-"
        L.append(f"{r['calculo'] + ' · ' + r['variante']:<34}{r['aciertos']:>6}/{r['total']:<3}{r['media_s']:>7.2f} s{vram:>11}")
    L += ["", T("ACERCAR A ÓRDENES Y PROGRAMAS (sin VRAM). «Estropea» = frases que ya estaban bien y cambia mal.")]
    for f in acercar:
        L.append(f"{f['calculo'] + ' · ' + f['variante'] + ' · ' + f['umbral']:<52}{f['aciertos']:>4}/{f['total']:<3}  {T('estropea')} {f['estropea']}/{f['total_control']}")
    L += ["", T("C · OLLAMA CORRIGIENDO EL TEXTO (con Whisper {c} cargado, que ocupa {w} MB; «total» es todo junto)", c=calculo or "?", w=vram_whisper_mb if vram_whisper_mb is not None else "?")]
    L.append(f"{'':<28}{T('bien'):>8}{T('estropea'):>10}{T('1.ª vez'):>9}{T('media'):>9}{T('VRAM'):>10}{T('total'):>10}")
    for r in ollama:
        etiqueta = f"{r['modelo']} · {'CPU' if r['cpu'] else 'tarjeta'}"
        if "error" in r:
            L.append(f"{etiqueta:<28}{T('no disponible')}: {r['error']}")
            continue
        vram = f"{r['vram_mb']} MB" if r.get("vram_mb") is not None else "-"
        total = "-" if r.get("total_mb") is None else f"{r['total_mb']} MB" + (" ⚠" if r["total_mb"] > TOPE_VRAM_MB else "")
        L.append(f"{etiqueta:<28}{r['bien']:>5}/{r['de']:<2}{r['estropea']:>7}/{r['de_control']:<2}{r['frio_s']:>7.1f} s{r['media_s']:>7.2f} s{vram:>10}{total:>10}")
    return "\n".join(L)


def principal(argv, salida=print, entrada=input, cargar=_cargar_gpu, http=requests):
    lista = PV.frases()
    if not all(PV.ruta_audio(i).exists() for i in range(len(lista))):
        salida(T("Primero graba las frases:  lina probar-voz"))
        return 1
    idioma = IDI.actual()
    audios = [PV.leer_wav(PV.ruta_audio(i)) for i in range(len(lista))]
    vocabulario = vocabulario_propio()
    pista = PV._pista()
    salida(T("Midiendo Whisper en la tarjeta con pesos normales y ligeros…"))
    whisper = medir_whisper(audios, lista, vocabulario, pista, cargar=cargar)
    umbrales = {"estricto": (0.86, 0.88), "flexible": (0.78, 0.80)}
    acercadas = medir_acercar(lista, [r for r in whisper if "error" not in r], vocabulario, idioma, umbrales)
    calculo = calculo_elegido(whisper)
    ollama, vram_w = [], None
    instalados = hay_ollama(http=http)
    if calculo is None:
        salida(T("Whisper no ha cargado en la tarjeta: me salto la parte C (no puedo medir el total)."))
    elif instalados is None:
        salida(T("Ollama no responde en {url}: me salto la parte C. Instálalo o arráncalo y repite.", url=OLLAMA))
    else:
        tengo = {m.get("name", "") for m in instalados}
        modelos = [m for m, _ in CANDIDATOS_OLLAMA if m in tengo]
        faltan = [(m, mb) for m, mb in CANDIDATOS_OLLAMA if m not in tengo]
        if faltan and shutil.which("ollama"):
            salida(T("Modelos pequeños de Ollama que no tienes: {lista}.", lista=", ".join(f"{m} (~{mb} MB)" for m, mb in faltan)))
            if entrada(T("¿Los bajo para probarlos? [s/N] ")).strip().lower() in ("s", "si", "sí", "y", "yes"):
                modelos += [m for m, _ in faltan if descargar_ollama(m, http=http)]
        if modelos:
            salida(T("Midiendo Ollama ({n} modelos, tarjeta y CPU)…", n=len(modelos)))
            base = vram_usada_mb()
            transcribir, _ = cargar(calculo)                                  # Whisper se queda cargado mientras se mide Ollama
            vram_w = _mas(base, vram_usada_mb())
            ollama = medir_ollama(modelos, idioma, vocabulario, lista, base, vram_w)
            del transcribir
        else:
            salida(T("No hay ningún modelo pequeño de Ollama que probar."))
    texto = informe(whisper, acercadas, ollama, vram_w, calculo)
    salida("\n" + texto)
    try:
        RUT.DATOS.mkdir(parents=True, exist_ok=True)
        INFORME.write_text(texto + "\n", encoding="utf-8")
        salida(T("\nGuardado en {ruta}", ruta=INFORME))
    except OSError:
        pass
    return 0
