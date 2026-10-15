"""Gestor de paquetes por familia (Arch, Debian/Ubuntu, Fedora, openSUSE): lo que Lina entiende, instala, comprueba y deshace en cada una."""
import pytest

from lina.nucleo import grupos as G
from lina.nucleo import herramientas as H
from lina.nucleo import plataforma as PL
from lina.nucleo import politica as PO
from lina.nucleo import rutas as RUT

FAMILIAS = ["arch", "debian", "fedora", "suse"]

OS_RELEASE = {
    "arch": {"ID": "arch"},
    "cachyos": {"ID": "cachyos", "ID_LIKE": "arch"},
    "ubuntu": {"ID": "ubuntu", "ID_LIKE": "debian"},
    "debian": {"ID": "debian"},
    "mint": {"ID": "linuxmint", "ID_LIKE": "ubuntu debian"},
    "fedora": {"ID": "fedora"},
    "rocky": {"ID": "rocky", "ID_LIKE": "rhel centos fedora"},
    "tumbleweed": {"ID": "opensuse-tumbleweed", "ID_LIKE": "opensuse suse"},
    "leap": {"ID": "opensuse-leap", "ID_LIKE": "suse opensuse"},
}


@pytest.fixture(autouse=True)
def politica_de_fabrica(tmp_path, monkeypatch):
    copia = tmp_path / "politica.txt"
    copia.write_text((RUT.DEFECTOS / "politica.txt").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(PO, "ARCHIVO", copia)
    PO._cache.update(marca="sin leer", datos=None)
    yield
    PO._cache.update(marca="sin leer", datos=None)


@pytest.fixture
def en(monkeypatch):
    def fijar(familia):
        monkeypatch.setenv("LINA_DISTRO", familia)
        PO._cache.update(marca="sin leer", datos=None)
    return fijar


# ---------- detección ----------
@pytest.mark.parametrize("clave,familia", [("arch", "arch"), ("cachyos", "arch"), ("ubuntu", "debian"), ("debian", "debian"), ("mint", "debian"),
                                           ("fedora", "fedora"), ("rocky", "fedora"), ("tumbleweed", "suse"), ("leap", "suse")])
def test_familia_por_os_release(clave, familia):
    assert PL.familia_de(OS_RELEASE[clave]) == familia


def test_distro_desconocida_y_forzada():
    assert PL.familia_de({"ID": "gentoo"}) is None
    d = PL.detectar(os_release={"ID": "gentoo"}, entorno={}, which=lambda _: None)
    assert d["familia"] is None and d["gestor"] is None and not d["tiene_gestor"]
    d = PL.detectar(os_release={"ID": "gentoo"}, entorno={"LINA_DISTRO": "debian"}, which=lambda _: "/usr/bin/apt-get")
    assert d["familia"] == "debian" and d["gestor"] == "apt-get" and d["tiene_gestor"]
    assert PL.detectar(os_release={"ID": "arch"}, entorno={"LINA_DISTRO": "rarisimo"}, which=lambda _: None)["familia"] == "arch"


# ---------- órdenes por familia ----------
@pytest.mark.parametrize("familia,cabecera", [("arch", ["pacman", "-S"]), ("debian", ["apt-get", "install"]), ("fedora", ["dnf", "install"]),
                                              ("suse", ["zypper", "--non-interactive", "install"])])
def test_orden_instalar(familia, cabecera):
    o = PL.orden("instalar", ["vlc"], familia)
    assert o[:len(cabecera)] == cabecera and o[-1] == "vlc"


@pytest.mark.parametrize("familia", FAMILIAS)
def test_ordenes_de_quitar_buscar_y_actualizar(familia):
    assert PL.orden("quitar", ["vlc"], familia)[-1] == "vlc"
    assert PL.orden("buscar", ["vlc"], familia)[-1] == "vlc"
    cadena = PL.ordenes_actualizar(familia)
    assert cadena and all(isinstance(o, list) for o in cadena)
    assert len(PL.ordenes_actualizar("debian")) == 2                      # apt: update y luego upgrade
    assert PL.orden("formatear", ["x"], familia) is None


def test_nombres_logicos_se_traducen():
    assert PL.orden("instalar", ["pygobject"], "debian")[-1] == "python3-gi"
    assert PL.orden("instalar", ["pygobject"], "arch")[-1] == "python-gobject"
    assert PL.orden("instalar", ["libsecret"], "debian")[-1] == "libsecret-tools"
    assert PL.orden("instalar", ["nodejs", "npm"], "suse")[-2:] == ["nodejs-default", "npm-default"]
    assert PL.orden("instalar", ["vlc"], None) is None or PL.familia_actual() in FAMILIAS


def test_cada_paquete_logico_existe_en_todas_las_familias():
    for nombre, tabla in PL.PAQUETES.items():
        assert all(tabla.get(f) for f in FAMILIAS), nombre


# ---------- instalaciones sencillas: lo único que va directo ----------
BUENAS = {
    "arch": ["pacman -S --noconfirm --needed vlc", "pacman -S vlc mpv", "pacman -S --noconfirm extra/vlc"],
    "debian": ["apt-get install -y vlc", "apt install -y vlc mpv", "apt-get install -y --no-install-recommends vlc", "apt-get -y install vlc"],
    "fedora": ["dnf install -y vlc", "dnf5 install vlc mpv", "yum install -y vlc"],
    "suse": ["zypper --non-interactive install vlc", "zypper -n in vlc", "zypper install -y --no-recommends vlc mpv"],
}
MALAS = {
    "arch": ["pacman -U ./x.pkg.tar.zst", "pacman -S --overwrite '*' vlc", "pacman -Sy vlc -S", "pacman -S ./vlc", "pacman -S vlc; rm x"],
    "debian": ["apt-get install -y ./x.deb", "apt install vlc bash-", "apt-get install -y vlc=1.0", "apt install -o APT::Get::AllowUnauthenticated=true vlc",
               "apt-get install --allow-unauthenticated vlc", "apt install -y https://x.example/a.deb", "apt install vlc/experimental", "apt-get remove -y vlc",
               "apt-get install -y vlc | sh", "apt-get install", "dnf install vlc"],
    "fedora": ["dnf install -y @development-tools", "dnf install -y ./x.rpm", "dnf install -y https://x.example/a.rpm", "dnf install --nogpgcheck vlc",
               "dnf remove -y vlc", "dnf install --setopt=gpgcheck=0 vlc", "apt-get install -y vlc"],
    "suse": ["zypper in ./x.rpm", "zypper --non-interactive remove vlc", "zypper in -t pattern devel_basis", "zypper --gpg-auto-import-keys in vlc",
             "zypper install --from repoextra vlc"],
}


@pytest.mark.parametrize("familia", FAMILIAS)
def test_instalaciones_sencillas_se_reconocen(familia):
    for c in BUENAS[familia]:
        nombres = PL.paquetes_a_instalar(c.split(), familia)
        assert nombres, c
        assert all(n in ("vlc", "mpv", "extra/vlc") for n in nombres), (c, nombres)


@pytest.mark.parametrize("familia", FAMILIAS)
def test_lo_raro_no_es_una_instalacion_sencilla(familia):
    for c in MALAS[familia]:
        assert PL.paquetes_a_instalar(c.split(), familia) is None, c


@pytest.mark.parametrize("familia", FAMILIAS)
def test_la_orden_canonica_se_vuelve_a_reconocer(familia):
    canonica = PL.orden_canonica_instalar(["vlc", "mpv"], familia)
    assert canonica.startswith("sudo ")
    assert PL.paquetes_a_instalar(canonica.split()[1:], familia) == ["vlc", "mpv"]


# ---------- interpretar órdenes de cualquier gestor ----------
@pytest.mark.parametrize("base,args,esperado", [
    ("pacman", "-S vlc", ("instalar", ["vlc"])), ("pacman", "-Rns vlc", ("quitar", ["vlc"])), ("pacman", "-Syu", ("actualizar", [])),
    ("pacman", "-Ss vlc", ("consulta", ["vlc"])), ("pacman", "-Qi vlc", ("consulta", ["vlc"])), ("pacman", "-U x.pkg.tar.zst", ("local", ["x.pkg.tar.zst"])),
    ("pacman", "-Fy", ("refrescar", [])), ("yay", "-S extra/vlc", ("instalar", ["vlc"])),
    ("apt-get", "install -y vlc", ("instalar", ["vlc"])), ("apt", "remove vlc", ("quitar", ["vlc"])), ("apt", "purge -y vlc", ("quitar", ["vlc"])),
    ("apt", "install vlc bash-", ("quitar", ["vlc", "bash"])), ("apt", "upgrade -y", ("actualizar", [])), ("apt", "full-upgrade", ("actualizar", [])),
    ("apt", "update", ("refrescar", [])), ("apt", "search vlc", ("consulta", ["vlc"])), ("apt", "install ./x.deb", ("local", ["./x.deb"])),
    ("apt", "install vlc=3.0", ("instalar", ["vlc"])), ("apt", "install vlc/noble", ("local", ["vlc/noble"])), ("dpkg", "-i x.deb", ("local", ["x.deb"])),
    ("dpkg", "-l", ("consulta", [])), ("dpkg", "--purge vlc", ("quitar", ["vlc"])),
    ("dnf", "install -y vlc", ("instalar", ["vlc"])), ("dnf", "remove vlc", ("quitar", ["vlc"])), ("dnf", "upgrade -y", ("actualizar", [])),
    ("dnf", "upgrade vlc", ("instalar", ["vlc"])), ("dnf", "search vlc", ("consulta", ["vlc"])), ("dnf", "install https://x.example/a.rpm", ("local", ["https://x.example/a.rpm"])),
    ("dnf", "makecache", ("refrescar", [])), ("yum", "install -y vlc", ("instalar", ["vlc"])),
    ("zypper", "-n in vlc", ("instalar", ["vlc"])), ("zypper", "remove vlc", ("quitar", ["vlc"])), ("zypper", "dup", ("actualizar", [])),
    ("zypper", "se vlc", ("consulta", ["vlc"])), ("zypper", "refresh", ("refrescar", [])), ("zypper", "in ./x.rpm", ("local", ["./x.rpm"])),
    ("rpm", "-qa", ("consulta", [])), ("rpm", "-qi vlc", ("consulta", ["vlc"])), ("rpm", "-ivh x.rpm", ("local", ["x.rpm"])), ("rpm", "-e vlc", ("quitar", ["vlc"])),
    ("ls", "-l", (None, [])), ("apt", "frobnicate", (None, [])),
])
def test_interpretar(base, args, esperado):
    assert PL.interpretar(base, args.split()) == esperado


def test_consultar_no_pide_confirmacion_en_ninguna_familia():
    for c in ("pacman -Qs vlc", "apt list --installed", "apt-cache search vlc", "dpkg -l", "dpkg-query -W vlc", "dnf search vlc", "dnf list installed",
              "rpm -qa", "zypper search vlc", "apt-file search bin/foo"):
        assert H.clasificar(c)[0] == "lectura", c


@pytest.mark.parametrize("comando,si", [
    ("sudo pacman -Syu --noconfirm", True), ("yay -Syu", True), ("sudo apt-get upgrade -y", True), ("sudo apt full-upgrade", True),
    ("sudo dnf upgrade -y --refresh", True), ("sudo dnf update", True), ("sudo zypper dup", True), ("sudo zypper --non-interactive update", True),
    ("sudo pacman -S vlc", False), ("sudo apt-get install -y vlc", False), ("sudo dnf upgrade vlc", False), ("sudo apt-get update", False),
    ("apt list --upgradable", False), ("sudo zypper refresh", False),
])
def test_actualizacion_completa(comando, si):
    assert PL.es_actualizacion_completa(comando) is si


# ---------- el filtro de comandos en cada familia ----------
@pytest.mark.parametrize("familia", FAMILIAS)
def test_instalar_un_paquete_normal_va_directo(en, familia):
    en(familia)
    c = PL.orden_canonica_instalar(["vlc"], familia)
    assert H.analizar_instalacion(c) == ["vlc"]
    assert H.clasificar(c)[0] == "instalar"


@pytest.mark.parametrize("familia,comando", [
    ("arch", "sudo pacman -S --noconfirm linux-lts"), ("debian", "sudo apt-get install -y linux-image-generic"),
    ("debian", "sudo apt-get install -y grub-efi-amd64"), ("fedora", "sudo dnf install -y kernel-core"), ("fedora", "sudo dnf install -y akmod-nvidia"),
    ("suse", "sudo zypper --non-interactive install kernel-default"), ("suse", "sudo zypper in grub2"), ("debian", "sudo apt-get install -y nvidia-driver-550"),
])
def test_el_kernel_y_el_arranque_piden_confirmacion_en_todas(en, familia, comando):
    en(familia)
    assert H.clasificar(comando)[0] == "critico", comando


@pytest.mark.parametrize("familia,comando", [
    ("debian", "sudo apt-get remove -y linux-image-6.8.0-generic"), ("debian", "sudo apt purge libc6"), ("debian", "sudo apt install vlc libc6-"),
    ("fedora", "sudo dnf remove -y glibc-common"), ("fedora", "sudo dnf remove kernel-core"), ("suse", "sudo zypper remove kernel-default"),
    ("arch", "sudo pacman -Rns linux"),
])
def test_quitar_lo_base_pide_confirmacion(en, familia, comando):
    en(familia)
    assert H.clasificar(comando)[0] == "critico", comando


@pytest.mark.parametrize("familia,comando", [
    ("debian", "sudo dpkg -i /tmp/x.deb"), ("debian", "sudo apt install ./x.deb"), ("debian", "sudo add-apt-repository ppa:evil/ppa"),
    ("debian", "echo 'deb http://x.example/ y main' | sudo tee /etc/apt/sources.list.d/x.list"), ("debian", "sudo apt-key add k.asc"),
    ("fedora", "sudo rpm -ivh x.rpm"), ("fedora", "sudo dnf install https://x.example/a.rpm"), ("fedora", "sudo dnf copr enable usuario/proyecto"),
    ("fedora", "sudo dnf config-manager --add-repo https://x.example/r.repo"), ("suse", "sudo zypper addrepo https://x.example/r r"),
    ("suse", "sudo zypper in ./x.rpm"), ("arch", "sudo pacman -U x.pkg.tar.zst"), ("arch", "paru -S algo-del-aur"), ("debian", "sudo snap install algo"),
])
def test_software_de_fuera_pide_confirmacion(en, familia, comando):
    en(familia)
    assert H.clasificar(comando)[0] == "critico", comando


def test_un_gestor_de_otra_familia_no_se_cuela_como_instalacion_sencilla(en):
    en("debian")
    assert H.analizar_instalacion("sudo pacman -S vlc") is None
    assert H.clasificar("sudo pacman -S vlc")[0] != "instalar"
    en("arch")
    assert H.analizar_instalacion("sudo apt-get install -y vlc") is None


def test_el_ayudante_de_root_se_reconoce_en_todas(en):
    for f in FAMILIAS:
        en(f)
        assert H.analizar_instalacion(f"sudo {H.RAIZ_AYUDANTE} instalar vlc") == ["vlc"]


# ---------- anotar, verificar y deshacer ----------
@pytest.mark.parametrize("familia", FAMILIAS)
def test_intenciones_de_cambio(en, familia):
    en(familia)
    assert ("paquetes_instalar", ["vlc"]) in H._intenciones_de_cambio(PL.orden_canonica_instalar(["vlc"], familia))
    quitar = " ".join(["sudo", *PL.orden("quitar", ["vlc"], familia)])
    assert ("paquetes_quitar", ["vlc"]) in H._intenciones_de_cambio(quitar)
    actualizar = " ".join(["sudo", *PL.ordenes_actualizar(familia)[-1]])
    assert any(i[0] == "sin_deshacer" for i in H._intenciones_de_cambio(actualizar))


SALIDAS = {   # familia -> (instalado, no instalado) como (codigo, salida)
    "arch": ((0, "vlc"), (1, "error: package 'vlc' was not found")),
    "debian": ((0, "ii "), (0, "rc "), (1, "dpkg-query: no packages found matching vlc")),
    "fedora": ((0, "vlc-3.0.x86_64"), (1, "package vlc is not installed")),
    "suse": ((0, "vlc-3.0.x86_64"), (1, "package vlc is not installed")),
}


@pytest.mark.parametrize("familia", FAMILIAS)
def test_comprobar_si_esta_instalado(familia):
    cons = PL.consulta_instalado("vlc", familia)
    assert cons and cons[-1] == "vlc"
    instalado, *no = SALIDAS[familia]
    assert PL.interpreta_instalado(*instalado, familia=familia) is True
    for codigo, salida in no:
        assert PL.interpreta_instalado(codigo, salida, familia) is False
    assert PL.interpreta_instalado(None, "", familia) is None


def test_debian_paquete_quitado_con_configuracion_no_cuenta_como_instalado():
    assert PL.interpreta_instalado(0, "rc ", "debian") is False


@pytest.mark.parametrize("familia", FAMILIAS)
def test_deshacer_una_instalacion_y_un_borrado(en, monkeypatch, familia):
    en(familia)
    lanzadas = []
    monkeypatch.setattr(H, "_como_root", lambda argv, **k: (lanzadas.append(argv), (0, ""))[1])
    est, _ = H._deshacer_payload({"tipo": "paquetes", "nuevos": ["vlc"]})
    assert est == "ok" and lanzadas[-1] == PL.orden("quitar", ["vlc"], familia)
    est, _ = H._deshacer_payload({"tipo": "paquetes_quitados", "paquetes": ["vlc"]})
    assert est == "ok" and lanzadas[-1] == PL.orden("instalar", ["vlc"], familia)
    est, _ = H._deshacer_payload({"tipo": "paquetes", "nuevos": ["--force-all"]})
    assert est == "omitido"


# ---------- buscar qué paquete trae un programa ----------
def test_pares_que_traen():
    arch = "extra/mpv 0.38 [installed]\n    usr/bin/mpv\nextra/vlc 3.0\n    usr/bin/vlc\n    usr/bin/cvlc\n"
    assert PL.pares_que_traen(arch, "arch") == [("mpv", "mpv"), ("vlc", "vlc"), ("vlc", "cvlc")]
    assert PL.pares_que_traen("vlc-bin: /usr/bin/vlc\nvlc-bin: /usr/bin/cvlc\n", "debian") == [("vlc-bin", "vlc"), ("vlc-bin", "cvlc")]
    assert PL.pares_que_traen("lo que sea", "fedora") == []


def test_sin_forma_de_buscar_por_archivo_se_dice_sin_inventar(en, monkeypatch):
    en("fedora")
    monkeypatch.setattr(H, "_ejecutables_parecidos", lambda p: [])
    texto = H._sugerir_paquete("programainexistente")
    assert "pacman" not in texto and "dnf search" in texto


# ---------- snapshots ----------
def test_snapshot_sin_herramienta_lo_explica(monkeypatch):
    monkeypatch.setattr(PL, "detectar_snapshots", lambda **k: None)
    numero, motivo = H.crear_snapshot("prueba")
    assert numero is None and "snapper ni Timeshift" in motivo


def test_snapshot_con_timeshift(monkeypatch):
    monkeypatch.setattr(PL, "detectar_snapshots", lambda **k: "timeshift")
    llamadas = []
    monkeypatch.setattr(H, "_ejecutar_simple", lambda argv, **k: (llamadas.append(argv), (0, "Snapshot '2026-10-15_16-20-00' created successfully"))[1])
    monkeypatch.setattr(H, "_privilegios", lambda: ["sudo", "-n"])
    ident, motivo = H.crear_snapshot("lina: instalar")
    assert ident == "2026-10-15_16-20-00" and motivo == ""
    assert "timeshift" in llamadas[0] and "--create" in llamadas[0]


def test_snapshot_con_snapper(monkeypatch):
    monkeypatch.setattr(PL, "detectar_snapshots", lambda **k: "snapper")
    monkeypatch.setattr(H, "_ejecutar_simple", lambda argv, **k: (0, "42"))
    monkeypatch.setattr(H, "_privilegios", lambda: [])
    assert H.crear_snapshot("x") == (42, "")


# ---------- capacidades detectadas ----------
def test_capacidades_detectadas_sin_suponer():
    presentes = {"/etc/default/limine", "/etc/snapper/configs/root", "/run/systemd/system"}
    programas = {"snapper": "/usr/bin/snapper", "steam": "/usr/bin/steam", "paru": "/usr/bin/paru", "restic": "/usr/bin/restic", "pactl": "/usr/bin/pactl",
                 "pacman": "/usr/bin/pacman"}
    c = PL.capacidades(os_release=OS_RELEASE["cachyos"], entorno={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"},
                       which=programas.get, existe=lambda r: r in presentes)
    assert c["familia"] == "arch" and c["init"] == "systemd" and c["arranque"] == "limine" and c["snapshots"] == "snapper"
    assert c["ayudante_aur"] == "paru" and c["opcionales"]["steam"] is True and c["opcionales"]["heroic"] is False
    assert c["opcionales"]["copias"] == ["restic"]


def test_capacidades_de_un_equipo_sin_nada_especial():
    c = PL.capacidades(os_release=OS_RELEASE["ubuntu"], entorno={}, which=lambda _: None, existe=lambda r: r == "/boot/grub/grub.cfg")
    assert c["familia"] == "debian" and c["snapshots"] is None and c["arranque"] == "grub" and c["ayudante_aur"] is None
    texto = "\n".join(PL.describir(c))
    assert "ninguna herramienta" in texto and "paru" not in texto


def test_audio_init_y_arranque():
    assert PL.detectar_audio(which=lambda p: p == "pactl", ejecutar=lambda a: (0, "Server Name: PulseAudio (on PipeWire 1.0.5)")) == "pipewire"
    assert PL.detectar_audio(which=lambda p: p == "pactl", ejecutar=lambda a: (0, "Server Name: pulseaudio")) == "pulseaudio"
    assert PL.detectar_audio(which=lambda p: False, ejecutar=lambda a: (1, "")) is None
    assert PL.detectar_init(existe=lambda r: r == "/run/systemd/system") == "systemd"
    assert PL.detectar_init(existe=lambda r: False, leer=lambda r: "runit\n") == "runit"
    assert PL.detectar_arranque(existe=lambda r: r == "/boot/loader/loader.conf") == "systemd-boot"
    assert PL.detectar_arranque(existe=lambda r: r == "/boot/grub2/grub.cfg") == "grub"
    assert PL.detectar_arranque(existe=lambda r: False) is None


def test_gpu_por_vendedor():
    assert PL.detectar_gpu(listar=lambda: ["card0", "card1"], leer=lambda t: "0x10de" if t == "card0" else "0x8086") == ["nvidia", "intel"]


# ---------- textos para la IA ----------
@pytest.mark.parametrize("familia,ajeno", [("debian", "pacman"), ("fedora", "pacman"), ("suse", "pacman"), ("arch", "apt-get")])
def test_las_instrucciones_no_hablan_de_otra_distribucion(en, familia, ajeno):
    en(familia)
    texto = G.sistema("INSTRUCCIONES", "datos", grupos=())
    assert ajeno not in texto and "@@" not in texto
    assert PL.FAMILIAS[familia]["texto_instalar"] in texto


def test_las_instrucciones_en_una_distro_desconocida_son_genericas(monkeypatch):
    monkeypatch.setattr(PL, "familia_actual", lambda entorno=None: None)
    texto = G.sistema("I", "d")
    assert "@@" not in texto and "pacman" not in texto


def test_politica_de_fabrica_incrustada_coincide_con_politica_txt():
    assert PO.TEXTO_DE_FABRICA == (RUT.DEFECTOS / "politica.txt").read_text(encoding="utf-8")
