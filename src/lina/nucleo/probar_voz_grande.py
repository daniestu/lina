# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-voz grande`: la prueba de verdad, con unas 100 frases tuyas, para saber si un corrector local (Ollama) sirve.

  lina probar-voz grande            graba las frases que falten (se puede parar con Ctrl+C y seguir otro día)
  lina probar-voz grande --ruido    lo mismo con música sonando, sin tocar su volumen (el peor caso)
  lina probar-voz grande --bajando[=N]   lo mismo con música, pero bajándola a N % al hablar, como hace Lina de verdad (N por defecto: tu ajuste, 20)
  lina probar-voz grande medir      pasa todas tus grabaciones por Whisper y cuenta lo que se entiende en cada situación
  lina probar-voz grande medir --ollama   además prueba modelos de Ollama como corrector (en las pruebas no sirvieron)

Lo que se mide es lo que importa: ¿Lina entiende la orden? Para las órdenes rápidas se mira si `directas` las reconoce igual que si las hubiera
escrito bien, y qué pasa con y sin corrector; para el resto, si el texto sale idéntico. Con los textos reales de Whisper, no con errores inventados."""
import re
import time

from lina.nucleo import acercar as ACE
from lina.nucleo import ajustes as AJ
from lina.nucleo import comandos as C
from lina.nucleo import directas as DIR
from lina.nucleo import idioma as IDI
from lina.nucleo import probar_voz as PV
from lina.nucleo import probar_voz_mas as MAS
from lina.nucleo.idioma import T
from lina.voz import atenuador as ATE

# Órdenes que Lina hace sin llamar a la IA (`directas`): se mide si las reconoce.
DIRECTAS_ES = [
    "Abre Firefox", "Abre Dolphin", "Abre Steam", "Abre Spotify", "Abre Discord", "Abre Kate", "Abre la terminal", "Abre Brave", "Abre Telegram",
    "Abre OBS", "Abre Heroic", "Ábreme Konsole", "Puedes abrir Dolphin", "Ábreme Steam",
    "Sube el volumen", "Baja el volumen", "Sube un poco el volumen", "Baja un poco el volumen", "Silencia el sonido", "Quita el silencio",
    "Maximiza esta ventana", "Minimiza esta ventana", "Pantalla completa", "Muestra el escritorio",
    "Pausa", "Pausa la música", "Reanuda la música", "Sigue con la música", "Siguiente canción", "Canción anterior", "Para la música",
    "Conecta mis auriculares", "Desconecta los auriculares", "Desconecta el mando", "Enciende el bluetooth", "Conecta el altavoz",
    "Qué hora es", "Qué día es hoy",
]
# Frases largas o con detalle, que van a la IA. Sin números (Whisper los escribe en cifras y no se podrían comparar).
LARGAS_ES = [
    "Pon música", "Pon música de Queen", "Pon la canción Bohemian Rhapsody de Queen", "Búscame una receta de tortilla de patatas", "Abre Firefox y busca recetas de tortilla",
    "Dime qué tiempo hace en Zaragoza esta tarde", "Escribe una nota para mañana con la lista de la compra", "Recuérdame llamar a mi madre dentro de una hora",
    "Pon un temporizador de un minuto", "Cuántos juegos tengo instalados en Steam", "Cómo va la gráfica", "Está bien mi equipo para jugar",
    "Cambia el fondo de pantalla por una foto de montañas", "Activa el modo oscuro", "Mira si hay actualizaciones pendientes en el sistema",
    "Cuánta memoria RAM estoy usando ahora mismo", "Cuánto espacio libre me queda en el disco", "Cierra todas las ventanas de Firefox",
    "Abre la carpeta de descargas y ordena los archivos por fecha", "Crea una carpeta nueva en documentos que se llame facturas",
    "Qué aplicaciones tengo abiertas ahora mismo", "Pon la pantalla al brillo máximo", "Activa MangoHud en Skyrim", "Cuál es la mejor versión de Proton para este juego",
    "Lanza Cyberpunk con GameMode activado", "Recuerda que mi navegador favorito es Brave", "Qué recuerdas de mí", "Olvida lo del navegador",
    "Apaga el ordenador dentro de media hora", "Léeme lo que hay en el portapapeles", "Resume esta página web", "Traduce al inglés lo que acabo de copiar",
    "Haz una captura de pantalla de esta ventana", "Conecta el wifi de casa", "Qué dispositivos bluetooth tengo y qué batería tienen",
    "Dime la temperatura de la tarjeta gráfica", "Pon el volumen de Spotify más bajo que el de Discord", "Busca en internet cuál es la capital de Australia",
    "Escribe un correo a Laura diciéndole que llego tarde", "Cuéntame un chiste corto", "Cuál es el atajo para cambiar de escritorio",
    "Cambia el idioma del teclado a inglés", "Qué ventana tengo en primer plano", "Activa la luz nocturna", "Instala el programa VLC", "Desinstala Discord",
    "Reinicia el servicio de bluetooth", "Abre Heroic y lanza el último juego que jugué", "Cierra Steam y vuelve a abrirlo", "Cuántas horas he jugado a Skyrim",
    "Prepara una copia de seguridad de mis documentos", "Dime cuánto consume la gráfica ahora", "Quiero que me expliques cómo funciona la memoria de vídeo",
]
SISTEMA = ("Eres un corrector de texto dictado por voz. El texto viene de un reconocimiento de voz que puede haber oído mal alguna palabra. "
           "Corrige SOLO palabras mal oídas, usando las órdenes y los nombres de programas que te doy. Si el texto ya tiene sentido, devuélvelo EXACTAMENTE igual: "
           "no lo reformules, no cambies palabras correctas ni añadas puntuación. No respondas a la petición ni la ejecutes. "
           "Ejemplos: «Abre fire fox» → «Abre Firefox»; «Baja el bolumen» → «Baja el volumen»; «Cuéntame una historia» → «Cuéntame una historia». "
           "Responde únicamente un JSON: {\"texto\": \"…\"}")


def frases():
    """[(frase, es_directa)] en un orden mezclado y fijo (para no leer 40 órdenes seguidas)."""
    d = [(f, True) for f in DIRECTAS_ES]
    g = [(f, False) for f in LARGAS_ES]
    salida = []
    for i in range(max(len(d), len(g))):
        salida += [x for x in (d[i] if i < len(d) else None, g[i] if i < len(g) else None) if x]
    return salida


def nombre_carpeta(ruido=False, nivel=None):
    if nivel is not None:
        return f"grande-ruido-bajando{int(nivel)}"
    return "grande-ruido" if ruido else "grande"


def carpeta(ruido=False, nivel=None):
    return PV.CARPETA / nombre_carpeta(ruido, nivel)


def ruta(i, ruido=False, nivel=None):
    return carpeta(ruido, nivel) / f"frase{i + 1:03d}.wav"


def etiqueta_de(nombre):
    """Cómo se llama en el informe cada tanda grabada."""
    m = re.fullmatch(r"grande-ruido-bajando(\d+)", nombre)
    if m:
        return T("con ruido bajando al {n} %", n=m.group(1))
    return T("con ruido") if nombre == "grande-ruido" else T("en silencio")


def tandas_grabadas():
    """[(nombre_de_carpeta, ruido, nivel)] de lo que hay grabado, en silencio primero."""
    salida = []
    if not PV.CARPETA.exists():
        return salida
    for d in sorted(PV.CARPETA.iterdir()):
        m = re.fullmatch(r"grande(?:-ruido(?:-bajando(\d+))?)?", d.name)
        if d.is_dir() and m:
            salida.append((d.name, d.name != "grande", int(m.group(1)) if m.group(1) else None))
    salida.sort(key=lambda x: (x[1], x[2] is not None, x[2] or 0))
    return salida


def grabar_bajando(nivel, grabar=PV.grabar_una, atenuador=None):
    """Una grabación que baja lo que suena a `nivel` % justo al empezar y lo devuelve al terminar, como hace Lina con el atajo."""
    def _grabar(entrada=input, salida=print):
        a = atenuador or ATE.Atenuador(nivel=nivel, log=lambda m: None)
        paso = {"n": 0}

        def entrada_con_bajada(mensaje):
            r = entrada(mensaje)
            paso["n"] += 1
            try:
                if paso["n"] == 1:
                    a.bajar("prueba")
                    time.sleep(0.2)
                elif paso["n"] == 2:
                    a.subir("prueba")
            except Exception:
                pass
            return r
        try:
            return grabar(entrada=entrada_con_bajada, salida=salida)
        finally:
            try:
                a.subir("prueba", todos=True)
            except Exception:
                pass
    return _grabar


def grabar_todas(ruido=False, grabar=PV.grabar_una, salida=print, entrada=input, nivel=None):
    lista = frases()
    if nivel is not None:
        ruido = True
        grabar = grabar_bajando(nivel, grabar)
        salida(T("Pon música sonando con el volumen que sueles tener. Al empezar a grabar se bajará a un {n} % y al terminar volverá.", n=int(nivel)))
    elif ruido:
        salida(T("Pon música sonando con el volumen que sueles tener, y habla como lo haces siempre."))
    hechas = sum(1 for i in range(len(lista)) if ruta(i, ruido, nivel).exists())
    if hechas:
        salida(T("Ya tienes {n} de {total} grabadas; sigo por donde lo dejaste.", n=hechas, total=len(lista)))
    try:
        for i, (frase, _) in enumerate(lista):
            if ruta(i, ruido, nivel).exists():
                continue
            while True:
                salida(T("\nFrase {n} de {total}:  «{frase}»", n=i + 1, total=len(lista), frase=frase))
                audio = grabar(entrada=entrada, salida=salida)
                if len(audio) < PV.FRECUENCIA * 0.3:
                    salida(T("   No he oído nada; repítela."))
                    continue
                PV.guardar_wav(ruta(i, ruido, nivel), audio)
                break
    except (KeyboardInterrupt, EOFError):
        salida(T("\nParo aquí. Cuando quieras sigo por donde lo dejaste."))
    return sum(1 for i in range(len(lista)) if ruta(i, ruido, nivel).exists())


# ======================= medir =======================
def _app_resuelta(nombre):
    """El programa instalado al que llevaría ese nombre (como lo haría Lina de verdad, con su parecido de sonido), o None."""
    try:
        r = C.buscar_app(nombre)
    except Exception:
        return None
    return C.normalizar(r[0][1]["nombre"]) if r and r[0][0] >= 70 else None


def _datos_comparables(r):
    if r is None:
        return None
    ident, datos = r
    if ident == "abrir_app":                                      # «Torfin» y «Dolphin» son lo mismo si Lina los lleva al mismo programa
        return ident, _app_resuelta(datos.get("nombre", "")) or C.normalizar(datos.get("nombre", ""))
    return ident, {k: C.normalizar(v) if isinstance(v, str) else v for k, v in datos.items()}


def entiende_igual(esperada, texto):
    """¿`directas` entiende `texto` igual que la frase bien escrita? (misma orden y mismos datos; los programas, por el que Lina abriría)."""
    return _datos_comparables(DIR.entender(texto)) == _datos_comparables(DIR.entender(esperada))


def evaluar(lista, textos):
    """lista = [(frase, es_directa)], textos = lo que quedó (mismo orden). → números."""
    n_dir = sum(1 for _, d in lista if d)
    return {
        "texto_ok": sum(1 for (f, _), t in zip(lista, textos) if PV.acierta(f, t)), "total": len(lista),
        "directa_ok": sum(1 for (f, d), t in zip(lista, textos) if d and entiende_igual(f, t)), "directas": n_dir,
        "directa_falsa": sum(1 for (f, d), t in zip(lista, textos) if not d and DIR.entender(t) is not None),
    }


def comparar(lista, antes, despues):
    """Cuántas frases arregla y cuántas estropea el corrector (por texto idéntico), con ejemplos."""
    arregla, estropea = [], []
    for (f, _), a, d in zip(lista, antes, despues):
        if not PV.acierta(f, a) and PV.acierta(f, d):
            arregla.append((a, d))
        elif PV.acierta(f, a) and not PV.acierta(f, d):
            estropea.append((a, d))
    return arregla, estropea


def solo_si_no_es_directa(antes, corregido):
    """La política barata: si `directas` ya reconoce lo que dijo Whisper, no se llama al corrector."""
    return [a if DIR.entender(a) is not None else c for a, c in zip(antes, corregido)]


def transcribir_todo(lista, rutas, cargar, pista):
    transcribir, _ = cargar("int8_float16")
    audios = [PV.leer_wav(r) for r in rutas]
    transcribir(audios[0], pista=pista)
    textos, tiempos = [], []
    for a in audios:
        t0 = time.time()
        textos.append(transcribir(a, pista=pista))
        tiempos.append(time.time() - t0)
    return textos, sum(tiempos) / len(tiempos)


def fallos_whisper(lista, textos):
    """Lo que Whisper solo no deja idéntico: (dijiste, oyó, ¿era orden rápida?, ¿Lina la entiende igual aun así?)."""
    return [(f, t, d, d and entiende_igual(f, t)) for (f, d), t in zip(lista, textos) if not PV.acierta(f, t)]


def informe(condiciones, ollama, ejemplos, fallos=()):
    L = [T("PRUEBA GRANDE · lo que importa es si Lina entiende la orden"), ""]
    for nombre, base in condiciones:
        L.append(T("{nombre}: {n} frases · Whisper solo: texto idéntico {a}/{n}, órdenes rápidas entendidas {b}/{c}, órdenes rápidas falsas {d}",
                   nombre=nombre, n=base["total"], a=base["texto_ok"], b=base["directa_ok"], c=base["directas"], d=base["directa_falsa"]))
    L += ["", f"{'':<44}{T('texto ok'):>9}{T('órdenes'):>9}{T('falsas'):>8}{T('arregla'):>9}{T('estropea'):>10}{T('media'):>9}{T('VRAM'):>9}"]
    for f in ollama:
        etiqueta = f"{f['condicion']} · {f['modelo']} · {'CPU' if f['cpu'] else 'tarjeta'} · {f['politica']}"
        if "error" in f:
            L.append(f"{etiqueta:<44}{T('no disponible')}: {f['error']}")
            continue
        vram = f"{f['vram_mb']} MB" if f.get("vram_mb") is not None else "-"
        L.append(f"{etiqueta:<44}{f['texto_ok']:>9}{f['directa_ok']:>9}{f['directa_falsa']:>8}{f['arregla']:>9}{f['estropea']:>10}{f['media_s']:>7.2f} s{vram:>9}")
    for nombre, filas in fallos:
        L += ["", T("DÓNDE FALLA WHISPER SOLO ({nombre}):  [orden] = orden rápida; ✓ = Lina la entiende igual, ✗ = no", nombre=nombre)]
        L += [f"   {'[orden] ' + ('✓' if ok else '✗') if d else '[otra]  '}  «{f}» → «{t}»" for f, t, d, ok in filas]
    for titulo, filas in ejemplos:
        if filas:
            L += ["", titulo] + [f"   «{a}» → «{d}»" for a, d in filas[:12]]
    return "\n".join(L)


def principal(argv, salida=print, entrada=input, cargar=MAS._cargar_gpu, http=MAS.requests, grabar=PV.grabar_una):
    if IDI.actual() != "es":
        salida(T("Esta prueba grande solo está hecha en español por ahora."))
        return 1
    lista = frases()
    if "medir" not in argv:
        nivel, ruido = None, "--ruido" in argv
        for a in argv:
            if a == "--bajando" or a.startswith("--bajando="):
                try:
                    nivel = int(a.split("=", 1)[1]) if "=" in a else int(AJ.solo_lectura().get("sonido", "volumen_al_escuchar"))
                except (ValueError, TypeError):
                    nivel = 20
                nivel = max(0, min(100, nivel))
        hechas = grabar_todas(ruido, grabar=grabar, salida=salida, entrada=entrada, nivel=nivel)
        salida(T("\nTienes {n} de {total} grabadas. Cuando quieras medir:  lina probar-voz grande medir", n=hechas, total=len(lista)))
        return 0
    modelos = []
    if "--ollama" in argv:
        modelos = ["qwen2.5:3b", "qwen2.5:1.5b"]
        for a in argv:
            if a.startswith("--modelos="):
                modelos = [m for m in a.split("=", 1)[1].split(",") if m]
        instalados = MAS.hay_ollama(http=http)
        if instalados is None:
            salida(T("Ollama no responde en {url}. Arráncalo y repite (o quita --ollama).", url=MAS.OLLAMA))
            return 1
        tengo = {m.get("name", "") for m in instalados}
        modelos = [m for m in modelos if m in tengo]
        if not modelos:
            salida(T("No tienes ninguno de esos modelos en Ollama (prueba:  ollama pull qwen2.5:3b)."))
            return 1
    vocabulario = MAS.vocabulario_propio()
    ordenes = ACE.ordenes_para(IDI.actual(), vocabulario)
    pista = PV._pista()
    condiciones, ollama, ejemplos, fallos = [], [], [], []
    for carpeta_nombre, cond_ruido, cond_nivel in tandas_grabadas():
        nombre = etiqueta_de(carpeta_nombre)
        idx = [i for i in range(len(lista)) if ruta(i, cond_ruido, cond_nivel).exists()]
        if len(idx) < 20:
            salida(T("{nombre}: solo {n} grabaciones (hacen falta al menos 20); lo salto.", nombre=nombre, n=len(idx)))
            continue
        sub = [lista[i] for i in idx]
        salida(T("Whisper sobre {n} frases {nombre}…", n=len(sub), nombre=nombre))
        try:
            textos, _ = transcribir_todo(sub, [ruta(i, cond_ruido, cond_nivel) for i in idx], cargar, pista)
        except Exception as e:
            salida(T("Whisper no ha cargado en la tarjeta ({error}).", error=f"{type(e).__name__}: {str(e)[:120]}"))
            return 1
        base = evaluar(sub, textos)
        condiciones.append((nombre, base))
        fallos.append((nombre, fallos_whisper(sub, textos)))
        for modelo in modelos:
            for cpu in (False, True):
                salida(T("Ollama {modelo} en {donde} sobre {nombre}…", modelo=modelo, donde="CPU" if cpu else T("la tarjeta"), nombre=nombre))
                antes_vram = MAS.vram_usada_mb()
                tiempos, corregidos = [], []
                try:
                    MAS.corregir_con_ollama(modelo, textos[0], ordenes, vocabulario, cpu, http=http, sistema=SISTEMA)     # la primera vez carga el modelo: no cuenta
                    for t in textos:
                        t0 = time.time()
                        corregidos.append(MAS.corregir_con_ollama(modelo, t, ordenes, vocabulario, cpu, http=http, sistema=SISTEMA))
                        tiempos.append(time.time() - t0)
                    vram = MAS._mas(antes_vram, MAS.vram_usada_mb())
                except Exception as e:
                    ollama.append({"condicion": nombre, "modelo": modelo, "cpu": cpu, "politica": "", "error": f"{type(e).__name__}: {str(e)[:120]}"})
                    continue
                finally:
                    MAS.soltar_modelo(modelo, http=http)
                for politica, finales in ((T("siempre"), corregidos), (T("solo si no es orden"), solo_si_no_es_directa(textos, corregidos))):
                    ev = evaluar(sub, finales)
                    arregla, estropea = comparar(sub, textos, finales)
                    ollama.append({"condicion": nombre, "modelo": modelo, "cpu": cpu, "politica": politica, **ev, "arregla": len(arregla), "estropea": len(estropea),
                                   "media_s": sum(tiempos) / len(tiempos), "vram_mb": vram})
                    if modelo == modelos[0] and cpu and politica == T("siempre"):
                        ejemplos += [(T("Lo que {modelo} ARREGLA ({nombre})", modelo=modelo, nombre=nombre), arregla), (T("Lo que {modelo} ESTROPEA ({nombre})", modelo=modelo, nombre=nombre), estropea)]
    if not condiciones:
        salida(T("No hay grabaciones suficientes. Graba con:  lina probar-voz grande"))
        return 1
    texto = informe(condiciones, ollama, ejemplos, fallos)
    salida("\n" + texto)
    try:
        (PV.CARPETA / "informe-grande.txt").write_text(texto + "\n", encoding="utf-8")
        salida(T("\nGuardado en {ruta}", ruta=PV.CARPETA / "informe-grande.txt"))
    except OSError:
        pass
    return 0
