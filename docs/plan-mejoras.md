# Plan de mejoras tras la beta (fases 11 a 15)

Objetivo: que Lina responda **al instante** a lo sencillo, **recuerde** lo que le pides que recuerde y sepa más de tu equipo (Bluetooth, juegos, GPU), sin perder
lo que la distingue: lo crítico solo se confirma con el atajo, todo queda en el diario y casi todo se puede deshacer.

Cada fase termina con: pruebas automáticas, textos traducidos (`en.toml`), entrada en el CHANGELOG, documentación y una prueba a mano en un equipo real.
Tamaños relativos: **S** pequeña, **M** media, **L** grande.

| Fase | Qué | Tamaño | Depende de |
|---|---|---|---|
| 11 | Medir dónde se va el tiempo *(hecha)* | S | — |
| 11b | No olvidar la petición tras un paso previo *(hecha)* | S | — |
| 12 | Camino rápido: órdenes simples sin pasar por la IA, y voz sin esperas *(hecha: abrir programa, volumen, silencio, ventanas, hora y música; voz con caché y Piper residente; falta confirmar en el equipo el Piper residente)* | L | 11 |
| 12b | Recetas que se ejecutan solas *(hecha: falta probarla en el equipo de Dani)* | L | 12 |
| 13 | Memoria de preferencias *(hecha: falta probarla en el equipo de Dani)* | M | — |
| 14 | Bluetooth completo y más diagnóstico de juegos *(hecha: falta probarla en el equipo de Dani)* | S | 12 (para sus órdenes directas) |
| 15 | GPU y energía (módulo opcional) *(hecha: falta probarla en el equipo de Dani)* | M | — |
| 17 | Revisión de octubre de 2026: seguridad, latencia y voz, autonomía y mantenimiento *(en curso: S1 y S2 hechas)* | L | — |

Fuera del plan, a propósito: excluir monitores de las capturas (Lina captura todos), una ventana de chat con historial (Lina es de voz) y quitar las
confirmaciones por atajo (es una decisión de seguridad, no una carencia).

---

## Fase 11 — Medir (S)

**Para qué:** hoy el registro solo dice «(X s en total)». Sin saber qué parte tarda no se puede decidir qué acelerar.

**Qué se hace**
1. **Cronómetro por fases** en `_voz_a_respuesta` y `_atender` (`nucleo/asistente.py`): fin de la frase → Whisper → decisiones previas del código → llamada a la IA
   (cada vuelta, con tiempo hasta el primer dato y total) → ejecución de herramientas → primera sílaba de Piper → fin de la voz.
2. **Una línea de registro por petición**, sin contenido: `Tiempos [modelo]: whisper 0,9 s · previas 0,1 s · ia 2,1 s · herramientas 0,4 s · sintesis 0,3 s · voz 2,0 s · 2 herramientas · hasta oírte 3,8 s`.
3. **Archivo `tiempos.jsonl`** en la carpeta de estado, solo números y la «ruta» que siguió (IA, directa), rotado a ~200 KB. Nunca la frase dicha.
4. **Orden `lina tiempos`:** media y mediana por fase de las últimas N peticiones y cuál es la fase más lenta.
5. Ajuste `diagnostico.tiempos` (sí por defecto, porque no guarda texto) y entrada en el documento de privacidad.

**Pruebas:** el cronómetro con un reloj falso; que `tiempos.jsonl` no contiene texto; rotación; `lina tiempos` con archivo vacío y con datos.

**Hecho cuando:** sabes, con datos de tu propio equipo, qué fase domina en una orden simple y en una compleja, y fijamos el objetivo de la fase 12
(propuesta: **menos de 1 s** desde el fin de la frase hasta que la acción empieza).

**Resultados de la primera medición (equipo de Dani, 20 órdenes con el atajo):**

