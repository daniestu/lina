# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-voz silencio [0.8,1.0,1.2,1.5]` (V3a): ¿cortaría frases el fin por silencio del atajo, y cuánto haría esperar?

Pasa tus grabaciones de `lina probar-voz` (las cortas y las tandas de `probar-voz grande`) por el detector (`voz/fin_de_frase.py`) con cada valor de silencio,
y compara lo que entiende Whisper con el audio cortado y con el completo. No graba, no usa la IA ni la red, no cambia nada: solo lee las grabaciones y
escribe el informe junto a ellas.

Tus grabaciones terminan donde pulsaste Intro, así que puede que no lleven el silencio final que el detector necesita para cortar. Para que eso no cuente
como «nunca corta», a cada una se le añade al final una cola sintética hecha con el ruido de fondo de la propia grabación (sus bloques más bajos). El
pitido de «te escucho» no está en estas grabaciones: lo cubren las pruebas del detector y se comprueba en vivo.
"""
import random
import time

import numpy as np

from lina.nucleo import ajustes as AJ
from lina.nucleo import directas as DIR
from lina.nucleo import idioma as IDI
from lina.nucleo import probar_voz as PV
from lina.nucleo import probar_voz_grande as PVG
from lina.nucleo import probar_voz_mas as MAS
from lina.nucleo.idioma import N_, T
from lina.voz import fin_de_frase as FDF

VALORES = (0.8, 1.0, 1.2, 1.5)
MARGEN_COLA = 3.0                  # segundos de cola por encima del silencio más largo que se mide
INFORME = "informe-silencio.txt"


def cola_de_fondo(audio, segundos, semilla=0):
    """`segundos` de ruido de fondo de la propia grabación: sus bloques de 30 ms más bajos (el 20 %, al menos 5), en un orden mezclado fijo."""
    bloques = FDF.trocear(audio)
    if not bloques:
        return np.zeros(int(segundos * FDF.FRECUENCIA), dtype=np.float32)
    bajos = sorted(bloques, key=lambda b: float(np.sqrt(np.mean(b * b))))[:max(5, len(bloques) // 5)]
    azar = random.Random(semilla)
    n = int(np.ceil(segundos / FDF.SEG_BLOQUE))
    return np.concatenate([bajos[azar.randrange(len(bajos))] for _ in range(n)]).astype(np.float32)


def igual(completo, cortado):
    """¿Lina entendería lo mismo? Mismo texto (normalizado) o, si es una orden directa, la misma orden con los mismos datos."""
    if PV.acierta(completo, cortado):
        return True
    return DIR.entender(completo) is not None and PVG.entiende_igual(completo, cortado)


def medir_tanda(grabaciones, transcribir, valores=VALORES, sensibilidad=0.012, espera_inicial=6.0):
    """grabaciones = [(frase, audio)]. → {valor: números} y los ejemplos de frases cortadas."""
    cola_seg = max(valores) + MARGEN_COLA
    completos = {}
    resultado, ejemplos = {}, []
    for v in valores:
        r = {"frases": len(grabaciones), "cortadas": 0, "antes": 0, "sin_voz": 0, "nunca": 0, "esperas": [], "frente_a_pulsar": []}
        for i, (frase, audio) in enumerate(grabaciones):
            con_cola = np.concatenate([audio, cola_de_fondo(audio, cola_seg, semilla=i)])
            fin, corte, espera = FDF.donde_termina(con_cola, silencio_fin=v, umbral_min=sensibilidad, espera_inicial=espera_inicial)
            if fin == FDF.NADA:
                r["sin_voz"] += 1
                continue
            if fin is None:
                r["nunca"] += 1
                continue
            r["esperas"].append(espera)
            r["frente_a_pulsar"].append((corte - len(audio)) / FDF.FRECUENCIA)
            if corte >= len(audio):
                continue                                         # corta en la cola: tiene todo lo que dijiste
            r["antes"] += 1                                      # oyó un silencio largo dentro de tu grabación, antes de tu Intro
            if i not in completos:
                completos[i] = transcribir(audio)
            cortado = transcribir(audio[:corte])
            if not igual(completos[i], cortado):
                r["cortadas"] += 1
                ejemplos.append((v, frase, completos[i], cortado))
        resultado[v] = r
    return resultado, ejemplos


def _tandas():
    """[(etiqueta, [(frase, ruta)])] de lo que hay grabado: las cortas y las de probar-voz grande."""
    tandas = []
    cortas = [(f, PV.CARPETA / f"frase{i + 1:02d}.wav") for i, f in enumerate(PV.FRASES.get(IDI.actual(), PV.FRASES["es"]))]
    cortas = [(f, r) for f, r in cortas if r.exists()]
    if cortas:
        tandas.append((T("cortas"), cortas))
    lista = PVG.frases() if IDI.actual() == "es" else []
    for nombre, ruido, nivel in PVG.tandas_grabadas():
        hay = [(lista[i][0], PVG.ruta(i, ruido, nivel)) for i in range(len(lista)) if PVG.ruta(i, ruido, nivel).exists()]
        if hay:
            tandas.append((PVG.etiqueta_de(nombre), hay))
    return tandas


def _media(xs):
    return sum(xs) / len(xs) if xs else 0.0


COLUMNAS = (N_("silencio"), N_("frases"), N_("antes de tu Intro"), N_("cortadas"), N_("sin voz"), N_("nunca corta"), N_("espera media"), N_("espera máx."), N_("frente a tu Intro"))


def informe(por_tanda, ejemplos, sensibilidad):
    L = [T("FIN DE FRASE POR SILENCIO (atajo) · ¿corta frases y cuánto hace esperar?"), ""]
    for etiqueta, res in por_tanda:
        L.append(f"{etiqueta}:")
        filas = [tuple(T(c) for c in COLUMNAS)]
        for v, r in res.items():
            filas.append((f"{v:.1f} s", r["frases"], r["antes"], r["cortadas"], r["sin_voz"], r["nunca"], f"{_media(r['esperas']):.2f} s",
                          f"{max(r['esperas'], default=0):.2f} s", f"{_media(r['frente_a_pulsar']):+.2f} s"))
        anchos = [max(len(str(f[i])) for f in filas) for i in range(len(filas[0]))]
        L += ["  " + "  ".join(str(c).rjust(anchos[i]) for i, c in enumerate(f)) for f in filas]
        L.append("")
    if ejemplos:
        L.append(T("Frases que cambian al cortarlas (silencio · dijiste · con todo el audio → cortado):"))
        L += [f"  {v:.1f} s · «{f}» · «{c}» → «{x}»" for v, f, c, x in ejemplos[:15]]
        L.append("")
    L += [T("Cómo leerlo:"),
          T("  · antes de tu Intro: corta dentro de tu grabación, en un silencio tuyo (si no, corta en la cola sintética, cuando ya habías terminado)."),
          T("  · cortadas: Lina entendería otra cosa con el audio cortado que con el completo (otro texto, o otra orden directa)."),
          T("  · sin voz: el detector no oyó voz en los primeros segundos (con el atajo diría «No te he oído»)."),
          T("  · nunca corta: no llegó a oír el silencio; tendrías que pulsar, como hoy."),
          T("  · espera: desde que acaba tu voz hasta que corta. Frente a tu Intro: + es que Lina tardaría más que tú en pulsar, − que menos."),
          T("  · Tus grabaciones terminan donde pulsaste Intro: a cada una se le añade al final una cola sintética con el ruido de fondo de la propia grabación "
            "(sus bloques más bajos), para que la falta de silencio final no cuente como «nunca corta»."),
          T("  · El pitido de «te escucho» no está en estas grabaciones (lo cubren las pruebas del detector; se comprueba en vivo)."),
          T("  · Sensibilidad usada: {s} (activacion.sensibilidad).", s=sensibilidad)]
    return "\n".join(L)


def principal(argv, salida=print, cargar=MAS._cargar_gpu):
    valores = VALORES
    if argv:
        try:
            valores = tuple(sorted({round(float(x), 2) for x in argv[0].split(",") if x.strip()}))
            if not valores or not all(0.3 <= v <= 3.0 for v in valores):
                raise ValueError
        except ValueError:
            salida(T("Uso:  lina probar-voz silencio [0.8,1.0,1.2,1.5]   (segundos de silencio, entre 0.3 y 3)"))
            return 2
    tandas = _tandas()
    if not tandas:
        salida(T("No hay grabaciones. Grábalas con  lina probar-voz  (y  lina probar-voz grande)."))
        return 1
    sensibilidad = float(AJ.solo_lectura().get("activacion", "sensibilidad"))
    try:
        transcribir_crudo, _ = cargar("int8_float16")
    except Exception as e:
        salida(T("Whisper no ha cargado en la tarjeta ({error}).", error=f"{type(e).__name__}: {str(e)[:120]}"))
        return 1
    pista = PV._pista()

    def transcribir(audio):
        return transcribir_crudo(audio, pista=pista)
    por_tanda, ejemplos = [], []
    for etiqueta, lista in tandas:
        salida(T("{etiqueta}: {n} grabaciones…", etiqueta=etiqueta, n=len(lista)))
        t0 = time.time()
        try:
            res, ej = medir_tanda([(f, PV.leer_wav(r)) for f, r in lista], transcribir, valores, sensibilidad)
        except Exception as e:                                 # Whisper puede cargar y fallar al transcribir (faltan librerías de CUDA…)
            salida(T("Whisper no ha cargado en la tarjeta ({error}).", error=f"{type(e).__name__}: {str(e)[:120]}"))
            return 1
        por_tanda.append((etiqueta, res))
        ejemplos += [(v, f, c, x) for v, f, c, x in ej]
        salida(T("  hecho en {s:.0f} s", s=time.time() - t0))
    texto = informe(por_tanda, ejemplos, sensibilidad)
    salida("\n" + texto)
    try:
        (PV.CARPETA / INFORME).write_text(texto + "\n", encoding="utf-8")
        salida(T("\nGuardado en {ruta}", ruta=PV.CARPETA / INFORME))
    except OSError:
        pass
    return 0
