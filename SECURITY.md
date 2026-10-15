# Seguridad

Lina ejecuta acciones en tu equipo a partir de lo que dices, así que la seguridad es parte central del proyecto.

## Cómo informar de una vulnerabilidad

**No abras un issue público.** Usa «Report a vulnerability» en la pestaña *Security* del repositorio de GitHub
(aviso privado). Responderemos lo antes posible.

Qué se considera y cómo se protege Lina está en [docs/seguridad.md](docs/seguridad.md) (modelo de amenazas, privilegios, privacidad).

Interesa especialmente: saltarse la confirmación de acciones críticas, inyección de instrucciones desde páginas web o archivos,
lectura de claves o secretos, y escalada de privilegios mediante `sudo`.

## Versiones con soporte

Mientras el proyecto esté en beta (0.x), solo se corrige la última versión publicada.

## Qué incluir en el aviso

- Qué versión usas (`lina --version`) y tu distribución (`lina sistema`).
- La orden, frase o contenido que provoca el problema, y qué esperabas que pasara.
- Si la IA intervino (qué le pediste) o es un fallo del propio filtro/instalador.
- No envíes claves reales: tápalas.

Se contesta en unos días. Cuando haya arreglo se publica una versión y se da el crédito que quieras (o ninguno).

## Alcance

Dentro: el código de este repositorio, el ayudante de root `lina-instalar` y el instalador de la regla de sudoers (`lina privilegios`), los bloqueos y confirmaciones,
la gestión de claves y el consentimiento de privacidad. Fuera: fallos de la IA que no dependan de Lina (por ejemplo, que un modelo diga algo erróneo), de Google/Piper/Whisper
o de tu distribución.