| Tipo de orden | Hasta que suena | Dónde se va |
|---|---|---|
| Abrir aplicación, volumen, ventanas | 3,3 – 5,0 s | Whisper 0,6–0,8 · IA 1,3–3,0 (2 llamadas) · acción 0,3–0,7 · síntesis 0,7–0,8 |
| Pregunta sin herramientas | 2,7 – 3,1 s | Whisper 0,7 · IA 1,2–1,5 · síntesis 0,7–0,9 |
| Consulta con herramientas (RAM, CPU, red, batería) | 6,7 – 19 s | La IA (5–17 s); la herramienta tarda ~0 s |
| Búsqueda web | 49,9 s | IA 45 s (esperas de red) |
| Instalar un programa (a fondo) | 30,4 s | IA 17,9 · instalación en segundo plano |

Qué sale de ahí: **1)** cada orden simple cuesta DOS llamadas a la IA (decidir y luego decir «Abierto»); **2)** tras actuar hay una TERCERA, el revisor «¿se cumplió lo pedido?», con espera de hasta 8 s y se prueba con dos modelos: cuando Google va lento, una orden de 3 s pasa a 14 s;
**3)** tras un fallo de red la clave gratuita queda «en pausa» 3 minutos y todo va a la de pago (en un mes: 3,50 € y 466 llamadas); **4)** Piper arranca un proceso por frase (0,7–0,9 s antes de oír nada); **5)** la captura de pantalla se enviaba en todas las peticiones (ya corregido, ver 11b).

---

## Fase 11b — No olvidar la petición (hecha)

**El fallo:** «Abre Stremio» → no está instalado → Lina lo instala (más de 10 s: pasa a segundo plano) → avisa «ya ha terminado» → y nunca lo abre. Se olvidaba de lo que de verdad se pidió.

**Qué se hizo**
1. Al pasar un comando a segundo plano se guarda la petición del usuario. Al terminar bien, Lina **retoma sola esa petición** (espera a no estar hablando contigo), le dice a la IA qué acaba de terminar y que haga lo que falta, sin repetir el paso previo.
2. Tope de 3 vueltas seguidas, para que no dé vueltas sin fin; si falla la tarea o nadie puede retomar, el aviso de siempre.
3. Las instrucciones de la IA dicen que su trabajo es cumplir la petición COMPLETA, no el primer paso, y el mensaje de «sigue en segundo plano» ya no le deja dar la petición por cumplida.

**Pendiente de probar a mano:** «Abre Stremio» con Stremio desinstalado: debe instalarlo y abrirlo sin pedírselo otra vez.

---

## Fase 12 — Camino rápido sin IA (L)

**Para qué:** «ábreme Stremio» o «sube el volumen» no necesitan un modelo: hoy cada orden espera a Gemini.

**Dónde se engancha:** en `_atender`, justo después de las órdenes que el código ya resuelve solo (manos libres, alias, reiniciar, cancelar) y **antes** de la
captura de pantalla y de la IA. Ahí ya hay un patrón: «lo hace el código, sin IA».

### 12.1 Diseño y módulo `nucleo/directas.py`
- Un **registro de acciones directas**. Cada una declara: `id`, frases que la activan (con variantes, sin importar tildes ni mayúsculas), cómo extrae sus parámetros,
  su **nivel de riesgo** y qué función la ejecuta.
- **Solo entran acciones de riesgo bajo** (abrir un programa, volumen, colocar ventanas, reproducción). Nada que borre, instale, apague o toque ajustes del sistema.
- Cada acción **reutiliza lo que ya existe** (`planificar_ventanas`, `planificar_audio`, el abrir aplicaciones) y se ejecuta por el mismo ejecutor, así que pasa por las
  mismas reglas de seguridad y deja su línea en el diario. El camino rápido no es una puerta lateral.
- **Confianza:** cada candidata saca una puntuación. Si hay una ganadora clara y todos los parámetros están, se ejecuta; si hay empate, falta un dato o la frase es
  una pregunta o una negación («¿cómo abro…?», «no abras…»), **cede el paso a la IA**.
- Las frases viven en una sección nueva de `comandos.txt` (el archivo que la IA no puede modificar), para ajustarlas sin tocar código.

