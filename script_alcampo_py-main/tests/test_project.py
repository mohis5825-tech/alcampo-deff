import base64
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import script
from alcampo.browser import http_issue, page_issue
from alcampo.core import (Account, ConfigError, accounts_from_rows, atomic_json,
                         balance_from_text, fingerprint, load_config,
                         money_cents, now, read_checkpoint, result, sheet_key)
from alcampo.reports import export_excel, send_excel
from alcampo.sources import read_accounts


class CoreTests(unittest.TestCase):
    def test_money(self):
        for source, expected in [("1.234,56 €", 123456), ("0,00", 0),
                                 ("-5,00", -500), ("12.34", 1234),
                                 ("1\u202f234,56", 123456), ("1234", 123400)]:
            with self.subTest(source=source):
                self.assertEqual(money_cents(source), expected)

    def test_reject_partial_or_ambiguous_money(self):
        for source in ("", "NaN", "$1,234.56", "1,234.56", "1,234", "12,3456", "Error 123", "1.23.456"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                money_cents(source)

    def test_balance_requires_club_label(self):
        self.assertIsNone(balance_from_text("Cesta 99,99 €"))
        self.assertEqual(balance_from_text("Tu Saldo es 1.234,56 €"), 123456)
        with self.assertRaises(ValueError):
            balance_from_text("Tu Saldo es 1,00 € Tu Saldo es 2,00 €")

    def test_accounts_preserve_password_and_deduplicate(self):
        rows = [{"Correo electrónico": " prueba@example.invalid ", "Contraseña": " 001abc "},
                {"email": "prueba@example.invalid", "password": " 001abc "}]
        accounts = accounts_from_rows(rows)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].password, " 001abc ")
        self.assertNotIn("001abc", repr(accounts[0]))

    def test_invalid_rows(self):
        for rows in ([{"email": "a@example.invalid", "password": 123}],
                     [{"email": "invalid", "password": "x"}],
                     [{"email": "a@example.invalid", "password": "x"},
                      {"email": "a@example.invalid", "password": "y"}]):
            with self.assertRaises(ConfigError):
                accounts_from_rows(rows)

    def test_sheet_id(self):
        key = "a" * 30
        self.assertEqual(sheet_key(key + "/edit?usp=sharing"), key)
        self.assertEqual(sheet_key(f"https://docs.google.com/spreadsheets/d/{key}/edit"), key)

    def test_http_and_auth_states(self):
        self.assertEqual(http_issue(SimpleNamespace(status=429)), "LIMITE_SERVICIO")
        self.assertEqual(http_issue(SimpleNamespace(status=503)), "ERROR_SERVIDOR")
        self.assertIsNone(page_issue("Si necesitas ayuda, llama a nuestro Call Center"))
        self.assertEqual(page_issue("Usuario o contraseña incorrectos"), "AUTENTICACION_RECHAZADA")

    def test_checkpoint_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progreso.json"
            data = {"version": 1, "fingerprint": "test", "started_at": now(),
                    "resultados": [result("a@example.invalid", "SALDO_OK", 123)]}
            atomic_json(path, data)
            self.assertEqual(read_checkpoint(path, "test", {"a@example.invalid"}), data)
            with self.assertRaises(ConfigError):
                read_checkpoint(path, "otra", {"a@example.invalid"})

    def test_config_rejects_insecure_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            config = json.loads((script.ROOT / "config.json").read_text())
            config["login_url"] = "http://example.invalid/login"
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ConfigError):
                load_config(path)


