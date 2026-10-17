# Publicar una versión

Para quien mantiene el proyecto. Nada de esto lo hace Lina sola: etiquetar, publicar y subir al AUR necesitan tu cuenta.

## Antes de etiquetar (`v0.1.0-beta`)

1. **Licencias de las voces inglesas** (`docs/creditos.md`): leer la licencia de los datos de `lessac` y `amy`. Si no permiten el uso, quitar la voz de
   `src/lina/voz/voces.py` o dejar el inglés fuera de la beta (`IDIOMAS = ("es",)` en `ajustes.py`).
2. CI en verde en `main` (Ruff, rastros, pruebas con cobertura ≥ 63 % en Python 3.11, 3.12 y 3.13, y las cuatro familias de distribución).
3. `python scripts/comprobar_rastros.py` sin avisos.
4. Probado a mano en un equipo real: `./install.sh`, `lina bienvenida`, `lina doctor --red`, hablar con el atajo, una confirmación por atajo, `lina update`,
   `lina uninstall`. Anotar en la hoja de ruta lo que falle.
5. Versión en `pyproject.toml`: `0.1.0b1` (PEP 440) y en `CHANGELOG.md` pasar «Sin publicar» a `[0.1.0-beta] - AAAA-MM-DD`, dejando un «Sin publicar» vacío encima.
6. Cambiar el clasificador `Development Status` si procede (hoy «3 - Alpha»).

## Etiquetar

```sh
git tag -a v0.1.0-beta -m "Lina 0.1.0-beta"
git push origin main v0.1.0-beta
```

En GitHub: *Releases → Draft a new release* con esa etiqueta, marcada como **pre-release**, y las notas copiadas del CHANGELOG.

## AUR

El paquete (`packaging/aur/PKGBUILD`) no instala Lina en `/usr`: instala las dependencias del sistema y la orden `lina-instalar` (el `install.sh`).

```sh
# primera vez: crear el repositorio vacío siguiendo https://wiki.archlinux.org/title/AUR_submission_guidelines
git clone ssh://aur.archlinux.org/lina-asistente.git && cd lina-asistente   # con el usuario «aur» que indica esa guía
cp ../lina/packaging/aur/{PKGBUILD,lina-asistente.install} .
updpkgsums                              # rellena sha256sums con el tarball de la etiqueta
makepkg -si                             # probarlo en un Arch de verdad (y mejor en un contenedor limpio)
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD lina-asistente.install .SRCINFO && git commit -m "lina-asistente 0.1.0b1" && git push
```

No se ha podido probar `makepkg` desde el entorno de desarrollo, así que el `PKGBUILD` solo está comprobado en cuanto a sintaxis. `namcap PKGBUILD` ayuda a revisarlo.
`lina-instalar` baja el código de la rama principal, no de la etiqueta: si quieres fijar la versión, `LINA_REPO` y una rama o etiqueta propias lo permiten.

## Después

- Anunciar el estado «beta cerrada» solo a quien vaya a probarla (fase 10) y pedir informes con `lina doctor --informe`, que no lleva datos personales.
- Las incidencias de seguridad van por aviso privado de GitHub (ver `SECURITY.md`).