### 12.2 Acciones iniciales
| Acción | Ejemplos | Detalle |
|---|---|---|
| Abrir aplicación | «abre Stremio», «ábreme el navegador» | Búsqueda difusa sobre los `.desktop` instalados (ya hay puntuación en `sistema.py`); si hay dos parecidos, a la IA |
| Volumen | «sube el volumen», «ponlo al 40», «silencia», «quita el silencio» | Pasos y límites razonables; nunca más del 100 % |
| Ventanas | «maximiza», «pantalla completa», «minimiza», «pon Firefox en el otro monitor» | Sobre la ventana activa o por nombre; **no incluye cerrar** (puede perder trabajo) |
| Reproducción | «pausa», «siguiente», «anterior», «continúa» | Por MPRIS (`playerctl`) cuando está disponible |

### 12.3 Respuesta y contexto
- La frase que dice Lina la **escribe el código** a partir de una plantilla traducible («Abriendo Stremio»), no una IA.
- La orden se anota en el historial como un turno más, para que «ahora ponla en pantalla completa» tenga a qué referirse.
- **Si la acción falla** (aplicación no encontrada, error del sistema), se cae a la IA con una nota «intenté X y falló», no se queda en silencio.

### 12.4 Seguridad y perfiles
- Lista blanca estricta; parámetros validados; **nunca se construye un comando como texto de shell** (siempre lista de argumentos).
- En el perfil **Prudente** las acciones directas piden la confirmación que ya pedirían; en Equilibrada y Autónoma van directas.
- Interruptor `directas.activo` y orden `lina directas`: lista lo que sabe hacer y **`lina directas probar "ábreme stremio"`** dice qué haría **sin ejecutarlo**.

### 12.5 Menos esperas en lo que sigue pasando por la IA
- **Revisor solo cuando hace falta:** no se llama tras acciones inocuas (abrir un programa, volumen, leer el estado) ni cuando ya hay una comprobación del código; con plazo corto (3 s) y **sin probar un segundo modelo** si el primero no contesta (ante la duda, se da por cumplido, como ya hace).
- **Pausas de modelo más finas:** un fallo de red (timeout) pausa 30 s, no 3 minutos; los 503/429 siguen igual. Si por una pausa se usa la clave de pago, se anota en el registro y en `lina tiempos`.
- **Medir cada llamada a la IA** (duración y resultado) dentro de `lina tiempos`, para saber cuánto cuesta cada vuelta.
- **Voz sin esperas:** caché de las frases fijas («Abierto.», «Hecho.», «Volumen al 40 %») ya sintetizadas por voz, para que suenen al instante, y Piper persistente (no un proceso por frase) para el resto.
- **Objetivo:** orden directa ≤ 1,2 s hasta que suena; con IA, mediana ≤ 3 s y sin picos de más de 10 s por esperas de red.

### 12.6 Pruebas y despliegue
- Tabla de frases → acción (positivas), frases que **no** deben activarse (preguntas, negaciones, frases largas que contienen «abre» por casualidad), ambigüedades,
  parámetros fuera de rango y ejecutor falso de principio a fin.
- Registro «Directa: …» con su tiempo para comparar durante una semana con lo que habría hecho la IA.
- **Hecho cuando:** ≥ 95 % de aciertos en la tabla, **cero** falsos positivos con consecuencias, y el objetivo de latencia de la fase 11 cumplido en tu equipo.

---

## Fase 12b — Recetas que se ejecutan solas (L)

**Para qué:** «desactiva mi cámara» la primera vez hay que descubrirlo (la IA piensa, prueba, comprueba). La segunda debería ser tan rápida como «sube el volumen». Hoy no lo es por dos motivos:

1. **Se aprende muy poco.** Solo se apunta una receta si en la petición hubo UN comando de cambio y luego otro de lectura que mira lo mismo, o un ajuste de KDE comprobado en pantalla, o la IA llama a `guardar_receta` (casi nunca). Lo que lleva varios pasos, o no se lee después, se pierde.
2. **Una receta es una pista, no un atajo.** Aunque exista, la petición va a la IA, que la lee y vuelve a ejecutarla: dos o tres llamadas, de 3 a 20 s según cómo vaya Google.

