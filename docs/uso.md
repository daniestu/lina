# Cómo se usa Lina

## Hablarle

- **Con el atajo** (`Meta+Espacio` en KDE, `Ctrl+Alt+Espacio` en GNOME): lo pulsas, hablas y lo vuelves a pulsar. Pulsarlo mientras habla la calla.
- **Sin manos**: «Oye Lina, …» (el nombre lo eliges tú). No escucha mientras juegas, salvo que se lo pidas. Se prueba con `lina manos-libres probar "oye lina abre firefox"`.
- Si le dices algo mientras trabaja, te escucha igualmente: «para» o «cancela eso» lo dejan; otra cosa distinta, la atiende en lugar de lo anterior.

Lina entiende la intención, no frases fijas. Estos ejemplos son solo orientativos.

## Qué puedes pedirle

| Para | Ejemplos |
|---|---|
| Programas y ventanas | «abre Firefox», «pon Dolphin a pantalla completa», «cierra esta ventana» |
| Sistema | «sube el volumen», «¿qué proceso gasta más CPU?», «conéctate al Wi-Fi de casa», «cambia la resolución del monitor» |
| Ajustes de KDE | «activa la luz nocturna», «pon el tema oscuro», «cambia el tamaño de la letra» |
| Juegos | «pon MangoHud en este juego», «qué opciones de lanzamiento tiene este juego en Steam» |
| Documentos | «hazme un currículum en PDF», «una factura para…», «prepárame un Excel con estos gastos», «copia esto al portapapeles» |
| Web | «resume esta página» (la que tienes copiada o la que le digas) |
| Notas y recordatorios | «apunta que el wifi es…», «¿qué tenía apuntado de la compra?», «avísame en 20 minutos» |
| Mirar la pantalla | «¿qué significa este error?», «¿dónde pulso para…?» (solo si permites las capturas: `lina privacidad`) |
| Manejar programas por su interfaz | «pulsa Siguiente», «marca la casilla…» (requiere `lina interfaz preparar`) |
| Sobre ella misma | «¿qué puedes hacer?», «cámbiate la voz», «llámate Jarvis», «¿cuánto he gastado de Gemini?» |
| Corregirla | «cuando oigas cait quiero decir Kate» (para lo que oye mal; solo con el atajo), «olvida el alias cait» |

## Cómo te pide permiso

- Lo que cambia el sistema queda **pendiente** y Lina te lo dice en una pregunta («voy a instalar X, ¿lo hago?»). Según el perfil que elijas
  (`lina config perfil autonomo|equilibrado|prudente`) pide confirmación para más o menos cosas.
- Responder «sí» o «no» por voz vale para lo corriente. Lo **crítico** (borrar de verdad, discos, arranque, software de fuera, subir el tope de gasto,
  cambiar de proveedor de IA) solo se confirma con el atajo, nunca por voz.
- Borrar mueve a la papelera, salvo que digas «definitivamente». Todo lo que cambia queda en un diario y se puede deshacer.

## Ajustes que querrás tocar

```sh
lina config                          # todos los ajustes
lina config poner asistente.nombre Jarvis
lina config perfil prudente
lina voz                             # voces disponibles
lina ia                              # con qué IA habla
lina privacidad                      # qué se envía y si se envían capturas
lina doctor                          # si algo no va
```

Más en [configuración](configuracion.md), [proveedores de IA](proveedores-ia.md), [idiomas](idiomas.md) y [seguridad](seguridad.md).
