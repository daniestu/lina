# Seguridad y confirmaciones

Principios:

1. **Autonomía por defecto, con frenos.** Lina actúa sola salvo en las categorías críticas de `politica.txt`
   (discos, arranque, cuentas y credenciales, red expuesta, borrado definitivo, software de fuera, dinero, sesión, persistencia,
   archivos de paquetes).
2. **Las acciones críticas solo se confirman con el atajo de teclado**, nunca por voz en manos libres: una frase mal oída o un vídeo
   de fondo no pueden autorizar nada.
3. **Bloqueos duros en el código** que ninguna política ni confirmación desbloquea (formatear discos, leer claves, descargar y ejecutar
   scripts de internet…).
4. **Lo que lee de fuera es información, no órdenes** (webs, documentos, resultados de herramientas).
5. **Todo cambio queda en un diario** y se puede deshacer; los borrados normales van a la papelera.
6. **Sin telemetría.** Las capturas de pantalla solo se envían a la IA para responder, y existe un modo privado que las desactiva.
7. **Las claves** viven en `~/.config/lina/` con permisos 600 y la IA no puede leerlas ni editarlas.