**Qué se hace**
1. **Aprender de cualquier éxito.** Cuando una petición termina CUMPLIDA (el código lo comprobó o el revisor lo confirma), sin nada pendiente de tu «sí» y sin contenido de internet de por medio, se guarda **la secuencia de pasos que de verdad funcionó**: las herramientas llamadas con sus datos, sin los intentos fallidos ni las exploraciones; el valor que cambió se convierte en `{valor}`; y **cómo se comprobó** (qué lectura confirmó el resultado y qué salida dio).
2. **Repetir sin IA.** Si lo que pides encaja claramente con una receta, el código la ejecuta paso a paso con las mismas herramientas y las mismas reglas de seguridad de siempre (un paso crítico sigue pidiendo tu atajo; una receta no da permisos nuevos), repite la comprobación y dice el resultado. Va delante de la IA, igual que las órdenes directas.
3. **Dirección y valores.** «Activa» y «desactiva» no pueden confundirse: cada receta guarda el efecto que produce y el encaje exige la misma dirección; si no está claro, vale solo como pista, como ahora. Los números («al 40») se sustituyen en `{valor}`.
4. **Si falla, a la IA.** Si un paso da error o la comprobación no da lo esperado, la IA toma el relevo con una nota («la receta falló en tal paso»); dos fallos seguidos y la receta se borra (como ya pasa).
5. **Confianza gradual.** Una receta comprobada por el código (se leyó el estado después y coincide) se repite directamente a la siguiente; una que solo confirmó el revisor necesita un segundo éxito antes de ejecutarse sola.
6. **Control.** `lina recetas` (ver, probar sin ejecutar, borrar), «olvida cómo desactivar la cámara» por voz, ajuste `recetas.directas` para apagarlo, y cada ejecución queda en el diario como cualquier otra acción (se puede deshacer).

**Pruebas:** aprendizaje de secuencias de varios pasos; que no aprende nada de lo fallido, contaminado, pendiente o no cumplido; encaje por dirección (activar/desactivar) y por valor; paso crítico que sigue pidiendo confirmación; fallo a mitad que cae a la IA; borrado tras dos fallos; `lina recetas`.

**Hecho cuando:** pides algo que Lina tuvo que descubrir (p. ej. desactivar la cámara), lo repites y se hace sin llamar a la IA en menos de ~2 s, con la misma comprobación.

---

## Fase 13 — Memoria de preferencias (M)

**Para qué:** «recuerda que mi opción preferida para jugar es Proton-CachyOS» y que Lina lo use en conversaciones futuras. Hoy hay notas, recetas y diario, pero no una
memoria de preferencias.

**Qué se hace**
1. **Almacén** pequeño en la carpeta de datos (SQLite o JSON, a decidir al empezar): texto corto (máx. 300 caracteres), fecha, etiquetas simples; tope de ~200 entradas.
2. **Solo lo que tú pides.** Órdenes resueltas por el código, como los alias: «recuerda que…», «olvida lo de…», «¿qué recuerdas de mí?». Lina **no guarda cosas por
   su cuenta** a partir de lo que oye o lee.
3. **La IA no puede escribir en la memoria.** Así una página web o un archivo con instrucciones ocultas no puede inyectar «recuerdos». La IA solo los **lee**.
4. **Uso:** en cada petición se recuperan por palabras los pocos recuerdos relevantes y se añaden como contexto («Preferencias que el usuario te pidió recordar: …»),
   con tope de tamaño.
5. **Privacidad:** se tapan claves y contraseñas antes de guardar; no se guarda nada que parezca una; `lina memoria` (ver y borrar), `lina olvidar memoria` y su inclusión
   en `lina uninstall --todo` y en el documento de privacidad.

**Pruebas:** guardar y recuperar; que la IA no tenga ninguna herramienta que escriba; inyección desde contenido web (no crea recuerdos); tope y límites; borrado;
tapado de claves; que «olvida» elimina de verdad.

**Hecho cuando:** reinicias Lina, abres una conversación nueva y usa lo que le pediste recordar.

---

## Fase 14 — Bluetooth completo y más diagnóstico de juegos (S)

- **Bluetooth** (`bluetoothctl`): estado del adaptador, dispositivos emparejados y conectados, **conectar y desconectar por nombre aproximado**, batería si el dispositivo
  la informa. «Conecta mis auriculares» pasa a ser una orden directa de la fase 12. Emparejar dispositivos nuevos **no**: pide confirmación.
