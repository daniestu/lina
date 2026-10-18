# Lina

Español · [English](README.en.md)

Asistente de voz para el escritorio Linux, pensado primero para hablar en español (el inglés es experimental). Le hablas («Oye Lina, …») o pulsas un atajo, y ella entiende lo que
quieres, lo hace en tu equipo (abrir programas, ajustar el sistema, manejar ventanas, buscar, escribir documentos…) y te contesta con voz.

> **Estado: beta temprana (0.1).** Funciona de forma completa en Arch Linux y derivados con KDE Plasma (Wayland). El núcleo ya se prueba también en Debian/Ubuntu,
> Fedora y openSUSE ([portabilidad](docs/portabilidad.md)); GNOME, Cinnamon, XFCE, sway y Hyprland tienen soporte, aún sin probar en equipos reales ([escritorios](docs/escritorios.md)); el resto del plan está en la [hoja de ruta](docs/hoja-de-ruta.md).

## Qué hace distinto

- **Entiende la intención, no frases fijas.** Pide las cosas con tus palabras.
- **Descubre cómo hacerlo ella misma** y recuerda lo que ha comprobado que funciona («recetas»).
- **Autónoma, pero con frenos.** Lo peligroso (borrar de verdad, tocar discos o el arranque, instalar software de fuera…) solo se
  confirma con el atajo de teclado, nunca por voz. Todo lo que cambia queda en un diario y se puede deshacer.
- **Tus datos son tuyos.** Sin telemetría. Las capturas de pantalla solo se envían con tu consentimiento, y hay un modo privado.
- **Barata.** Funciona con la clave gratuita de Gemini; una clave de pago es opcional y tiene un tope mensual.
- **Sin atarte a una IA.** Gemini por defecto, y se puede cambiar a Anthropic, a OpenAI o a cualquier servicio compatible (OpenRouter, Groq, Ollama en tu equipo, un servidor de tu empresa) con `lina ia`. [Cómo](docs/proveedores-ia.md).

## Instalación (resumen)

```sh
git clone https://github.com/daniestu/lina.git
cd lina
./install.sh
```

El instalador te enseña cada paso, crea el atajo de teclado y el servicio, y termina con `lina bienvenida`, que te guía para poner tu clave de Gemini
(gratuita), probar el micrófono y decidir la libertad y la privacidad de Lina. Después: `lina doctor` para comprobar que todo está bien y `lina update`
para actualizar. Más detalle en [instalación](docs/instalacion.md). En Arch Linux y derivados habrá además un paquete del AUR (`lina-asistente`, orden `lina-instalar`)
cuando se publique la primera versión; mientras tanto, usa el instalador. Para saber qué pedirle: [cómo se usa](docs/uso.md).

## Ajustes

Todo está en un único archivo, `~/.config/lina/config.toml`, y se cambia con `lina config` (se aplica sin reiniciar):

```sh
lina config                          # ver todos los ajustes
lina config poner asistente.nombre Jarvis
lina config perfil prudente          # autonomo (por defecto), equilibrado o prudente
lina voz                             # elegir otra voz
```

Cada ajuste está explicado en [docs/configuracion.md](docs/configuracion.md).

## Privacidad y permisos

```sh
lina privacidad       # qué se envía a la IA y qué no; decides si se envían capturas de pantalla
lina privilegios      # qué permisos de administrador tiene Lina (por defecto, ninguno)
lina olvidar          # borrar lo que guarda de ti
```

Sin telemetría. Las capturas no se envían hasta que lo permites, y la contraseña de administrador nunca pasa por Lina. Detalles y modelo de amenazas en
[docs/seguridad.md](docs/seguridad.md).

## Documentación

- [Cómo se usa](docs/uso.md)
- [Instalación](docs/instalacion.md)
- [Proveedores de IA](docs/proveedores-ia.md)
- [Idiomas](docs/idiomas.md)
- [Portabilidad entre distribuciones](docs/portabilidad.md)
- [Escritorios compatibles](docs/escritorios.md)
- [Configuración](docs/configuracion.md)
- [Arquitectura](docs/arquitectura.md)
- [Seguridad y confirmaciones](docs/seguridad.md)
- [Hoja de ruta](docs/hoja-de-ruta.md)
- [Publicar una versión](docs/publicacion.md) (para quien mantiene el proyecto)
- [Créditos y licencias de terceros](docs/creditos.md)
- [Cómo contribuir](CONTRIBUTING.md)

## Licencia

[GNU AGPL-3.0 o posterior](LICENSE). Es código abierto: puedes usarlo, estudiarlo, modificarlo y compartirlo. Si compartes una versión modificada, o la ofreces como servicio
por Internet, tienes que publicar tu código con la misma licencia y conservar los avisos de copyright. El nombre «Lina» y su logotipo no van con la licencia: ver
[TRADEMARKS.md](TRADEMARKS.md).
