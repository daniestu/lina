# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S11: el nombre de una web se resuelve una sola vez por salto y se conecta a esa IP comprobada (DNS rebinding).

Antes, `_comprobar_destino` resolvía el nombre para revisar que no fuera interno y `requests` lo resolvía otra vez al descargar: un dominio que cambiara de IP
entre las dos (primero una pública, después 127.0.0.1 o la red de metadatos) saltaba la revisión. Sin red de verdad: un servidor en 127.0.0.1 hace de web
«permitida» (PERMITIR_PRIVADAS) y el resolvedor falso cambia de respuesta tras la primera vez.
"""
import http.server
import socket
import threading

import pytest

from lina.modulos import web as W

NOMBRE = "rebinding.test"
CUERPO = b"<html><head><title>Buena</title></head><body><p>" + b"Texto de la web comprobada, con contenido suficiente. " * 8 + b"</p></body></html>"


class _Web(http.server.BaseHTTPRequestHandler):
    vistos = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _Web.vistos.append(self.headers.get("Host"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(CUERPO)))
        self.end_headers()
        self.wfile.write(CUERPO)


@pytest.fixture
def servidor(monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Web)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Web.vistos = []
    monkeypatch.setattr(W, "PUERTOS", W.PUERTOS | {srv.server_address[1]})
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def resolvedor(monkeypatch):
    """La primera vez, NOMBRE es 127.0.0.1 (el servidor de la prueba, permitido aquí); después, una dirección a la que no se puede llegar."""
    real, veces = socket.getaddrinfo, []

    def falso(host, *a, **k):
        if host == NOMBRE:
            veces.append(host)
            ip = "127.0.0.1" if len(veces) == 1 else "203.0.113.9"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, a[0] if a and isinstance(a[0], int) else 0))]
        return real(host, *a, **k)
    monkeypatch.setattr(socket, "getaddrinfo", falso)
    return veces


def test_se_conecta_a_la_ip_comprobada_aunque_el_dns_cambie_despues(servidor, resolvedor, monkeypatch):
    monkeypatch.setattr(W, "PERMITIR_PRIVADAS", True)
    datos, tipo, url, _ = W.descargar(f"http://{NOMBRE}:{servidor}/pagina")
    assert b"web comprobada" in datos and tipo == "text/html" and url == f"http://{NOMBRE}:{servidor}/pagina"
    assert resolvedor == [NOMBRE]                                  # una sola resolución: la que se revisó
    assert _Web.vistos == [f"{NOMBRE}:{servidor}"]                 # y la web recibe su nombre en Host, no la IP


def test_una_direccion_interna_en_la_unica_resolucion_ni_se_pide(monkeypatch):
    monkeypatch.setattr(W, "PERMITIR_PRIVADAS", False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))])
    monkeypatch.setattr(W, "_pedir", lambda *a, **k: pytest.fail("no debía pedirse"))
    with pytest.raises(W.ErrorWeb, match="red interna"):
        W.descargar(f"https://{NOMBRE}/")


def test_si_alguna_de_las_direcciones_es_interna_no_se_lee(monkeypatch):
    monkeypatch.setattr(W, "PERMITIR_PRIVADAS", False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                                                                     (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))])
    with pytest.raises(W.ErrorWeb, match="red interna"):
        W.descargar(f"https://{NOMBRE}/")


def test_devuelve_la_ip_comprobada():
    import unittest.mock as M
    with M.patch.object(socket, "getaddrinfo", return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1::1", 0, 0, 0))]):
        assert W._comprobar_destino("https://ejemplo.test/") == "2606:2800:220:1::1"


@pytest.mark.parametrize("ip", ["93.184.216.34", "2606:2800:220:1::1"])
def test_en_https_conecta_a_la_ip_y_comprueba_el_certificado_con_el_nombre(ip):
    adaptador = W._AdaptadorFijado(ip, "ejemplo.test")
    peticion = W.requests.Request("GET", "https://ejemplo.test/ruta").prepare()
    conexion = adaptador.get_connection_with_tls_context(peticion, True)
    assert conexion.host.strip("[]") == ip and conexion.port == 443
    assert conexion.conn_kw.get("server_hostname") == "ejemplo.test" and conexion.assert_hostname == "ejemplo.test"
    assert conexion.cert_reqs == "CERT_REQUIRED"
    adaptador.close()


def test_con_proxy_se_queda_como_antes():
    """Con un proxy, quien resuelve es el proxy: no se fija la IP (límite documentado en el plan)."""
    adaptador = W._AdaptadorFijado("93.184.216.34", "ejemplo.test")
    peticion = W.requests.Request("GET", "http://ejemplo.test/").prepare()
    conexion = adaptador.get_connection_with_tls_context(peticion, True, proxies={"http": "http://proxy.test:3128"})
    assert conexion.host == "proxy.test"
    adaptador.close()


def test_la_redireccion_se_revisa_y_resuelve_salto_a_salto(monkeypatch):
    monkeypatch.setattr(W, "PERMITIR_PRIVADAS", False)
    resueltos, pedidos = [], []

    def resolver(host, *a, **k):
        resueltos.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34" if host == NOMBRE else "127.0.0.1", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", resolver)

    def pedir(url, ip):
        pedidos.append((url, ip))
        return type("Redireccion", (), {"status_code": 302, "headers": {"Location": "http://otra.test/"}, "close": lambda s: None})()
    monkeypatch.setattr(W, "_pedir", pedir)
    with pytest.raises(W.ErrorWeb, match="red interna"):
        W.descargar(f"https://{NOMBRE}/")
    assert resueltos == [NOMBRE, "otra.test"] and pedidos == [(f"https://{NOMBRE}/", "93.184.216.34")]