- **Juegos:** `ver_juegos` y `proton` suman comprobaciones de GameMode, Vulkan y, si están, LSFG y MangoHud. Siempre en modo **diagnóstico** (señalan, no modifican).
- Pruebas con salidas simuladas de `bluetoothctl` y de los comandos de diagnóstico.

---

## Fase 15 — GPU y energía, módulo opcional (M)

**Solo aparece si hay una GPU compatible.**
1. **Detección:** NVIDIA (`nvidia-smi`), AMD (sysfs/hwmon de `amdgpu`) o Intel; si no hay, la herramienta ni se ofrece.
2. **Herramienta `gpu`, de solo lectura:** frecuencias, temperatura, consumo, VRAM usada, límite de potencia y **motivo de la limitación** (térmica, de potencia…).
3. **LACT:** detectar si está, listar perfiles. **Cambiar de perfil es una acción que pide confirmación**, nunca directa.
4. **Registro de métricas a archivo** («cada 2 segundos durante 15 minutos»): tarea en segundo plano con límites de duración, frecuencia y tamaño, salida en CSV
   dentro de una carpeta de Lina; si quieres una hoja de cálculo, la herramienta de hojas ya existente la convierte. No se queda corriendo sin que se sepa: se ve y se
   cancela con `lina procesos`.
5. Pruebas con salidas simuladas de NVIDIA, AMD y sin GPU.

---

## Fase 16 — Encargar trabajos de programación a un agente externo (M, no prioritaria)

Idea apuntada, sin empezar. Lina no lleva un agente de programación dentro: le encarga la tarea al que el usuario ya tenga instalado y con su propia cuenta.

- **Camino elegido**: conectar por MCP (Lina ya tiene el grupo `mcp`). Claude Code puede ofrecerse como servidor MCP (`claude mcp serve`); hay que comprobar con la versión instalada que lo permite y qué herramientas expone. Alternativa si no: lanzarlo como programa con su modo sin pantalla (`claude -p`, `codex exec`).
- **Neutral**: ajuste para elegir qué agente; nada de atarse a uno. No se incluye en Lina (Claude Code es propietario y el proyecto es AGPL): solo se llama al instalado.
- **Seguridad**: apagado por defecto, limitado a una carpeta, confirmación con el atajo antes de empezar, lo que lea de webs o archivos se trata como datos y su propio código y ajustes quedan fuera de su alcance.
- **Voz**: tareas largas en segundo plano con aviso al terminar.
- **Privacidad y coste**: el código que toque sale al proveedor y gasta de su cuenta; se explica antes de activarlo.

## Fase 17 — Revisión de octubre de 2026 (L, por partes)

Sale de una revisión del código completo (23 y 24 de octubre de 2026). Cada punto es un cambio pequeño **con su prueba y su línea en el CHANGELOG**, y se hace
**de uno en uno**, con el plan aprobado antes de tocar código. Tamaños: **S** pequeño, **M** medio, **L** grande.

### Qué se midió antes de proponer nada (seguridad)
Se pasaron ~50 comandos por el clasificador (`tratar_borrado` + `clasificar`) con un `$HOME` de prueba **fuera** de las zonas desechables (en `/tmp` los
borrados salen como autónomos por estar en zona desechable; esa primera medida no valía). Lo que se ejecuta **sin confirmar y sin poder deshacerse** con el
perfil `autonomo`:
- **Sacar archivos del equipo**: `curl -d/-F/--data-binary @archivo`, `curl -T`, `curl "…?q=$(cat … | base64)"`, `wget --post-file`, `tar … | curl -T -`, `scp`,
  `rsync … usuario@host:`, `nc host puerto < archivo`.
- **Borrar por rodeos**: `git clean -fdx`, `c=rm; $c -rf …`, `busybox rm -rf …`, `awk 'BEGIN{system("rm …")}'`, `perl -e 'unlink …'`, `vim -c ':!rm …'`,
  `systemd-run --user rm …`.
