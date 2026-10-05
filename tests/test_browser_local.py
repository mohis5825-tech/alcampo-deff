"""Pruebas reales de Chromium contra una web ficticia en loopback, sin servicios externos.

Activar: ALCAMPO_BROWSER_TESTS=1 python -m unittest discover -s tests -v
"""
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from alcampo.browser import process_account
from alcampo.core import Account


FORM = '<form action="/login" method="post"><input id="uname1" name="email"><input id="pwd1" type="password" name="password"><button>Entrar</button></form>'


class FakeSite(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def html(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(("<!doctype html><html><body>" + text + "</body></html>").encode())

    def do_GET(self):
        if self.path == "/login":
            # Una sesión anterior no debe filtrarse a la siguiente cuenta.
            if "session=ok" in self.headers.get("Cookie", ""):
                self.html("Sesión anterior conservada por error", 500)
            else:
                self.html(FORM)
        elif self.path == "/rate":
            self.html("Límite temporal", 429)
        elif self.path == "/challenge":
            self.html("Verifica que eres humano")
        elif self.path == "/home":
            self.html("Cuenta de prueba")
        elif self.path == "/settings/loyalty":
            if "session=ok" in self.headers.get("Cookie", ""):
                self.html("Tu Saldo es 1.234,56 €")
            else:
                self.html(FORM)
        else:
            self.html("No encontrado", 404)

    def do_POST(self):
        data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        if data.get("password") == ["ficticio-correcto"]:
            self.send_response(303)
            self.send_header("Location", "/home")
            self.send_header("Set-Cookie", "session=ok; Path=/; HttpOnly")
            self.end_headers()
        else:
            self.html(FORM + "<p>Usuario o contraseña incorrectos</p>")


@unittest.skipUnless(os.environ.get("ALCAMPO_BROWSER_TESTS") == "1", "Prueba Chromium local opcional")
class BrowserLocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

    def config(self):
        # Se invoca el adaptador directamente; la configuración de producción exige HTTPS.
        return {"timeout_ms": 1500, "login_url": self.base + "/login",
                "balance_url": self.base + "/settings/loyalty", "email_selector": "#uname1",
                "password_selector": "#pwd1", "balance_selector": "body", "submit_selector": ""}

    def test_balance_and_session_isolation(self):
        for email in ("uno@example.invalid", "dos@example.invalid"):
            row = process_account(self.browser, Account(email, "ficticio-correcto"), self.config())
            self.assertEqual(row["estado"], "SALDO_OK", row)
            self.assertEqual(row["saldo_centimos"], 123456)

    def test_auth_rejection(self):
        row = process_account(self.browser, Account("uno@example.invalid", "ficticio-incorrecto"), self.config())
        self.assertEqual(row["estado"], "AUTENTICACION_RECHAZADA")

    def test_rate_limit(self):
        config = self.config()
        config["login_url"] = self.base + "/rate"
        row = process_account(self.browser, Account("uno@example.invalid", "ficticio"), config)
        self.assertEqual(row["estado"], "LIMITE_SERVICIO")

    def test_human_verification(self):
        config = self.config()
        config["login_url"] = self.base + "/challenge"
        row = process_account(self.browser, Account("uno@example.invalid", "ficticio"), config)
        self.assertEqual(row["estado"], "VERIFICACION_MANUAL")

    def test_missing_form_is_not_invalid_password(self):
        config = self.config()
        config["login_url"] = self.base + "/home"
        config["timeout_ms"] = 100
        row = process_account(self.browser, Account("uno@example.invalid", "ficticio"), config)
        self.assertEqual(row["estado"], "TIMEOUT")
