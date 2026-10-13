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
- Cada cambio de comportamiento lleva su prueba. Las pruebas no deben tocar tu `$HOME` real: usan carpetas temporales.
- `ruff check .` y `pytest` en verde antes de abrir la PR.
- **Nunca** subas claves, registros ni datos personales (el `pre-commit` lo comprueba, pero la responsabilidad es tuya).
- Cualquier cosa que ejecute comandos o toque el sistema pasa por las capas de seguridad (`nucleo/herramientas.py`, `nucleo/politica.py`):
  no las saltes ni las debilites sin discutirlo antes en un issue.

## Dónde está cada cosa

Mira [docs/arquitectura.md](docs/arquitectura.md).