- **Ejecutar scripts fuera de Descargas**: `bash ~/proyecto/x.sh`, `source ~/proyecto/x.sh` (en `~/Descargas` sí se confirma).
- **Leer credenciales** (salen como lectura y van a la IA): `~/.config/gh/hosts.yml`, `~/.docker/config.json`, `~/.kube/config`, `~/.git-credentials`, historiales de
  bash y fish, `env`; y `sqlite3` sobre las cookies de Brave/Chromium (las de Firefox sí están bloqueadas).
- **Quitar el bloqueo de pantalla**: `gsettings … screensaver lock-enabled false`, `kwriteconfig6 --file kscreenlockerrc … Autolock false`.

Lo que ya está bien: `rm` va a la papelera; `shred`, `truncate` y `dd` sobre tus archivos se confirman; `find -delete`, `env rm`, `command rm` y `\rm` se bloquean;
`> archivo` y `mv` se ejecutan solos pero el diario guarda copia y se deshacen.

### Seguridad
| # | Qué | Tamaño |
|---|---|---|
| S1 | **Modo privado solo por código** *(hecha)*: la IA solo puede activarlo; quitarlo, frase exacta de `comandos.txt` y solo con el atajo. | S |
| S2 | **La IA no escribe alias de voz** *(hecha; además, enseñar un alias solo con el atajo)*: antes `alias_de_voz` solo exige que lo oído aparezca en tus últimas frases y «significa» es libre, así que un alias inyectado («conecta = desconecta») invertiría órdenes futuras antes de llegar a `directas`. La IA solo podrá listarlos; apuntar y borrar, solo por tus frases («cuando oigas X quiero decir Y»), que ya resuelve el código. | S |
| S3 | **VRAM antes de cargar Ollama**: el plan B (`preguntar_local` sin herramientas) carga `qwen3-vl:8b` sin mirar nada y puede pasar del tope de 4 GB junto a Whisper. Comprobar el tamaño del modelo y la VRAM libre antes; si no cabe dentro del tope, no se carga y se dice. | S |
| S4 | **Más secretos**: añadir a la lista de credenciales `gh`, `docker`, `kube`, `.git-credentials`, historiales de shell y los perfiles de Chromium/Brave/Vivaldi (`Cookies`, `Login Data`); `env`/`printenv` pasan a tapar valores que parezcan claves. | S |
| S5 | **Red de salida bloqueada en tareas contaminadas**: si en la tarea se ha leído contenido de fuera, los comandos que **envían** datos (las formas de la lista de arriba, `ssh` con orden remota, `socat`) se bloquean, sea cual sea el perfil. Descargar (`curl -o`, `wget` sin datos) sigue igual. Sin contenido de fuera no cambia nada. | M |
| S6 | **Cerrar los rodeos medidos**, cada uno con su prueba: variable usada como programa (`$c …`) → crítico; `busybox`/`toybox` se analizan como el programa que llaman; `awk/gawk … system(`, `perl/ruby -e` → como `python -c` (código en línea); `vim/nvim -c ':!'`, `less +!` → crítico; `systemd-run`, `run0`, `setsid` → se analiza la orden de dentro; `git clean -f` → borrado definitivo; ejecutar un script de cualquier carpeta tuya → software de fuera; bloqueo de pantalla (`gsettings`, `kscreenlockerrc`) → cuentas y credenciales. | M |
| S7 | **Origen por petición en la cola de «además»**: lo que apuntas para después con «Oye Lina» hereda `origen_voz_libre` del último que habló, no el suyo; si entretanto pulsas el atajo, esa frase contaría como dicha con el atajo. Cada entrada de la cola guarda su origen. | S |
| S8 | **`lina update` a releases**: hoy sigue `main` (cada commit, no las versiones). Pasar a la última etiqueta `vX.Y.Z-beta` con `git verify-tag`, y fijar dependencias (archivo de restricciones o `uv.lock`) para que un `faster-whisper` o `piper-tts` nuevo no rompa Lina sin aviso. | M |
| S9 | **Fase aparte: aislar los comandos de la IA con `bwrap`** (o `systemd-run --user -p ProtectHome=read-only`): carpetas escribibles por lista, red solo cuando haga falta. Es la defensa de fondo frente a una lista negra sobre bash, que nunca estará completa. **Diseño primero** (qué carpetas, cómo convive con el diario, la papelera, `sudo` y los programas con ventana), sin código hasta aprobarlo. | L |

