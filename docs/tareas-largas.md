# Tareas largas y tareas programadas (A6): diseño

Diseño escrito el 2026-11-18, **sin código**. Espera a dos cosas: la semana de uso con `ia.aislar = auto` (S9f, ver `docs/aislamiento.md`) y las
respuestas del mantenedor a las preguntas del final. Fila A6 de `docs/plan-mejoras.md`.

## Qué se quiere

1. **Tareas largas:** una petición que necesita varios pasos («organiza mis fotos por año y luego sube la copia al disco externo») tiene un plan
   visible, con pasos y progreso, que **sobrevive a un reinicio**: al volver, Lina dice por dónde iba y pregunta si sigue.
2. **Tareas programadas:** «cada lunes vacía Descargas», «todos los días a las 9 dime si hay actualizaciones». Pasan por el ejecutor, la política y el
   diario como cualquier otra orden.

## Lo que ya hay y se reutiliza

- **Recordatorios** (`modulos/recordatorios.py`): guardados en disco, con repetición («cada…», mínimo 5 minutos), un hilo que mira cada pocos
  segundos y aviso al arrancar de lo que se pasó mientras el equipo estaba apagado. Una tarea programada es un recordatorio con una acción.
- **Ejecutor y política** (`nucleo/herramientas.py`, `nucleo/politica.py`): cada orden se clasifica, se confirma si toca y queda en el diario.
- **Acciones preparadas** (`Ejecutor.preparar_accion`): la descripción la escribe el código, nunca la IA, y solo se ejecuta con tu «sí».
- **Aislamiento** (`nucleo/aislamiento.py`, S9): sistema de solo lectura, claves y datos de Lina tapados, y sin red tras leer contenido de fuera.
- **Contenido de fuera** (S5): lo leído de internet o de un archivo ajeno marca la tarea y frena lo que podría sacar datos.

## La decisión de seguridad que lo ordena todo

**Una tarea programada corre sin ti delante.** Por eso, en la primera versión:

1. **Al programarla, confirmas la acción exacta.** La IA propone la tarea con una herramienta (`programar_tarea`), y el código la convierte en una
   acción preparada con su descripción escrita por el código: qué orden exacta, cada cuánto y desde cuándo. Solo se guarda con tu «sí» por el atajo
   (nunca por manos libres ni por `lina di`, como las demás confirmaciones).
2. **Al ejecutarse, no hay IA.** El código ejecuta esa orden guardada, tal cual, por el ejecutor y **siempre aislada** (`bwrap`, aunque `ia.aislar` esté
   en `no`; si `bwrap` no funciona en el equipo, las tareas programadas no se ofrecen). Así, nada que la tarea lea mientras corre puede cambiar lo que
   hace: no hay a quién inyectarle instrucciones.
3. **Lo que necesitaría IA al ejecutarse** («resúmeme las noticias cada mañana») queda para una segunda versión, y solo para **informar**: la respuesta
   va a una notificación o se dice en voz alta, pero en esa ejecución no hay herramientas que cambien nada, y la tarea cuenta como contaminada.
4. **Límites:** como mucho 20 tareas programadas; repetición mínima de 1 hora; una orden que falla 3 veces seguidas se pausa y se avisa; nada con `sudo`
   ni de `SIEMPRE_CONFIRMAN` (borrar sin papelera, formatear, tocar el arranque…); `lina tareas` las lista, las pausa y las quita.
5. **Al cambiar la política** (`politica.txt`) o actualizar Lina, cada tarea se vuelve a clasificar antes de su próxima ejecución; si ahora pediría
   confirmación, se pausa y se avisa.

## Tareas largas (el plan que sobrevive a un reinicio)

- **El plan lo escribe la IA** con una herramienta (`plan_de_tarea`: pasos en frases cortas). El código lo guarda en `~/.local/state/lina/tareas/`
  (archivo 600), con el estado de cada paso (pendiente, hecho, falló) **según los hechos**: un paso solo pasa a hecho si su orden acabó bien
  (`ejecucion.salio_bien`) y, si había comprobación, si salió bien.
- **Al reiniciar**, Lina no sigue sola: dice «me quedé en el paso 3 de 5 de …; ¿sigo?», y solo con tu «sí» retoma. El contexto de la conversación no
  se guarda; solo el plan, los pasos y su estado.
- **Contenido de fuera:** si un paso leyó contenido de fuera, al retomar la tarea se marca contaminada otra vez (la marca se guarda con el plan).
- **En el registro y el diario**, lo de siempre: qué orden, cuándo y cómo acabó. El plan guardado no lleva textos leídos de fuera, solo los pasos.

## Piezas propuestas (sin empezar)

| # | Qué | Tamaño |
|---|---|---|
| A6a | Tareas programadas sin IA al ejecutarse: `programar_tarea`, guardado con tu «sí», ejecución aislada por el hilo de los recordatorios, `lina tareas` | M |
| A6b | Límites, pausa tras 3 fallos, reclasificación al cambiar la política, aviso al arrancar de las que no corrieron | S |
| A6c | Plan de tarea larga guardado, estado de los pasos por hechos, «¿sigo?» tras reiniciar | M |
| A6d | (Segunda versión) tareas programadas que solo informan, con IA y sin herramientas que cambien nada | M |

**Criterio para darlo por bueno**, escrito antes del código: (1) pruebas con el reloj simulado: una tarea corre a su hora, no corre sin tu «sí», no
corre si `bwrap` no funciona, se pausa tras 3 fallos y tras un cambio de política que la haría confirmar; (2) prueba de que, al ejecutarse, no se llama
a la IA; (3) prueba de paráfrasis (≥3 formas, incluidas «Cada lunes vacía Descargas», «Todos los lunes por la mañana borra lo que haya en Descargas» y
«Programa que se vacíe la carpeta de descargas cada semana»): la IA propone `programar_tarea` con la orden y la repetición correctas, y con «¿Qué tareas
tengo programadas?» no programa nada; (4) banco gratis 2+2 sin regresiones; (5) una semana de uso del mantenedor con al menos una tarea programada.

**Coste:** sin clave de pago. Unas cuatro piezas (M+S+M, y M para la segunda versión) y un día de cupo gratuito para el banco.

## Preguntas para el mantenedor

1. ¿Vale que las tareas programadas corran **siempre aisladas**, aunque `ia.aislar` esté en `no`, y que no se ofrezcan si `bwrap` no funciona?
2. ¿Vale que en la primera versión no haya IA al ejecutarse (solo órdenes fijas confirmadas), y que lo que necesite IA quede para A6d, solo para
   informar?
3. ¿Repetición mínima de 1 hora, o prefieres otra?
4. Tras un reinicio, ¿basta con que Lina pregunte «¿sigo?» al arrancar, o prefieres que solo lo diga cuando le hables?
