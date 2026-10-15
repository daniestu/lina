import subprocess

import pytest

from lina.nucleo import herramientas as H
from lina.nucleo import privilegios as P
from lina.nucleo import raiz as R


def resultado(codigo):
    return subprocess.CompletedProcess([], codigo, b"", b"")


def sudo_falso(total=False, instalar=False):
    """Un `sudo` falso: `sudo -n true` vale si total; `sudo -n -l ayudante…` vale si instalar."""
    def f(orden, **kw):
        if orden[:3] == ["sudo", "-n", "true"]:
            return resultado(0 if total else 1)
        if orden[:3] == ["sudo", "-n", "-l"]:
            return resultado(0 if (instalar or total) else 1)
        return resultado(1)
    return f


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    P.olvidar()
    monkeypatch.setattr(P, "COMPROBAR", True)
    monkeypatch.setattr(P.os, "geteuid", lambda: 1000)
    yield
    P.olvidar()


def test_niveles():
    assert P.nivel(sudo_falso(total=True), usar_cache=False) == "total"
    assert P.nivel(sudo_falso(instalar=True), usar_cache=False) == "instalar"
    assert P.nivel(sudo_falso(), usar_cache=False) == "ninguno"
    assert P.nivel(lambda *a, **k: (_ for _ in ()).throw(OSError("sin sudo")), usar_cache=False) == "ninguno"


def test_el_nivel_se_recuerda_un_minuto():
    llamadas = []
    def f(orden, **kw):
        llamadas.append(orden)
        return resultado(0)
    P.nivel(f, ahora=lambda: 100.0)
    P.nivel(f, ahora=lambda: 130.0)
    assert len(llamadas) == 1
    P.nivel(f, ahora=lambda: 200.0)
    assert len(llamadas) == 2


def test_adaptar_segun_el_nivel():
    pac = "sudo -n pacman -S --noconfirm --needed ydotool"
    assert P.adaptar(pac, ["ydotool"], "total") == pac
    assert P.adaptar(pac, ["ydotool"], "instalar") == f"sudo -n {R.AYUDANTE} instalar ydotool"
    assert P.adaptar(pac, ["ydotool"], "ninguno", existe=lambda x: "/usr/bin/pkexec") == pac.replace("sudo -n", "pkexec", 1)
    assert P.adaptar("sudo -n systemctl restart sshd", None, "ninguno", existe=lambda x: "/usr/bin/pkexec") == "pkexec systemctl restart sshd"


def test_adaptar_no_toca_lo_complejo_ni_lo_que_no_es_sudo():
    complejo = "sudo -n sh -c 'rm -rf /x; id'"
    assert P.adaptar(complejo, None, "ninguno", existe=lambda x: "/usr/bin/pkexec") == complejo
    assert P.adaptar("sudo -n ls $(id)", None, "ninguno", existe=lambda x: "/usr/bin/pkexec") == "sudo -n ls $(id)"
    assert P.adaptar("ls /home", None, "ninguno") == "ls /home"
    assert P.adaptar("sudo -n true", None, "ninguno", existe=lambda x: None) == "sudo -n true"          # sin pkexec: se deja y fallará con su aviso


def test_sin_activar_no_cambia_nada(monkeypatch):
    monkeypatch.setattr(P, "COMPROBAR", False)
    assert P.adaptar("sudo -n true", None, "ninguno", existe=lambda x: "/usr/bin/pkexec") == "sudo -n true"
    assert P.pide_contrasena("sudo true", None, "ninguno") is False


def test_cuando_se_confirma_antes():
    assert P.pide_contrasena("sudo systemctl restart sshd", None, "ninguno") is True
    assert P.pide_contrasena("sudo systemctl restart sshd", None, "instalar") is True          # el ayudante solo instala
    assert P.pide_contrasena("sudo systemctl restart sshd", None, "total") is False
    assert P.pide_contrasena("sudo pacman -S ydotool", ["ydotool"], "instalar") is False
    assert P.pide_contrasena("sudo pacman -S ydotool", ["ydotool"], "ninguno") is True
    assert P.pide_contrasena("ls /home", None, "ninguno") is False


def test_clasificar_integra_el_nivel(monkeypatch):
    monkeypatch.setattr(P, "nivel", lambda *a, **k: "ninguno")
    clase, motivo = H.clasificar("sudo systemctl restart bluetooth")
    assert clase == "critico" and "contraseña" in motivo
    monkeypatch.setattr(P, "nivel", lambda *a, **k: "instalar")
    assert H.clasificar("sudo pacman -S --noconfirm --needed ydotool")[0] == "instalar"
    assert H.clasificar(f"sudo -n {R.AYUDANTE} instalar ydotool")[0] == "instalar"
    monkeypatch.setattr(P, "nivel", lambda *a, **k: "total")
    assert H.clasificar("sudo pacman -S --noconfirm --needed ydotool")[0] == "instalar"


def test_instalar_por_el_ayudante_sigue_pasando_por_la_politica():
    # un paquete de una sección crítica de politica.txt (p. ej. servidores SSH) pide confirmación también por el ayudante
    assert H.analizar_instalacion(f"sudo -n {R.AYUDANTE} instalar openssh") == ["openssh"]
    assert H.clasificar(f"sudo -n {R.AYUDANTE} instalar openssh")[0] in ("critico", "instalar")