### Latencia y voz
| # | Qué | Tamaño |
|---|---|---|
| V1 | **Cola de voz**: hoy `_hablar` usa un solo `respuesta.wav` y un solo `self.reproductor`; avisos sueltos («lo pienso a fondo», «Google está tardando», el estado) pueden coincidir, pisarse el audio, y «cállate» solo para uno. Un hablante cada vez, archivos propios por frase. | S |
| V2 | **Captura de pantalla solo cuando haga falta**: hoy se hace en cada pulsación, también en modo privado o sin permiso. | S |
| V3 | **Fin de frase por silencio con el atajo** (ajuste, apagado por defecto hasta medirlo): una pulsación en vez de dos, con el detector que ya usa el manos libres. Medir con `lina tiempos` y `probar-voz` que no corta frases. | M |
| V4 | **Instrucciones más ligeras**: cada llamada lleva ~16 000 caracteres de instrucciones y 5 000–14 000 de herramientas, y se repiten en cada vuelta. Primero medir si la caché de Gemini se aprovecha (`cachedContentTokenCount` en el registro); después pasar las reglas de situaciones concretas (música, navegador…) a sus grupos. | M |
| V5 | **Respuesta y voz por frases** (streaming): empezar Piper con la primera frase. Poco para respuestas de una frase; se nota en el modo «a fondo». Después de V1. | M |
| V6 | **Detector de palabra clave para «Oye Lina»** (p. ej. openWakeWord, en CPU, sin VRAM) en vez de pasar Whisper por cada trozo con voz. Opcional y medido como `probar-voz` (falsos positivos por hora, aciertos, CPU). Ojo con las licencias: los modelos preentrenados de openWakeWord no son de uso comercial; habría que entrenar el de «Oye Lina». | M |

### Autonomía
| # | Qué | Tamaño |
|---|---|---|
| A1 | **Medir la memoria antes de cambiarla**. Hoy un recuerdo es pertinente si comparte **una** raíz de palabra con la petición, y eso además desactiva las órdenes directas y las recetas. Paso 1 (S): una tanda de pares (petición, recuerdo, ¿viene al caso?) escrita a mano y una orden `lina memoria medir` que cuente aciertos, falsos positivos y órdenes directas que se pierden con «1 palabra en común» frente a «2 o más». Paso 2, **solo si no basta** (M): embeddings pequeños en CPU (modelo multilingüe de ~100 MB con ONNX), **opcionales y apagados por defecto**, medidos con la misma tanda (aciertos, tiempo por petición, memoria) como hace `probar-voz`. Nada de VRAM. | S + M |
| A2 | **Banco de pruebas de la IA**: frases → herramientas esperadas, con respuestas grabadas para la CI y una pasada real opcional. Sin él, cada cambio de instrucciones o de modelo (los `-latest` cambian sin avisar) es a ciegas. | M |
| A3 | **Modelos fijados** en vez de `-latest`, y cambiar de versión solo tras pasar A2. Después de A2. | S |
| A4 | **`lina di "frase"`**: hablarle por texto a la Lina en marcha (sin micrófono, para pruebas completas reproducibles). Cuenta como manos libres: no confirma nada, porque cualquier programa local podría llamarlo. | S |
| A5 | **Más contexto, con las mismas reglas que las capturas**: portapapeles, texto seleccionado y archivo seleccionado en Dolphin («resume esto», «manda este archivo»), solo cuando la frase lo pide. | M |
| A6 | **Tareas largas**: plan con pasos y progreso que sobrevive a un reinicio, y tareas programadas («cada lunes vacía Descargas») que pasan por el ejecutor y el diario como todo. | L |
| A7 | **Avisos por iniciativa propia, opcionales**: disco casi lleno, batería baja, actualizaciones pendientes. Apagados por defecto. | M |

