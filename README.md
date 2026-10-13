# Lina

Asistente de voz en español para el escritorio Linux. Le hablas («Oye Lina, …») o pulsas un atajo, y ella entiende lo que
quieres, lo hace en tu equipo (abrir programas, ajustar el sistema, manejar ventanas, buscar, escribir documentos…) y te contesta con voz.

> **Estado: beta temprana (0.1).** Funciona de forma completa en Arch Linux y derivados con KDE Plasma (Wayland). El soporte para otras
> distribuciones y escritorios está en marcha: mira la [hoja de ruta](docs/hoja-de-ruta.md).

## Qué hace distinto

- **Entiende la intención, no frases fijas.** Pide las cosas con tus palabras.
- **Descubre cómo hacerlo ella misma** y recuerda lo que ha comprobado que funciona («recetas»).
- **Autónoma, pero con frenos.** Lo peligroso (borrar de verdad, tocar discos o el arranque, instalar software de fuera…) solo se
  confirma con el atajo de teclado, nunca por voz. Todo lo que cambia queda en un diario y se puede deshacer.
- **Tus datos son tuyos.** Sin telemetría. Las capturas de pantalla solo se envían con tu consentimiento, y hay un modo privado.
- **Barata.** Funciona con la clave gratuita de Gemini; una clave de pago es opcional y tiene un tope mensual.

## Instalación (resumen)

```sh
git clone https://github.com/daniestu/lina.git
cd lina
./install.sh
```

Después, crea un atajo de teclado global (por ejemplo `Meta+Espacio`) que ejecute `lina pulsar`, y guarda tu clave de Gemini cuando
Lina te la pida. Todo lo configurable está en `~/.config/lina/`.

## Documentación

- [Arquitectura](docs/arquitectura.md)
- [Seguridad y confirmaciones](docs/seguridad.md)
- [Hoja de ruta](docs/hoja-de-ruta.md)
- [Créditos y licencias de terceros](docs/creditos.md)
- [Cómo contribuir](CONTRIBUTING.md)

## Licencia

[MIT](LICENSE).
