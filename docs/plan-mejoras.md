# Plan de mejoras tras la beta (fases 11 a 15)

Objetivo: que Lina responda **al instante** a lo sencillo, **recuerde** lo que le pides que recuerde y sepa más de tu equipo (Bluetooth, juegos, GPU), sin perder
lo que la distingue: lo crítico solo se confirma con el atajo, todo queda en el diario y casi todo se puede deshacer.

Cada fase termina con: pruebas automáticas, textos traducidos (`en.toml`), entrada en el CHANGELOG, documentación y una prueba a mano en un equipo real.
Tamaños relativos: **S** pequeña, **M** media, **L** grande.

| Fase | Qué | Tamaño | Depende de |
|---|---|---|---|
| 11 | Medir dónde se va el tiempo | S | — |
| 12 | Camino rápido: órdenes simples sin pasar por la IA | L | 11 |
| 13 | Memoria de preferencias | M | — |
| 14 | Bluetooth completo y más diagnóstico de juegos | S | 12 (para sus órdenes directas) |
| 15 | GPU y energía (módulo opcional) | M | — |

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

### 12.5 Pruebas y despliegue
- Tabla de frases → acción (positivas), frases que **no** deben activarse (preguntas, negaciones, frases largas que contienen «abre» por casualidad), ambigüedades,
  parámetros fuera de rango y ejecutor falso de principio a fin.
- Registro «Directa: …» con su tiempo para comparar durante una semana con lo que habría hecho la IA.
- **Hecho cuando:** ≥ 95 % de aciertos en la tabla, **cero** falsos positivos con consecuencias, y el objetivo de latencia de la fase 11 cumplido en tu equipo.

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

## Orden y entregas

1. **11** (rápida) y a continuación **12** (la que más cambia la experiencia), por partes: 12.1–12.2 primero con *abrir app* y *volumen*, probar en tu equipo y luego
   ampliar.
2. **13** puede ir en paralelo a 12 si prefieres alternar.
3. **14** y **15** al final, cuando haya demanda real.

Versión sugerida: `0.2.0-beta` al cerrar la fase 12 y la 13.

## Riesgos y cómo se cubren

| Riesgo | Cobertura |
|---|---|
| Un falso positivo del camino rápido ejecuta algo no pedido | Solo riesgo bajo, umbral de confianza, negaciones y preguntas a la IA, `lina directas probar`, registro y diario |
| El camino rápido se salta la seguridad | Mismo ejecutor y mismas reglas; no hay ruta especial |
| La memoria permite inyección de contenido ajeno | Solo el código escribe, solo con una frase tuya |
| Dependencias que no están en todas las distribuciones (`playerctl`, `bluetoothctl`, LACT) | Se detectan; si faltan, la acción no se ofrece y Lina lo dice, y `lina doctor` indica qué instalar |
| Más superficie que probar en otros escritorios | Cada acción declara qué escritorios soporta y pasa por la capa de `sesion.py` |
