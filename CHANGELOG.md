# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- Si Lina necesita ver la pantalla y no hay permiso, lo pide ella (explicando que la captura va a Google) y solo se activa si confirmas con el atajo; con «no» no insiste.
- Sin captura en la petición, Lina sabe que no ve nada y no describe la pantalla (solo conoce el título de la ventana).
- Estructura de proyecto con paquete `lina` (`src/`), comando `lina` y datos del usuario en las carpetas estándar XDG
  (`~/.config/lina`, `~/.local/share/lina`, `~/.local/state/lina`).
- Pruebas automáticas (`tests/`) y comprobación de que no se cuelan secretos ni datos personales.

- Cuatro voces en español (`es_MX-claude-high` por defecto, `es_ES-davefx-medium` y dos hablantes de `es_ES-sharvard-medium`),
  descargadas automáticamente la primera vez. Se elige con `lina voz NOMBRE`; el catálogo está organizado por idioma.

- Ajustes en un único archivo, `~/.config/lina/config.toml`, con validación, valores de fábrica y recarga en caliente; `lina config` para verlos y
  cambiarlos. Migra solo lo que había en `activacion.txt`, `voz.txt`, `presupuesto.txt` y `politica.txt` (ver `docs/configuracion.md`).
- Perfiles de autonomía (`autonomo`, `equilibrado`, `prudente`) e interruptores por categoría. Discos, arranque, cuentas, dinero y gasto se confirman siempre.
- Velocidad de la voz ajustable (`voz.velocidad`).
- Claves en el llavero del sistema (`lina clave gemini|pago|NOMBRE`), con respaldo en un archivo 600; la clave de pago exige un tope mensual; ninguna clave sale en el registro.
- Lina conoce su propia documentación, comandos y ajustes (herramienta `mis_ajustes`): consulta, prueba y cambia voces y cambia ajustes cuando se lo pides, sin frases fijas; lo que da más permisos solo con el atajo; claves y gasto no los toca ella. La voz elegida se oye al instante.
- Privilegios mínimos (`lina privilegios`): ayudante de root `lina-instalar` que solo instala paquetes de los repositorios del sistema, regla de sudoers que solo permite ese ayudante (con vista previa, consentimiento, validación con `visudo` y desinstalación), nivel «total» opcional con aviso y, sin regla, confirmación con el atajo y contraseña pedida por el sistema (polkit). La IA no puede tocar nada de esto.
- Privacidad: `lina privacidad` explica qué se envía a la IA y qué no, y pide permiso antes de enviar capturas de pantalla (no se envía ninguna hasta que se decide; la IA no puede decidirlo). `lina olvidar` borra diario, registro de acciones, recetas y registro del sistema. El registro de acciones rota solo y tapa las claves; `privacidad.registrar_preguntas` permite no dejar lo hablado en el registro.
- Más bloqueos contra contenido hostil: tuberías a un shell o intérprete, descargar y ejecutar en una misma orden, `sh -c "$(curl …)"`, conexiones `/dev/tcp`, código que descarga y ejecuta; piden el atajo el código libre que borra, los contenedores con acceso total, `find -delete/-exec` y `systemctl enable`. Las órdenes de la IA corren sin variables de entorno que parezcan claves. Modelo de amenazas y pruebas de ataque en `docs/seguridad.md` y `tests/test_ataques.py`.

### Eliminado
- `scripts/probar_gemini.py` (diagnóstico antiguo, atado al archivo de clave de antes) y código sin uso.

### Corregido
- Bloqueo duro: la IA no puede ejecutar `lina config poner|perfil`, `lina clave` ni `lina voz NOMBRE` (cambiar sus propios permisos, gasto o claves es cosa del usuario).
- Pruebas antiguas puestas al día (`t_abrir`, `t_abrir2`).

- El resplandor ya no es una ventana a pantalla completa: son cuatro franjas finas en los bordes de cada monitor (y una sola capa si hay pantallas duplicadas). Si el compositor no deja pasar el ratón, solo se bloquean los bordes y no el escritorio.
- El resplandor de escucha ya no debe bloquear el ratón: la zona de entrada se vacía al crear la ventana, al mostrarla y ya mostrada.
- Al abrir un programa, ya no se avisa de que «ha terminado» cuando el usuario cierra su ventana.
- Las recetas solo se guardan si al final se da por cumplido lo pedido, y describen la petición original (no una queja como «No lo has hecho»).
- Una respuesta que afirma algo habiendo cargado herramientas pero sin hacer ni leer nada del equipo se revisa a fondo.

### Cambiado
- El asistente pasa a llamarse **Lina** (palabra de activación por defecto: «Lina»; el nombre es configurable).
