#!/usr/bin/env python3
"""
Política de autonomía del asistente: qué hace solo y qué te pregunta antes.

Los datos viven en politica.txt (para leerlos y editarlos con comodidad). Este módulo solo sabe leerlos, validarlos
y entregarlos; la lógica que los aplica está en herramientas.py. El archivo se relee solo cuando lo guardas; si falta
una sección, se usa la de fábrica. No depende de audio ni de IA, para poder probarlo por separado.
"""
import copy
import re
import time
from lina.nucleo import ajustes as AJ
from lina.nucleo import rutas as RUT

ARCHIVO = RUT.editable("politica.txt")

SECCIONES_CRITICAS = ["discos_y_particiones", "arranque", "cuentas_y_credenciales", "red_expuesta", "borrado",
                      "software_de_fuera", "dinero", "gasto_del_asistente", "sesion", "persistencia", "archivos_de_paquetes"]
SECCIONES = ["modo", "limites", "contenido_de_fuera"] + SECCIONES_CRITICAS + ["zonas_desechables"]
SECCIONES_OPCIONALES = {"contenido_de_fuera", "archivos_de_paquetes"}      # si tu archivo no la tiene, se usa la de fábrica SIN avisar (es nueva)

TIPOS_CON_VARIOS_VALORES = {"programa", "ruta", "servicio", "paquete", "ejecutar_desde"}   # una regla por cada valor
TIPOS_CON_PROGRAMA = {"subcomando", "bandera"}                                             # PROGRAMA + opciones
MODOS = {"alta", "prudente"}
# Rutas que harían crítico absolutamente todo: se ignoran y se avisa
RUTAS_DEMASIADO_AMPLIAS = {"/", "/*", "*", "~", "~/", "~/*", "$HOME", "/home", "/home/*"}