class SourceTests(unittest.TestCase):
    def test_selects_worksheet_and_preserves_text(self):
        client, sheet = MagicMock(), MagicMock()
        client.open_by_key.return_value.worksheet.return_value = sheet
        sheet.get_all_records.return_value = [{"Correo electrónico": "a@example.invalid", "Contraseña": "00123"}]
        gspread = MagicMock()
        gspread.service_account_from_dict.return_value = client
        encoded = base64.b64encode(b'{}').decode()
        with patch.dict(os.environ, {"GOOGLE_CREDS_B64": encoded}), patch.dict("sys.modules", {"gspread": gspread}):
            rows = read_accounts({"sheet_id": "a" * 30, "worksheet": "Mis cuentas"})
        self.assertEqual(rows[0].password, "00123")
        client.open_by_key.return_value.worksheet.assert_called_once_with("Mis cuentas")
        sheet.get_all_records.assert_called_once_with(numericise_ignore=["all"])

    def test_local_json_without_google(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            path.write_text('[{"email":"a@example.invalid","password":"ficticio"}]')
            self.assertEqual(len(read_accounts({}, path)), 1)


class ReportTests(unittest.TestCase):
    def test_excel_numeric_sorted_and_formula_safe(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "personalizado.xlsx"
            rows = [result("=formula@example.invalid", "SALDO_OK", 123456),
                    result("b@example.invalid", "SALDO_OK", 0),
                    result("c@example.invalid", "TIMEOUT")]
            export_excel(rows, path, {"Procesadas": 3})
            book = load_workbook(path)
            self.assertEqual(book["Resultados"]["C2"].value, 1234.56)
            self.assertEqual(book["Resultados"]["A2"].data_type, "s")
            self.assertEqual(book["Resultados"]["C3"].value, 0)
            self.assertIsNone(book["Resultados"]["C4"].value)
            book.close()

    def test_telegram_error_does_not_leak_token(self):
        token = "12345:" + "A" * 25
        fake_requests = MagicMock()
        fake_requests.post.return_value.status_code = 200
        fake_requests.post.return_value.json.return_value = {"ok": False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.xlsx"
            path.write_bytes(b'fixture')
            with patch.dict(os.environ, {"BOT_TOKEN": token, "CHAT_ID": "-100"}), patch.dict("sys.modules", {"requests": fake_requests}):
                with self.assertRaises(ConfigError) as raised:
                    send_excel(path, {}, "Prueba")
            self.assertNotIn(token, str(raised.exception))
            call = fake_requests.post.call_args
            self.assertEqual(call.kwargs["files"]["document"][0], "custom.xlsx")
            self.assertEqual(call.kwargs["timeout"], (10, 60))


class RunnerTests(unittest.TestCase):
    def test_partial_progress_and_resume(self):
        accounts = [Account("a@example.invalid", "secreto-ficticio"), Account("b@example.invalid", "otro-ficticio")]
        playwright_module = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            args = SimpleNamespace(config=script.ROOT / "config.json", telegram=False,
                                   input_file=None, limit=None, check_config=False,
                                   output_dir=output, resume=False, max_seconds=60, headed=False)
            first = result(accounts[0].email, "VERIFICACION_MANUAL")
            with patch("script.read_accounts", return_value=accounts), patch.dict("sys.modules", {"playwright.sync_api": playwright_module}), patch("alcampo.browser.process_account", return_value=first), redirect_stdout(StringIO()):
                self.assertEqual(script.run(args), 3)
            checkpoint = json.loads((output / "progreso.json").read_text())
            self.assertFalse(checkpoint["complete"])
            self.assertEqual(len(checkpoint["resultados"]), 1)
            self.assertNotIn("secreto-ficticio", (output / "progreso.json").read_text())
            args.resume = True
            with patch("script.read_accounts", return_value=accounts), patch.dict("sys.modules", {"playwright.sync_api": playwright_module}), patch("alcampo.browser.process_account", side_effect=lambda browser, account, *rest: result(account.email, "SALDO_OK", 123)), patch("script.time.sleep"), redirect_stdout(StringIO()):
                self.assertEqual(script.run(args), 0)
            self.assertTrue(json.loads((output / "progreso.json").read_text())["complete"])

    def test_dry_run_never_launches_browser(self):
        args = SimpleNamespace(config=script.ROOT / "config.json", telegram=False,
                               input_file=None, limit=None, check_config=True)
        with patch("script.read_accounts", return_value=[Account("a@example.invalid", "test")]), patch("alcampo.browser.process_account") as process, redirect_stdout(StringIO()):
            self.assertEqual(script.run(args), 0)
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
