"""Probar y aprender ajustes de configuración (sobre todo de KDE): comprobar que surten efecto y guardarlos como receta."""
from lina.nucleo import autoconocimiento as AUTO
from lina.nucleo import ejecucion as EJ
from lina.nucleo import herramientas as H
from lina.nucleo import idioma as IDI
from lina.nucleo.registro import log
from lina.voz import voces as VOC
import os
import re
import shlex
import shutil


class MixinAjustes:
    def probar_ajuste_kde(self, args):
        """Escribe un ajuste de KDE, recarga el programa, abre su panel, LEE en pantalla qué valor muestra y lo compara con el esperado.
        Si no coincide, lo revierte. Así nunca se da por bueno algo que no tiene efecto."""
        ej = self.ejecutor
        archivo, clave = str(args.get("archivo") or "").strip(), str(args.get("clave") or "").strip()
        valor = str(args.get("valor") if args.get("valor") is not None else "").strip()
        panel, control = str(args.get("panel") or "").strip(), str(args.get("control") or "").strip()
        esperado, recargar = str(args.get("esperado") or "").strip(), str(args.get("recargar") or "").strip()
        ajuste, sinonimos = str(args.get("ajuste") or "").strip(), str(args.get("sinonimos") or "").strip()
        grupos = args.get("grupos")
        grupos = [grupos] if isinstance(grupos, str) else grupos
        nombre_ok = r"[\w][\w .@+:/-]*"
        if (not re.fullmatch(r"[\w][\w.@+/-]*", archivo) or ".." in archivo or not isinstance(grupos, list)
                or not all(isinstance(g, str) and re.fullmatch(nombre_ok, g) for g in grupos) or not re.fullmatch(nombre_ok, clave)
                or not valor or valor.startswith("-") or len(valor) > 200 or not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.+-]*", panel)
                or not control or not esperado):
            malos = [n for n, bien in (("archivo", bool(re.fullmatch(r"[\w][\w.@+/-]*", archivo)) and ".." not in archivo),
                                       ("grupos (una lista de textos)", isinstance(grupos, list) and all(isinstance(g, str) and re.fullmatch(nombre_ok, g) for g in grupos)),
                                       ("clave", bool(re.fullmatch(nombre_ok, clave))),
                                       ("valor", bool(valor) and not valor.startswith("-") and len(valor) <= 200),
                                       ("panel (nombre del kcm, p. ej. kcm_xxx)", bool(re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.+-]*", panel))),
                                       ("control (el texto del control en el panel)", bool(control)),
                                       ("esperado (el TEXTO que mostrará el panel)", bool(esperado))) if not bien]
            log("probar_ajuste_kde: datos no válidos (" + ", ".join(malos or ["?"]) + ")")
            return ("Datos no válidos para probar el ajuste. Falta o está mal: " + ", ".join(malos or ["algún campo"]) + ". "
                    "Corrígelo y vuelve a llamar (no pases a otro método sin haberlo intentado bien: así queda apuntado como receta).")
        if (recargar and len(valor) >= 3 and valor.lower() not in {"true", "false", "yes", "off"}
                and re.search(r"(?<![\w.-])" + re.escape(valor) + r"(?![\w.-])", recargar, re.I)):
            return (f"El comando de recarga contiene el valor que estás probando («{valor}»): eso APLICA el cambio por otra vía, falsea la comprobación "
                    "e invalida el revertido. Usa un comando que solo haga recargar el programa, o déjalo vacío (los paneles suelen leer del disco "
                    "al abrirse). No he escrito nada.")
        if self.modo_privado:                                  # comprobar un ajuste exige mirar el panel, y en modo privado no se mira nada
            return ("Modo privado: no puedo mirar el panel para comprobar el ajuste, así que no he escrito nada. Díselo al usuario: si quiere, que quite "
                    "el modo privado, o que te pida cambiarlo SIN comprobar (con kwriteconfig6, sin mirar la pantalla).")
        propios = {H._sin_acentos(x.lower()).strip() for x in list(grupos) + [clave]}
        if H._sin_acentos(control.lower()).strip() in propios:
            return (f"El «control» («{control}») es el nombre de un grupo o de la clave del archivo, no de algo que SE VE en el panel. Pon las "
                    "palabras exactas de un control de la pantalla (una etiqueta, un selector, un campo); si no sabes cómo se llama, abre el "
                    "panel y míralo con mirar_pantalla. No he escrito nada.")
        escribir = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5" if shutil.which("kwriteconfig5") else None
        if not escribir:
            return "No hay kwriteconfig6 en este equipo, así que no puedo escribir ese ajuste."
        problema = H._validar_panel_kde(f"kcmshell6 {panel}")
        if problema:
            return problema
        pregunta_panel = (f"En el panel de ajustes que está abierto, ¿qué valor muestra exactamente este control: {control}? "
                          "Responde solo con lo que se ve escrito en el control (por ejemplo «Tras 15 minutos»); si no ves "
                          "el panel o ese control, dilo.")
        conocida = _A.REC.probada_kde(archivo, list(grupos), clave, panel) if _A.REC is not None else None
        valor_en_archivo = None
        if conocida:       # receta ya demostrada: esta clave mueve este panel. Se salta la lectura previa (unos 6 s); la comprobación de DESPUÉS se mantiene
            antes, error_antes = None, None
            leer = "kreadconfig6" if shutil.which("kreadconfig6") else "kreadconfig5" if shutil.which("kreadconfig5") else None
            if leer:
                rc_, out_ = EJ._ejecutar_simple([leer, "--file", archivo] + [x for g in grupos for x in ("--group", g)] + ["--key", clave])
                valor_en_archivo = out_.strip() if rc_ == 0 else None
            log(f"Receta probada «{conocida.get('ajuste')}» ({conocida.get('id')}): no se lee el panel antes; en el archivo había «{valor_en_archivo}»")
        else:
            antes, error_antes = self._leer_panel_antes(panel, pregunta_panel)     # la REFERENCIA: sin saber cómo estaba, copiar lo que se ve como «esperado» daría por bueno un cambio que no hizo nada
        if antes and not error_antes and H.control_no_visible(antes):
            # El control que eligió la IA no existe en el panel (suele ser el idioma: el panel está en el idioma del usuario). Antes de escribir nada,
            # se le enseña qué muestra el panel de verdad, para que elija el control correcto a la primera.
            inventario, _ = self._leer_panel_antes(panel, "Lista TODOS los controles que se ven en esta ventana de ajustes: para cada uno, el texto "
                                                          "exacto de su etiqueta y el valor que muestra ahora. Una línea por control, sin comentarios.")
            log(f"Receta: el control «{control[:60]}» no está en el panel «{panel}»; se le enseña lo que muestra: {(inventario or '')[:300]}")
            if inventario and not H.control_no_visible(inventario):
                return (f"NO HE ESCRITO NADA: el panel «{panel}» no tiene ningún control llamado «{control}». Esto es lo que muestra de verdad (con los "
                        f"textos exactos, en el idioma del usuario):\n{inventario[:900]}\nElige de ahí el control que corresponde a lo que pide el usuario y "
                        "vuelve a llamar con ese texto exacto en «control» y, en «esperado», el texto que mostrará el panel tras el cambio (si no "
                        "sabes cuál será, usa el que verías con el ajuste ya aplicado).")
        antes = None if (error_antes or not antes or H.control_no_visible(antes)) else antes
        log(f"Lectura previa del panel «{panel}» (control «{control[:60]}»): {(antes or 'no se ha podido leer')[:300]}")
        if antes and H.coincide_visto(antes, esperado) and not H.visto_con_problema(antes, esperado):
            ej.duda, ej.efecto_sin_comprobar = "", False
            log(f"Receta NO apuntada: el panel «{panel}» ya mostraba lo esperado antes de tocar nada (no se ha demostrado ningún cambio)")
            return (f"YA ESTABA ASÍ: antes de tocar nada, el panel «{panel}» ya mostraba «{antes[:120]}», que es lo esperado ({esperado}). No he escrito "
                    "nada. Díselo al usuario tal cual (ya estaba así); no digas que lo has cambiado tú.")
        partes = [escribir, "--file", archivo] + [x for g in grupos for x in ("--group", g)] + ["--key", clave, valor]
        r1 = ej.herramienta({"comando": " ".join(shlex.quote(x) for x in partes), "motivo": f"probar {clave}={valor} en {archivo}"})
        if not r1.startswith("código de salida: 0"):
            return "No se ha podido escribir el ajuste (no se ha probado nada): " + r1[:400]
        id_escritura = (H.diario.listar(1) or [{}])[0].get("id") if H.diario else None      # para revertir EXACTAMENTE esta escritura
        aviso_rec = ""
        if recargar:
            r2 = self._recargar_interno(recargar, "recargar el programa tras el ajuste")
            aviso_rec = H.aviso_recarga(recargar, r2)
            if aviso_rec:
                log("La recarga no funcionó: " + " | ".join(r2.splitlines()[:2])[:200])
        ej.cerrar_paneles()
        ej.lanzar(f"kcmshell6 {panel}")
        texto, error = _A._ver_pantalla(self._claves("mini"), pregunta_panel, 3)
        ej.cerrar_paneles()
        log(f"Lectura del panel «{panel}» (control «{control[:60]}», esperado «{esperado[:60]}»): {(texto or error or '')[:400]}")
        if error:
            ej.duda = "no se pudo mirar el panel para comprobar el ajuste"
            return (f"NO SE HA PODIDO COMPROBAR: {error} El ajuste {clave}={valor} QUEDA ESCRITO en {archivo} pero sin saber si tiene efecto: "
                    "díselo al usuario, no lo des por hecho." + aviso_rec)
        problema = H.coincide_visto(texto, esperado) and H.visto_con_problema(texto, esperado)
        if H.coincide_visto(texto, esperado) and not problema:
            ej.duda, ej.efecto_sin_comprobar = "", False
            aprendida = None
            if antes or conocida:                              # solo se aprende lo DEMOSTRADO: antes era otra cosa y tras escribir es lo esperado (o ya estaba demostrado)
                aprendida = _A.REC.aprender_kde(ajuste, sinonimos, getattr(self, "pregunta_pura", ""), archivo, list(grupos), clave, valor, panel, control,
                                             esperado, recargar, web=bool(ej.contaminado))
            if aprendida:
                ej.receta_turno = True
            if not aprendida:
                log("Receta NO apuntada: " + ("no pude leer el panel ANTES de cambiar (sin referencia no se demuestra el cambio)" if not antes
                                              else "faltan datos (nombre del ajuste, archivo, clave o panel) o no tiene palabras concretas"))
            return (f"COMPROBADO EN PANTALLA: tras escribir {clave}={valor} en {archivo} (grupos {' / '.join(grupos) or 'raíz'}) el panel «{panel}» "
                    f"muestra «{texto[:120]}», que es lo esperado ({esperado}). El ajuste funciona y queda aplicado."
                    + (" (Receta ya probada: no leí el panel antes de cambiar" + (f"; el archivo ya tenía el valor {valor}, así que quizá ya estaba así" if valor_en_archivo == valor else "") + ".)" if conocida
                       else "" if antes else " (Nota: no pude leer el panel ANTES de cambiar, así que esto no demuestra del todo que el cambio tuviera efecto.)")
                    + (" Queda apuntado como receta para la próxima vez." if aprendida else "") + aviso_rec)
        _A.REC.fallo_kde(archivo, list(grupos), clave)             # si había una receta con esta clave, esta vez no ha funcionado (a la segunda seguida, se olvida)
        deshecho = ej.deshacer(id_escritura) if id_escritura else "No hay diario: no he podido revertirlo solo."
        if recargar:
            self._recargar_interno(recargar, "recargar el programa tras revertir")
        ej.duda_revertida = deshecho.startswith("Deshecho:")
        rev = (f"Lo he REVERTIDO ({deshecho.splitlines()[0][:150]})" if ej.duda_revertida else
               f"OJO: NO he podido revertirlo solo ({deshecho.splitlines()[0][:150]}); díselo al usuario o usa deshacer_cambio")
        if problema:
            ej.duda = f"el panel avisa de un problema con el valor {valor[:40]}"
            return (f"LA PANTALLA AVISA DE UN PROBLEMA: el panel «{panel}» menciona «{esperado}», pero para decir otra cosa (la pantalla dijo: "
                    f"«{texto[:160]}»). Eso NO cuenta como comprobado. {rev}. Lo más probable es que el VALOR «{valor}» no sea válido (que no "
                    "exista o no esté instalado): averigua cuáles son los valores válidos antes de reintentar. No le digas al usuario que está "
                    "hecho." + aviso_rec)
        if H.control_no_visible(texto):
            ej.duda = f"no se pudo comprobar el ajuste {clave}: el control «{control[:40]}» no se ve en el panel"
            return (f"NO SE HA PODIDO COMPROBAR: el panel «{panel}» no muestra el control «{control}» (la pantalla dijo: «{texto[:120]}»), así que no sé "
                    f"si la clave {clave} funciona. {rev}. El problema es el CONTROL "
                    "que elegiste o lo que esperabas ver, no necesariamente la clave: abre el panel (`kcmshell6 " + panel + "`), míralo con "
                    "mirar_pantalla para ver cómo se llama de verdad ese control y qué texto muestra, y vuelve a probar con eso en «control» y "
                    "«esperado». No le digas al usuario que está hecho." + aviso_rec)
        if antes is not None and not H.mismo_valor_visto(antes, texto):                  # algo cambió, aunque no a lo esperado
            ej.duda = f"el ajuste {clave} cambió el panel, pero no a lo esperado"
            return (f"EL PANEL CAMBIÓ, PERO NO A LO ESPERADO: antes mostraba «{antes[:100]}», tras escribir {clave}={valor} en {archivo} muestra "
                    f"«{texto[:120]}» y esperabas «{esperado}». {rev}. Esa clave SÍ tiene efecto (algo cambió). Si «{texto[:80]}» es lo que el usuario "
                    f"quería, repite la misma prueba con esperado=«{texto[:80]}» (recuerda: «esperado» es el TEXTO QUE MUESTRA el panel, no el valor del "
                    "archivo); si no lo es, prueba otro valor. No le digas al usuario que está hecho." + aviso_rec)
        ej.duda = f"el ajuste {clave} no tuvo efecto visible"
        return (f"NO TUVO EFECTO: tras escribir {clave}={valor} en {archivo} (grupos {' / '.join(grupos) or 'raíz'}) el panel «{panel}» muestra "
                f"«{texto[:120]}» y se esperaba «{esperado}» (ojo: «esperado» es el TEXTO QUE MUESTRA el panel, no el valor del archivo). {rev}. Esa clave o ese grupo no son los "
                "buenos, o la unidad no es la que usa el programa: prueba otra clave u otro grupo (buscar_clave_en_binarios, buscar_web u "
                "observar_config) y vuelve a probar. No le digas al usuario que está hecho." + aviso_rec)

    def _recargar_interno(self, comando, motivo):
        """El comando de recarga de probar_ajuste_kde es parte de la prueba, no un cambio del usuario: no se anota en el diario."""
        ej = self.ejecutor
        ej.sin_anotar = True
        try:
            return ej.herramienta({"comando": comando, "motivo": motivo})
        finally:
            ej.sin_anotar = False

    def _leer_panel_antes(self, panel, pregunta):
        """Abre el panel y lee lo que muestra ANTES de tocar nada. Es la referencia que hace que «comprobado» signifique «ha cambiado»."""
        ej = self.ejecutor
        ej.cerrar_paneles()
        ej.lanzar(f"kcmshell6 {panel}")
        texto, error = _A._ver_pantalla(self._claves("mini"), pregunta, 3)
        ej.cerrar_paneles()
        return texto, error

    def _guardar_receta(self, args):
        """La IA pide apuntar una receta. Solo se acepta lo que de verdad se ejecutó bien en ESTA petición y se comprobó después: nada que no se haya
        probado, y nada que no sea un simple cambio de ajuste."""
        cambiar, leer = " ".join(str(args.get("cambiar", "")).split()), " ".join(str(args.get("leer", "")).split())
        ajuste, comprobar = str(args.get("ajuste", "")).strip(), str(args.get("comprobar", "")).strip()
        if not ajuste or not cambiar or not comprobar:
            return "No guardo la receta: faltan el nombre del ajuste, el comando o cómo lo comprobaste."
        if len(cambiar) > 300 or len(leer) > 300:
            return "No guardo la receta: el comando es demasiado largo para ser un simple cambio de ajuste."
        if self.ejecutor.duda:
            return f"No guardo la receta: lo último que se hizo sigue con una duda sin resolver ({self.ejecutor.duda_corta()})."
        hechas = [(i, n, a, r) for i, (n, a, r) in enumerate(self.acciones_turno)]

        def bien_ejecutado(cmd):
            return [i for i, n, a, r in hechas if n == "ejecutar_comando" and " ".join(str((a or {}).get("comando", "")).split()) == cmd and H._codigo_de_salida(r) == 0]
        donde = bien_ejecutado(cambiar)
        if not donde:
            return "No guardo la receta: ese comando no se ejecutó bien en esta petición (solo se apunta lo que de verdad funcionó, tal cual se ejecutó)."
        if (H.clasificar(cambiar)[0] not in {"autonomo", "inocuo"}
                or re.search(_A._ORDEN_DE_SOFTWARE, cambiar)):
            return "No guardo la receta: no es un simple cambio de ajuste (pide permisos especiales o es de los que preguntan antes)."
        ultimo = donde[-1]
        comprobado = False
        if leer:
            if H.clasificar(leer)[0] not in {"lectura", "inocuo"}:
                return "No guardo la receta: «leer» tiene que ser un comando de solo lectura."
            donde_leer = bien_ejecutado(leer)
            if not donde_leer:
                return "No guardo la receta: el comando de lectura no se ejecutó en esta petición."
            comprobado = donde_leer[-1] > ultimo
        if not comprobado:
            comprobado = any(n == "mirar_pantalla" and str(r).startswith("Lo que se ve") for i, n, a, r in hechas if i > ultimo)
        if not comprobado:
            return ("No guardo la receta: no consta que hayas comprobado que funciona. Lee el valor DESPUÉS del cambio con un comando de lectura (y pásalo en "
                    "«leer») o míralo con mirar_pantalla, y vuelve a llamar.")
        self.ejecutor.recetas_diferidas.append({"ajuste": ajuste, "palabras": args.get("palabras", ""), "cambiar": cambiar, "valor_usado": args.get("valor_usado", ""),
                                                "leer": leer, "comprobar": comprobar, "web": bool(self.ejecutor.contaminado)})
        self.ejecutor.receta_turno = True
        return (f"Receta anotada: «{ajuste}». Se guardará al terminar SOLO si se confirma que lo que pidió el usuario está cumplido; hasta entonces no "
                "digas que ya está guardada.")

    @staticmethod
    def _relacionado(cambio, lectura):
        """¿Ese comando de lectura mira justo lo que cambió el otro? Mismo programa (o su par kwriteconfig/kreadconfig) y alguna palabra concreta en común."""
        try:
            tc, tl = shlex.split(cambio), shlex.split(lectura)
        except ValueError:
            return False
        if not tc or not tl:
            return False
        bc, bl = os.path.basename(tc[0]), os.path.basename(tl[0])
        pares = {"kwriteconfig6": "kreadconfig6", "kwriteconfig5": "kreadconfig5"}
        if not (bc == bl or pares.get(bc) == bl):
            return False
        comunes = {t for t in tc[1:] if not t.startswith("-") and len(t) >= 3} & {t for t in tl[1:] if not t.startswith("-") and len(t) >= 3}
        comunes -= {"set", "get", "true", "false"}
        return bool(comunes)

    def _aprender_automatico(self):
        """Red de seguridad: si en esta petición se cambió UN ajuste con un comando y luego se leyó con un comando de lectura que mira lo mismo,
        pero nadie apuntó la receta (la IA suele olvidarse), se apunta aquí. El nombre sale del «motivo» del comando y el valor, de su último argumento."""
        ej = self.ejecutor
        if not getattr(self, "turno_aceptado", False) or ej.receta_turno or ej.duda or ej.pendientes or ej.contaminado:
            return
        hechas = [(n, a or {}, str(r)) for n, a, r in self.acciones_turno]
        if any(n in {"guardar_receta", "usar_receta", "probar_ajuste_kde"} for n, _, _ in hechas):
            return
        cambios = []
        for i, (n, a, r) in enumerate(hechas):
            if n != "ejecutar_comando" or not r.startswith("código de salida: 0"):
                continue
            cmd = " ".join(str(a.get("comando", "")).split())
            if H.clasificar(cmd)[0] in {"autonomo", "inocuo"}:
                cambios.append((i, cmd, str(a.get("motivo", ""))))
        if len(cambios) != 1:                                      # varios pasos (cambiar + recargar...): que lo apunte la IA con guardar_receta
            return
        i, cambiar, motivo = cambios[0]
        if (re.search(_A._ORDEN_DE_SOFTWARE, cambiar)
                or re.search(r"[;&|<>`]|\$\(", cambiar) or len(cambiar) > 300):
            return
        try:
            base = os.path.basename(shlex.split(cambiar)[0])
        except (ValueError, IndexError):
            return
        if self._NO_AJUSTE.match(base):
            return
        leer = next((cmd for j, (n, a, r) in enumerate(hechas) if j > i and n == "ejecutar_comando" and r.startswith("código de salida: 0")
                     for cmd in [" ".join(str(a.get("comando", "")).split())]
                     if H.clasificar(cmd)[0] in {"lectura", "inocuo"} and self._relacionado(cambiar, cmd)), None)
        if not leer:
            return
        salida = hechas[[" ".join(str(a.get("comando", "")).split()) for _, a, _ in hechas].index(leer)][2]
        salida = " ".join(salida.splitlines()[1:])[:100] if salida.startswith("código") else salida[:100]
        if not salida.strip():
            return
        ajuste = IDI.segun(self._VERBO_INICIAL_POR_IDIOMA).sub("", motivo.strip()).strip(" .") if motivo else ""
        if len(ajuste) < 4 or ajuste.lower() == "tarea":
            return
        try:
            toks = shlex.split(cambiar)
        except ValueError:
            return
        valor_usado = ""
        if len(toks) >= 3 and not toks[-1].startswith("-") and not toks[-2].startswith("-") and cambiar.count(toks[-1]) == 1:
            valor_usado = toks[-1]
        receta = _A.REC.aprender_comando(ajuste, "", self._peticion_de_receta(), cambiar, valor_usado, leer, f"leído después con {leer}: {salida}", web=False)
        if receta:
            ej.receta_turno = True
            log(f"Receta apuntada automáticamente: «{receta['ajuste']}» (se cambió con un comando y se comprobó con otro; la IA no la había guardado)")

    def _mis_ajustes(self, args):
        """Lina consulta su documentación y sus ajustes, y los cambia (con las protecciones de autoconocimiento.py)."""
        accion = str(args.get("accion") or "ayuda")
        if accion == "ayuda":
            return AUTO.ayuda(args.get("tema"))
        if accion == "cambiar":
            if (str(args.get("ajuste") or "").strip().lower() in ("privacidad.capturas", "capturas")
                    and str(args.get("valor") or "").strip().lower() in ("si", "sí", "s", "y", "yes", "true", "1")):
                # el consentimiento nunca lo cambia la IA: lo deja pendiente y lo confirma el usuario con el atajo
                if self.modo_privado:
                    return "Está activado el modo privado: no envío capturas hasta que el usuario lo quite. Díselo."
                return self._permiso_de_capturas() or "Ya tienes permiso para enviar capturas: no hay nada que cambiar."
            hecho, texto = AUTO.cambiar(args.get("ajuste"), args.get("valor"), voz_libre=self.origen_voz_libre,
                                        contaminado=bool(self.ejecutor.contaminado))
            log(f"Ajuste cambiado por la IA: {args.get('ajuste')!r} -> {args.get('valor')!r}: {'hecho' if hecho else texto[:120]}")
            return texto
        if accion in ("elegir_voz", "probar_voz"):
            nombre = str(args.get("voz") or "")
            if nombre not in VOC.catalogo():
                return f"No conozco la voz «{nombre}». Las que hay: {', '.join(VOC.catalogo())}."
            if not VOC.asegurar(nombre, log=log):
                return f"No he podido descargar la voz {nombre}: mira el registro."
            if accion == "elegir_voz":
                VOC.fijar(nombre)
                log(f"Voz cambiada por la IA: {nombre}")
                return f"Hecho: ahora hablo con {nombre}. Se nota ya desde tu siguiente frase; esta respuesta aún sale con la voz de antes."
            self._hablar(str(args.get("texto") or IDI.T("Hola, así suena mi voz.")), voz=nombre)
            return f"Dicho con la voz {nombre}. Si vas a probar varias, hazlo una a una en esta misma respuesta y no repitas el texto en tu contestación."
        return "Acción desconocida: usa ayuda, cambiar, elegir_voz o probar_voz."


# Al final a propósito: asistente.py importa este módulo y este importa a asistente.py; así vale importar cualquiera de los dos primero.
from lina.nucleo import asistente as _A  # se usa al llamar (no al importar): así valen los parches de pruebas