# @@FABRICA@@
TEXTO_DE_FABRICA = '# ============================================================================================\n#  POLÍTICA DE AUTONOMÍA DEL ASISTENTE\n#  Qué hace por su cuenta y qué te pregunta antes.\n# ============================================================================================\n#\n#  CÓMO FUNCIONA\n#   - El asistente actúa SOLO, sin preguntar, salvo que lo que va a hacer encaje en alguna de las\n#     secciones CRÍTICAS de este archivo. En ese caso deja la acción preparada y espera tu confirmación.\n#   - Además hay un BLOQUEO DURO en el código (borrar el sistema, formatear discos, leer claves,\n#     descargar y ejecutar scripts de internet...). Eso no se puede desbloquear desde aquí ni diciendo que sí.\n#   - Solo LEER algo (cat, ls, grep...) nunca es crítico, aunque sea una ruta crítica.\n#   - Se relee solo al guardar el archivo: NO hace falta reiniciar. Si te equivocas al escribir, el registro\n#     del asistente (journalctl --user -u lina) te avisa de qué línea es y usa los valores de fábrica\n#     de la sección que falte.\n#   - Este archivo lo protege el código: el asistente NO puede modificarlo por voz. Lo que se pregunta y lo\n#     que no lo decides tú, a mano.\n#\n#  FORMATO de las líneas dentro de cada sección crítica  (una regla por línea; # para comentarios):\n#     motivo TEXTO                      lo que se te dice al pedir confirmación\n#     programa NOMBRE                   cualquier uso de ese programa (admite *, por ejemplo  mkfs.*)\n#     subcomando PROGRAMA PAL1 PAL2     ese programa con alguna de esas palabras (btrfs balance)\n#     bandera PROGRAMA OPC1 OPC2        ese programa con alguna de esas opciones (pacman -U)\n#     ruta PATRON                       si el comando modifica algo en esa ruta. Admite *; sin * incluye\n#                                       todo lo que haya dentro. ~ es tu carpeta personal.\n#     servicio UNIDAD                   systemctl start/stop/restart/enable/disable... de ese servicio\n#     paquete PATRON                    instalar o quitar ese paquete con pacman, paru o yay\n#     ejecutar_desde RUTA               ejecutar un programa o script que esté en esa ruta\n#\n#  PERFIL Y ATAJOS\n#   - El perfil (autonomo, equilibrado o prudente) y los interruptores por categoría están en config.toml, sección [autonomia]\n#     (lina config perfil prudente). Se aplican ENCIMA de este archivo: pueden apretar el modo o aflojar categorías, pero\n#     discos, arranque, cuentas, dinero y gasto se confirman siempre.\n#\n#  CÓMO AJUSTARLO\n#   - ¿Quieres que te pregunte MENOS por algo? Borra la línea (o la sección entera).\n#   - ¿Quieres que te pregunte MÁS? Añade líneas, o cambia  autonomia  a  prudente  (abajo).\n#   - Si dejas una sección sin ninguna línea, esa categoría queda sin vigilar.\n# ============================================================================================\n\n\n# --------------------------------------------------------------------------------------------\n#  MODO\n#    alta      actúa solo en todo lo que no sea crítico (lo que has pedido)\n#    prudente  como antes: pide confirmación para casi todo lo que cambie algo. Útil si algún día quieres\n#              apretar las tuercas sin tocar nada más.\n# --------------------------------------------------------------------------------------------\n[modo]\nautonomia alta\n\n\n# --------------------------------------------------------------------------------------------\n#  LÍMITES\n#    borrados_masivos   a la papelera se pueden mandar hasta este número de archivos de golpe. Más de eso, o\n#                       cualquier comodín (*), se considera borrado masivo y pide confirmación.\n# --------------------------------------------------------------------------------------------\n[limites]\nborrados_masivos 10\n\n\n# --------------------------------------------------------------------------------------------\n#  CONTENIDO DE FUERA  (buscar en internet, descargar cosas...)\n#    no   El asistente puede buscar en internet, probar lo que encuentre y, si no funciona, probar otra cosa, todo\n#         por su cuenta y SIN pedirte confirmación. Lo crítico de más abajo SÍ la sigue pidiendo. (Lo que has pedido.)\n#    si   Después de leer algo de internet o de un archivo descargado, los cambios «libres» de esa misma petición\n#         piden confirmación, por si una web trajera instrucciones escondidas para la IA.\n#  Con «no» sigues protegido por: las secciones críticas de abajo, los bloqueos duros del código, las snapshots\n#  automáticas y el diario con «deshaz lo último». Lo que NO te protege: una web maliciosa podría hacer que la IA\n#  cambie por su cuenta cosas no críticas (siempre anotadas y casi siempre reversibles).\n# --------------------------------------------------------------------------------------------\n[contenido_de_fuera]\nfrenar_cambios no\n\n\n# ============================================================================================\n#  SECCIONES CRÍTICAS (piden confirmación)\n# ============================================================================================\n\n# 1) Particiones, formatear o tocar otros discos (otros sistemas y discos).\n#    Copiar archivos a otro disco es normal y no entra aquí: lo que vigila es tocar los discos en sí.\n[discos_y_particiones]\nmotivo toca discos o particiones (también los de otros sistemas)\nruta /dev/nvme*\nruta /dev/sd*\nruta /dev/vd*\nruta /dev/hd*\nruta /dev/mmcblk*\nruta /dev/disk/*\nruta /dev/mapper/*\nruta /dev/md*\nprograma mount\nprograma umount\nprograma fsck\nprograma fsck.*\nprograma e2fsck\nprograma ntfsfix\nprograma ntfsresize\nprograma resize2fs\nprograma tune2fs\nprograma losetup\nprograma swapon\nprograma swapoff\nsubcomando btrfs balance check device rescue resize defragment scrub\n\n\n# 2) Arranque: gestor de arranque (Limine, GRUB, systemd-boot...), fstab, parámetros del kernel, initramfs.\n#    Los paquetes de esta sección se vigilan al instalarlos o quitarlos (una actualización normal, pacman -Syu,\n#    no entra: ya crea su propia snapshot).\n[arranque]\nmotivo toca el arranque del sistema, el kernel o los controladores base\nruta /boot\nruta /efi\nruta /etc/fstab\nruta /etc/crypttab\nruta /etc/default/limine\nruta /etc/limine*\nruta /etc/default/grub\nruta /etc/kernel\nruta /etc/mkinitcpio.conf\nruta /etc/mkinitcpio.d\nruta /etc/modprobe.d\nruta /etc/modules-load.d\nruta /etc/sysctl.conf\nruta /etc/sysctl.d\nruta /usr/lib/modules\nruta /sys/module\nruta /proc/sys\nprograma mkinitcpio\nprograma limine-*\nprograma efibootmgr\nprograma bootctl\nprograma grub-*\nprograma update-grub\nprograma sbctl\nprograma dracut\nprograma kernel-install\nprograma depmod\nprograma modprobe\nprograma insmod\nprograma rmmod\nbandera sysctl -w --write -p --load --system\npaquete linux\npaquete linux-*\npaquete limine*\npaquete mkinitcpio*\npaquete systemd\npaquete systemd-*\npaquete glibc\npaquete pacman\npaquete filesystem\npaquete base\npaquete btrfs-progs\npaquete nvidia*\npaquete lib32-nvidia*\n\n\n# 3) Usuarios, contraseñas, permisos de administrador, claves y credenciales.\n[cuentas_y_credenciales]\nmotivo toca usuarios, contraseñas, permisos de administrador o claves\nruta /etc/passwd\nruta /etc/shadow\nruta /etc/group\nruta /etc/gshadow\nruta /etc/sudoers\nruta /etc/sudoers.d\nruta /etc/pam.d\nruta /etc/security\nruta /etc/polkit-1\nruta /usr/share/polkit-1\nruta ~/.ssh\nruta ~/.gnupg\nruta ~/.password-store\nruta ~/.local/share/kwalletd\nprograma passwd\nprograma chpasswd\nprograma chage\nprograma gpasswd\nprograma groupadd\nprograma groupdel\nprograma groupmod\nprograma useradd\nprograma userdel\nprograma usermod\nprograma visudo\nprograma ssh-keygen\nprograma ssh-add\nprograma gpg\nprograma gpg2\nprograma kwallet-query\nprograma secret-tool\nprograma keyctl\n\n\n# 4) Red expuesta: cortafuegos, SSH, abrir puertos.\n[red_expuesta]\nmotivo cambia el cortafuegos, SSH o algo que expone tu PC a la red\nprograma ufw\nprograma iptables\nprograma ip6tables\nprograma iptables-restore\nprograma nft\nprograma firewall-cmd\nservicio sshd\nservicio ssh\nservicio nftables\nservicio ufw\nservicio firewalld\nservicio iptables\nservicio ip6tables\nservicio avahi-daemon\nservicio smb\nservicio smbd\nservicio nmb\nservicio nfs-server\nservicio nginx\nservicio httpd\nservicio apache2\nruta /etc/ssh\nruta /etc/nftables.conf\nruta /etc/ufw\nruta /etc/firewalld\nruta /etc/iptables\nruta /etc/hosts\nruta /etc/resolv.conf\nruta /etc/NetworkManager\nruta /etc/systemd/network\nruta /etc/systemd/resolved.conf\nruta /etc/systemd/resolved.conf.d\nruta /etc/samba\nruta /etc/exports\nruta /etc/nginx\nruta /etc/httpd\nruta /etc/apache2\nbandera nc -l --listen\nbandera ncat -l --listen\n\n\n# 5) Borrar sin pasar por la papelera, o borrados masivos.\n#    Los borrados normales de tus archivos ya van a la papelera y no entran aquí. Aquí entra borrar de verdad\n#    (rm, shred...) salvo en las zonas desechables de abajo, y mandar muchos archivos de golpe a la papelera\n#    (ver [limites]).\n[borrado]\nmotivo borra de forma definitiva, o muchos archivos de golpe\nprograma rm\nprograma unlink\nprograma shred\nprograma wipe\nprograma srm\nprograma truncate\nprograma dd\n\n\n# 6) Ejecutar scripts bajados de internet, o software de fuera de las fuentes de confianza.\n#    Va directo: repositorios oficiales de pacman y Flathub. Pide confirmación: el AUR (paru, yay), pip, npm,\n#    cargo..., paquetes sueltos (pacman -U), añadir repositorios y ejecutar lo que haya en Descargas.\n[software_de_fuera]\nmotivo instala o ejecuta software de fuera de las fuentes de confianza\nprograma paru\nprograma yay\nprograma pikaur\nprograma aurman\nprograma makepkg\nprograma pacman-key\nprograma pip\nprograma pip3\nprograma pipx\nprograma uv\nprograma npm\nprograma npx\nprograma pnpm\nprograma yarn\nprograma cargo\nprograma go\nprograma gem\nprograma composer\nprograma *.AppImage\nprograma *.run\nbandera pacman -U --upgrade\nsubcomando flatpak remote-add remote-modify remote-delete\nruta /etc/pacman.conf\nruta /etc/pacman.d\nruta /usr/local/bin\nruta /usr/local/sbin\nruta /opt\nejecutar_desde ~/Descargas\nejecutar_desde ~/Downloads\n\n\n# 7) Cualquier cosa que cueste dinero.\n#    Desde la terminal solo se pueden vigilar servicios de pago en la nube. Las compras en una web las evita\n#    la regla de la IA de no comprar nada, y el gasto del propio asistente tiene su sección aparte.\n[dinero]\nmotivo puede costar dinero\nprograma aws\nprograma gcloud\nprograma az\nprograma doctl\nprograma hcloud\nprograma linode-cli\nprograma terraform\nprograma pulumi\nprograma stripe\n\n\n# 8) Subir el límite de gasto del asistente (se estrena al llegar el control de gasto; solo con tu voz).\n[gasto_del_asistente]\nmotivo cambia el límite de gasto del asistente\n\n\n# 9) Apagar, reiniciar o cerrar sesión (tira todo lo que tengas abierto).\n#    Sección extra, no incluida en la lista básica. Si no la quieres, borra la sección entera.\n[sesion]\nmotivo apaga, reinicia o cierra tu sesión, o reinicia el escritorio (perderías lo que tengas abierto)\nprograma reboot\nprograma poweroff\nprograma shutdown\nprograma halt\nprograma kexec\nsubcomando systemctl reboot poweroff halt kexec suspend hibernate hybrid-sleep suspend-then-hibernate soft-reboot\nsubcomando loginctl terminate-user terminate-session kill-user kill-session poweroff reboot suspend hibernate\nservicio sddm\nservicio display-manager\nservicio systemd-logind\nservicio plasma-kwin_wayland\nservicio plasma-kwin_x11\nservicio plasma-workspace\nservicio plasma-plasmashell\nprograma kwin_wayland\nprograma kwin_x11\n\n\n# 10) Crear servicios o tareas automáticas del sistema (formas de dejar algo ejecutándose para siempre).\n#     Sección extra, no incluida en la lista básica. Si no la quieres, borra la sección entera.\n[persistencia]\nmotivo crea servicios o tareas automáticas, o cambia lo que se carga siempre al iniciar sesión o al abrir cualquier juego\nruta /etc/systemd/system\nruta /usr/lib/systemd/system\nruta /etc/cron*\nruta /var/spool/cron\nruta /etc/profile\nruta /etc/profile.d\nruta /etc/environment\nruta /etc/xdg/autostart\nruta ~/.config/autostart\nruta ~/.config/systemd/user\nruta ~/.bashrc\nruta ~/.bash_profile\nruta ~/.bash_login\nruta ~/.profile\nruta ~/.zshrc\nruta ~/.zshenv\nruta ~/.zprofile\nruta ~/.config/fish\nruta ~/.config/environment.d\nruta ~/.config/plasma-workspace/env\nruta ~/.local/share/vulkan\nruta ~/.config/vulkan\nruta /etc/vulkan\nruta /usr/share/vulkan\nruta /etc/ld.so.preload\nruta /etc/ld.so.conf.d\nruta /etc/udev/rules.d\nruta /usr/lib/udev/rules.d\nprograma crontab\nprograma at\nprograma batch\n\n\n# 11) Modificar archivos que pertenecen a programas instalados (/usr/bin, /usr/lib, /usr/share...).\n#     Evita que el asistente «arregle» un programa editando /usr/bin con sed o creando enlaces ahí.\n#     Esos archivos son de pacman: un parche a mano se pierde o rompe cosas al actualizar. Instalar con pacman NO entra aquí.\n#     Si no la quieres, borra la sección entera.\n[archivos_de_paquetes]\nmotivo modifica archivos de programas instalados (/usr, /bin...): un parche a mano se pierde o rompe al actualizar\nruta /usr/bin\nruta /usr/sbin\nruta /usr/lib\nruta /usr/lib64\nruta /usr/libexec\nruta /usr/share\nruta /usr/include\nruta /bin\nruta /sbin\nruta /lib\nruta /lib64\n\n\n# ============================================================================================\n#  ZONAS DESECHABLES\n#  Aquí SÍ puede borrar de verdad (rm) sin preguntar: son cachés y temporales que se regeneran.\n#  Si en una de estas rutas hay cosas tuyas, bórrala de la lista.\n# ============================================================================================\n[zonas_desechables]\nruta /tmp\nruta /var/tmp\nruta /dev/shm\nruta ~/.cache\nruta /var/cache\n'
# @@FIN_FABRICA@@