### Mantenimiento
| # | Qué | Tamaño |
|---|---|---|
| M1 | **Las pruebas no deben tocar el `$HOME` real**: importar `comandos.py` ya llama a `rutas.editable("comandos.txt")`, que copia el archivo de fábrica a `~/.config/lina` si falta, y el proceso de pytest no cambia `HOME` (las suites sí). `conftest.py` debería poner `HOME` y las XDG en una carpeta temporal antes de importar nada. A comprobar primero. | S |
| M2 | **Registro de herramientas**: `_ejecutar_herramienta` es una cadena de `if` de ~170 líneas; un diccionario `{nombre: función}` junto a cada declaración. | M |
| M3 | **Estado de la petición en una clase** (`TareaActual`, reiniciada en `nueva_tarea`) en vez de 44 `getattr(self, …, defecto)`; cambiar `estado` siempre con el cerrojo (hoy `decir` y `avisar` no lo cogen). | M |
| M4 | **Resultados con estructura** (`rc`, salida, comprobado, preparado) que se convierten en texto solo para la IA, en vez de comparar prefijos como `"código de salida: 0"` o `"COMPROBADO AHORA"`. Poco a poco, herramienta a herramienta. | L |
| M5 | **mypy más estricto** (`check_untyped_defs`) en los módulos grandes, uno a uno, empezando por `herramientas.py`. | M |
| M6 | En CLAUDE.md, `ruff` como `uvx ruff check src tests` (en el equipo del mantenedor `ruff` no está en el PATH). | S |

### Orden propuesto
1. **S1** (hecha), **S2**, **S3**: lo aprobado.
2. **S4**, **S5**, **S6** (cada rodeo por separado), **S7**: la seguridad estrecha, de lo más sencillo a lo más delicado.
3. **M1**: antes de seguir añadiendo pruebas.
4. **V1**, **V2**: pequeñas y se notan cada día.
5. **A1 paso 1** (medir la memoria) y **A2** (banco de la IA): medir antes de decidir.
6. **V3**, **V4**, **A4**, **A3**.
7. **M2**, **M3**, **S8**.
8. **S9** (diseño de `bwrap`) cuando lo anterior esté probado; **V5**, **V6**, **A5**–**A7**, **M4**, **M5** según la demanda real.

### Fuera, a propósito
- **Cambiar el perfil por defecto o `frenar_cambios`**: decisión del mantenedor; S4–S6 cubren lo medido sin tocar la autonomía.
- **Que lo desconocido pida confirmación** (invertir la lógica): decisión del mantenedor, por la misma razón.
- **Corrector de Whisper con IA local, `hotwords` y `acercar`**: ya medidos y descartados (ver «Decisiones tomadas» en CLAUDE.md).
- **Una ventana de chat**: Lina es de voz; `lina di` (A4) es para probar y para usarla en silencio, sin historial ni ventana.
- **Nada que suba de 4 GB de VRAM**: por eso los embeddings (A1) y el detector de palabra clave (V6) van en la CPU.
- **Quitar las confirmaciones por atajo**: es una decisión de seguridad, no una carencia.

## Orden y entregas

1. **11** (rápida) y a continuación **12** (la que más cambia la experiencia), por partes: 12.1–12.2 primero con *abrir app* y *volumen*, probar en tu equipo y luego
   ampliar.
2. **13** puede ir en paralelo a 12 si prefieres alternar.
3. **14** y **15** al final, cuando haya demanda real.
4. **16** cuando todo lo anterior esté probado y la voz funcione bien.

Versión sugerida: `0.2.0-beta` al cerrar la fase 12 y la 13.

## Riesgos y cómo se cubren

| Riesgo | Cobertura |
|---|---|
| Un falso positivo del camino rápido ejecuta algo no pedido | Solo riesgo bajo, umbral de confianza, negaciones y preguntas a la IA, `lina directas probar`, registro y diario |
| El camino rápido se salta la seguridad | Mismo ejecutor y mismas reglas; no hay ruta especial |
| La memoria permite inyección de contenido ajeno | Solo el código escribe, solo con una frase tuya |
| Dependencias que no están en todas las distribuciones (`playerctl`, `bluetoothctl`, LACT) | Se detectan; si faltan, la acción no se ofrece y Lina lo dice, y `lina doctor` indica qué instalar |
| Más superficie que probar en otros escritorios | Cada acción declara qué escritorios soporta y pasa por la capa de `sesion.py` |