@pytest.mark.parametrize("orden", [
    "lina privilegios instalar", "lina privilegios total", "lina privilegios quitar", "yes | lina privilegios total", "cd ~ && lina privilegios instalar",
    "python -m lina privilegios total", f"sudo rm {R.AYUDANTE}", f"sudo sed -i s/x/y/ {R.AYUDANTE}", "sudo tee /etc/sudoers.d/lina-total",
    f"sudo -n {R.AYUDANTE} instalar x; sudo -n {R.AYUDANTE} instalar -Syu", f"{R.AYUDANTE} instalar x && id", "cat /usr/lib/lina/lina-instalar",
    "sudo cp x /usr/share/polkit-1/actions/org.lina.instalar.policy", "sudoedit /etc/sudoers.d/lina-instalar", "visudo -f /etc/sudoers.d/x"])
def test_la_ia_no_puede_tocar_los_privilegios(orden):
    assert H.clasificar(orden)[0] == "bloqueado", orden


@pytest.mark.parametrize("orden", ["lina privilegios", "lina privilegios estado", "pkexec systemctl restart sshd"])
def test_estado_se_puede_mirar(orden):
    assert H.clasificar(orden)[0] != "bloqueado"


def test_pkexec_se_trata_como_sudo():
    assert H._con_sudo("pkexec rm -rf /home/x")
    assert H.clasificar("pkexec rm -rf /home/x/tmp")[0] == "critico"


# ------------------------------------------------------------------ lina privilegios
class Teclas:
    def __init__(self, *respuestas):
        self.r, self.preguntas = list(respuestas), []

    def __call__(self, texto):
        self.preguntas.append(texto)
        return self.r.pop(0)


def lanzador(codigo=0, texto=b"ok"):
    llamadas = []
    def f(orden, **kw):
        llamadas.append((orden, kw))
        return subprocess.CompletedProcess(orden, codigo, texto, b"")
    f.llamadas = llamadas
    return f


def cli(argv, teclas, ejecutar, terminal=True, monkeypatch=None):
    salida = []
    cod = P.principal(argv, entrada=teclas, salida=salida.append, ejecutar=ejecutar, es_terminal=terminal, existe=lambda x: "/usr/bin/" + x)
    return cod, "\n".join(salida)


def test_instalar_enseña_todo_y_solo_actua_si_aceptas(monkeypatch):
    monkeypatch.setenv("USER", "dani")
    f = lanzador()
    cod, texto = cli(["instalar"], Teclas("no"), f)
    assert cod == 1 and f.llamadas == [] and "No se ha cambiado nada" in texto
    assert R.AYUDANTE in texto and R.sudoers_instalar("dani").splitlines()[-1] in texto and "sha256" in texto and "polkit" in texto
    f = lanzador()
    cod, texto = cli(["instalar"], Teclas("sí"), f)
    orden, kw = f.llamadas[0]
    assert cod == 0 and orden[:2] == ["sudo", R.PYTHON] and "-I" in orden and "-c" in orden
    import json
    carga = json.loads(kw["input"])
    assert carga["accion"] == "instalar" and carga["usuario"] == "dani" and carga["sha256"] == P.hash_ayudante()
    assert "def main" in orden[-1] and orden[-1].rstrip().endswith("sys.exit(main())")


def test_sin_terminal_no_hay_consentimiento(monkeypatch):
    monkeypatch.setenv("USER", "dani")
    f = lanzador()
    cod, texto = cli(["instalar"], Teclas("sí"), f, terminal=False)
    assert cod == 2 and f.llamadas == [] and "terminal" in texto


def test_total_exige_la_frase_exacta(monkeypatch):
    monkeypatch.setenv("USER", "dani")
    for mal in ("sí", "dar acceso total", "DAR ACCESO TOTAL ", "", "TOTAL"):
        f = lanzador()
        cod, texto = cli(["total"], Teclas(mal), f)
        if mal == "DAR ACCESO TOTAL ":                       # el espacio final se ignora
            assert cod == 0
            continue
        assert cod == 1 and f.llamadas == [], mal
    f = lanzador()
    cod, texto = cli(["total"], Teclas(P.FRASE_TOTAL), f)
    assert cod == 0 and "AVISO" in texto and "NOPASSWD: ALL" in texto


def test_quitar_pide_confirmar_y_borra(monkeypatch):
    monkeypatch.setenv("USER", "dani")
    f = lanzador()
    cod, texto = cli(["quitar"], Teclas("s"), f)
    import json
    assert cod == 0 and json.loads(f.llamadas[0][1]["input"])["accion"] == "quitar"


def test_usuario_raro_no_llega_al_instalador(monkeypatch):
    monkeypatch.setenv("USER", "dani; id")
    f = lanzador()
    cod, texto = cli(["instalar"], Teclas("sí"), f)
    assert cod == 2 and f.llamadas == []


def test_el_estado_solo_mira_y_nunca_instala(monkeypatch):
    monkeypatch.setenv("USER", "dani")
    f = lanzador(1)
    cod, texto = cli(["estado"], Teclas(), f)
    assert cod == 0 and "Sin permisos" in texto and f.llamadas and all(l[0][:2] == ["sudo", "-n"] for l in f.llamadas)


def test_acciones_desconocidas():
    assert cli(["borrar-todo"], Teclas(), lanzador())[0] == 2