def _aplicar_perfil(datos, de_fabrica, aj):
    """Pone encima de politica.txt el perfil de autonomía y los interruptores de config.toml. Solo puede apretar el modo (prudente, frenar
    cambios tras leer internet); las categorías en «libre» dejan de pedir confirmación y las que están en «confirmar» recuperan sus reglas de
    fábrica si el archivo las había vaciado. Las de AJ.SIEMPRE_CONFIRMAN no se tocan nunca."""
    modo, frenar, categorias = AJ.politica_efectiva(aj)
    if modo == "prudente":
        datos["modo"] = "prudente"
    if frenar:
        datos["frenar_contenido_de_fuera"] = True
    fabrica = {s["nombre"]: s for s in de_fabrica["secciones"]}
    for sec in datos["secciones"]:
        estado = categorias.get(sec["nombre"])
        if estado is None or sec["nombre"] in AJ.SIEMPRE_CONFIRMAN:
            continue
        if estado == "libre":
            sec["reglas"] = []
        elif estado == "confirmar" and not sec["reglas"]:
            sec["reglas"] = copy.deepcopy(fabrica[sec["nombre"]]["reglas"])
            sec["motivo"] = fabrica[sec["nombre"]]["motivo"]
    datos["perfil"] = aj.get("autonomia", "perfil")


