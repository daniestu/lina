# Hoja de ruta

| Fase | Contenido |
|---|---|
| 0 | Estructura profesional del repositorio *(hecha; falta el uso real de unos días)* |
| 1 | Configuración, perfiles de autonomía y nombre y voz de Lina (`config.toml`, claves en el llavero) *(hecha: ajustes, `lina config`, perfiles, claves y órdenes de voz)* |
| 2 | Seguridad y privilegios: sudo limitado a instalar paquetes, modelo de amenazas, consentimiento de privacidad *(hecha)* |
| 3 | Portabilidad entre distribuciones (Arch, Debian/Ubuntu, Fedora, openSUSE) *(hecha: capa de paquetes y capacidades en `plataforma.py`, [detalles](portabilidad.md))* |
| 4 | Instalador y primer arranque guiado: `install.sh`, atajo automático, `lina bienvenida`, `lina doctor`, `lina update` *(hecha, falta probarla en instalaciones reales; [detalles](instalacion.md))* |
| 5 | Portabilidad de escritorio (KDE Plasma, GNOME, X11, sway/Hyprland) *(hecha, falta probarla en equipos reales distintos de KDE; [detalles](escritorios.md))* |
| 6 | Calidad e ingeniería: código dividido, CI, tipado, cobertura *(hecha: `herramientas.py` y `asistente.py` divididos, CI en tres versiones de Python y cuatro familias de distribución, cobertura con mínimo del 63 %; mypy sigue como aviso informativo mientras se anotan los tipos módulo a módulo)* |
| 7 | Proveedores de IA intercambiables: Gemini, API compatible con OpenAI, Anthropic, modelos locales y de empresa |
| 8 | Internacionalización: idioma configurable, textos y prompts por idioma; el inglés será el primer idioma nuevo, tras la beta |
| 9 | Documentación y publicación: README, licencias, paquete AUR, versión `v0.1.0-beta` |
| 10 | Beta cerrada |

En paralelo, el motor de voz será intercambiable: Piper en local por defecto, con Kokoro y otros como opciones.
