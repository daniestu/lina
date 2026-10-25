# Cómo contribuir

¡Gracias por querer ayudar! Lina está en beta temprana: lo más útil ahora es **probarla en tu distribución** e informar de lo que falle.

## Entorno de desarrollo

```sh
git clone https://github.com/daniestu/lina.git && cd lina
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

Necesitas Python 3.11 o superior.

## Reglas

- **Commits** con [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- **Código y mensajes al usuario en español**; nombres de variables y módulos también en español, como el resto del proyecto.
- Cada cambio de comportamiento lleva su prueba. Las pruebas no deben tocar tu `$HOME` real: `tests/conftest.py` les da a todas una casa temporal en
  `tests/.casa-pruebas/` (con `HOME`, las carpetas XDG y `XDG_RUNTIME_DIR` dentro, sin bus de sesión ni `DISPLAY`/`WAYLAND_DISPLAY`) antes de importar
  nada de Lina, porque `rutas.py` fija sus carpetas al importarse; no importes Lina antes que el conftest. Esa casa tiene que estar fuera de las zonas
  desechables (`/tmp`…): si clonas el repositorio ahí, `tests/test_aislamiento.py` falla y te dice qué hacer (o usa `LINA_PRUEBAS_BASE`). Para lo de
  cada prueba, `tmp_path` y `monkeypatch`, como siempre.
- `ruff check .` y `pytest` en verde antes de abrir la PR.
- **Nunca** subas claves, registros ni datos personales (el `pre-commit` lo comprueba, pero la responsabilidad es tuya).
- Cualquier cosa que ejecute comandos o toque el sistema pasa por las capas de seguridad (`nucleo/herramientas.py`, `nucleo/politica.py`):
  no las saltes ni las debilites sin discutirlo antes en un issue.

## Licencia de tus contribuciones

Lina es **AGPL-3.0 o posterior** (ver `LICENSE`). Al enviar una contribución (código, documentación, traducciones…) confirmas que:

1. **Es tuya o tienes derecho a enviarla** (certificado de origen del desarrollador, <https://developercertificate.org>). Añade `Signed-off-by: Tu Nombre <correo>` a tus commits
   (`git commit -s`).
2. **Concedes al mantenedor del proyecto** una licencia perpetua, mundial, gratuita y no exclusiva para usar, modificar, distribuir y **sublicenciar tu contribución bajo
   cualquier licencia**, incluidas licencias comerciales o propietarias. Conservas el copyright de lo que escribes y puedes usarlo como quieras. Esto permite al
   proyecto ofrecer licencias comerciales o cambiar de licencia en el futuro; la versión que ya se publicó con la AGPL sigue siéndolo.

Si no estás de acuerdo, no envíes la contribución. *(Este texto es un borrador sin revisión legal.)*

## Dónde está cada cosa

Mira [docs/arquitectura.md](docs/arquitectura.md).