def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


def _parsear(texto):
    """Devuelve ({sección: [(nº de línea, tipo, resto)]}, [avisos])."""
    secciones, avisos, actual = {}, [], None
    for n, linea in enumerate(texto.splitlines(), 1):
        l = re.split(r"\s#", linea.strip(), maxsplit=1)[0].strip()
        if not l or l.startswith("#"):
            continue
        if l.startswith("["):
            m = re.fullmatch(r"\[([a-z_]+)\]", l)
            if not m:
                avisos.append(f"línea {n}: «{l}» parece una sección mal escrita (se ignora)")
                actual = None
            elif m.group(1) not in SECCIONES:
                avisos.append(f"línea {n}: la sección [{m.group(1)}] no existe (se ignora). Las válidas son: {', '.join(SECCIONES)}")
                actual = None
            else:
                actual = m.group(1)
                secciones.setdefault(actual, [])
            continue
        if actual is None:
            avisos.append(f"línea {n}: «{l}» está fuera de una sección válida (se ignora)")
            continue
        partes = l.split(None, 1)
        secciones[actual].append((n, partes[0], partes[1].strip() if len(partes) > 1 else ""))
    return secciones, avisos


def _construir(secciones, avisos):
    """Convierte las líneas en reglas listas para usar, validándolas."""
    datos = {"modo": "alta", "limites": {"borrados_masivos": 10}, "frenar_contenido_de_fuera": False, "secciones": [], "desechables": []}
    for n, tipo, resto in secciones.get("contenido_de_fuera", []):
        if tipo == "frenar_cambios" and resto in ("si", "no"):
            datos["frenar_contenido_de_fuera"] = resto == "si"
        else:
            avisos.append(f"línea {n}: en [contenido_de_fuera] solo vale «frenar_cambios si» o «frenar_cambios no»; uso «si» por si acaso")
            datos["frenar_contenido_de_fuera"] = True
    for n, tipo, resto in secciones.get("modo", []):
        if tipo != "autonomia" or resto not in MODOS:
            avisos.append(f"línea {n}: en [modo] solo vale «autonomia alta» o «autonomia prudente»; uso «prudente» por si acaso")
            datos["modo"] = "prudente"
        else:
            datos["modo"] = resto
    for n, tipo, resto in secciones.get("limites", []):
        if tipo == "borrados_masivos" and resto.isdigit() and int(resto) >= 1:
            datos["limites"]["borrados_masivos"] = int(resto)
        else:
            avisos.append(f"línea {n}: en [limites] solo vale «borrados_masivos NÚMERO» (1 o más); ignorada")
    for nombre in SECCIONES_CRITICAS:
        sec = {"nombre": nombre, "motivo": "es una acción crítica", "reglas": []}
        for n, tipo, resto in secciones.get(nombre, []):
            if tipo == "motivo":
                if resto:
                    sec["motivo"] = resto
                continue
            if tipo in TIPOS_CON_VARIOS_VALORES:
                for v in resto.split():
                    if tipo == "ruta" and v in RUTAS_DEMASIADO_AMPLIAS:
                        avisos.append(f"línea {n}: la ruta «{v}» abarcaría todo y haría crítico absolutamente todo: se ignora")
                        continue
                    sec["reglas"].append((tipo, v))
                if not resto:
                    avisos.append(f"línea {n}: «{tipo}» sin ningún valor; ignorada")
            elif tipo in TIPOS_CON_PROGRAMA:
                valores = resto.split()
                if len(valores) < 2:
                    avisos.append(f"línea {n}: «{tipo}» necesita un programa y al menos una palabra u opción; ignorada")
                else:
                    sec["reglas"].append((tipo, valores))
            else:
                avisos.append(f"línea {n}: no entiendo «{tipo}» en [{nombre}] (los tipos válidos son: motivo, "
                              f"{', '.join(sorted(TIPOS_CON_VARIOS_VALORES | TIPOS_CON_PROGRAMA))}); ignorada")
        datos["secciones"].append(sec)
    for n, tipo, resto in secciones.get("zonas_desechables", []):
        if tipo != "ruta":
            avisos.append(f"línea {n}: en [zonas_desechables] solo valen líneas «ruta PATRON»; ignorada")
            continue
        for v in resto.split():
            if v in RUTAS_DEMASIADO_AMPLIAS:
                avisos.append(f"línea {n}: la zona desechable «{v}» abarcaría todo: se ignora")
            else:
                datos["desechables"].append(v)
    if not any(s["reglas"] for s in datos["secciones"]):
        avisos.append("no queda ninguna regla crítica: todo lo que no esté bloqueado por el código se hará sin preguntar")
    return datos


_cache = {"marca": "sin leer", "datos": None}


def datos():
    """La política actual; vuelve a leer politica.txt y config.toml solo si han cambiado."""
    try:
        marca_txt = ARCHIVO.stat().st_mtime_ns
    except OSError:
        marca_txt = None
    aj = AJ.actuales(log=log)
    marca_total = (marca_txt, aj.marca)
    if _cache["datos"] is not None and _cache["marca"] == marca_total:
        return _cache["datos"]
    marca = marca_txt                                    # (abajo solo se mira si politica.txt existe)
    avisos = []
    de_fabrica, _ = _parsear(TEXTO_DE_FABRICA)
    if marca is None:
        avisos.append(f"no encuentro {ARCHIVO.name}: uso la política de fábrica")
        secciones = dict(de_fabrica)
    else:
        try:
            secciones, avisos = _parsear(ARCHIVO.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            avisos.append(f"no he podido leer {ARCHIVO.name} ({e}): uso la política de fábrica")
            secciones = dict(de_fabrica)
        for nombre in SECCIONES:
            if nombre not in secciones:
                if nombre not in SECCIONES_OPCIONALES:
                    avisos.append(f"falta la sección [{nombre}]: uso la de fábrica")
                secciones[nombre] = de_fabrica.get(nombre, [])
    resultado = _construir(secciones, avisos)
    _aplicar_perfil(resultado, _construir(de_fabrica, []), aj)
    if _cache["datos"] is None:
        log(f"Política de autonomía cargada de {ARCHIVO.name} (modo {resultado['modo']})")
    else:
        log(f"{ARCHIVO.name} cambiado: política recargada (modo {resultado['modo']})")
    for aviso in avisos:
        log(f"   Aviso en {ARCHIVO.name}: {aviso}")
    _cache["marca"], _cache["datos"] = marca_total, resultado
    return resultado


def cargar():
    """Fuerza la lectura (útil al arrancar, para ver los avisos en el registro)."""
    return datos()
