"""CLI: Google Sheets o JSON -> consulta secuencial -> progreso y Excel."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from alcampo.core import (
    ConfigError, FINAL_STATES, TECHNICAL_STATES, atomic_json, fingerprint,
    load_config, now, read_checkpoint, result,
)
from alcampo.reports import export_excel, send_excel, telegram_config
from alcampo.sources import read_accounts

ROOT = Path(__file__).resolve().parent


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Debe ser un entero positivo")
    return number


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--input-file", type=Path, help="JSON local; evita necesitar Google")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=positive)
    parser.add_argument("--max-seconds", type=positive)
    parser.add_argument("--headed", action="store_true", help="Mostrar el navegador")
    parser.add_argument("--resume", action="store_true", help="Reutilizar resultados terminales de progreso.json, hasta 24 horas")
    parser.add_argument("--check-config", action="store_true", help="Leer y validar la fuente sin visitar Alcampo ni enviar mensajes")
    parser.add_argument("--telegram", action="store_true", help="Enviar el Excel al destino configurado")
    return parser.parse_args()


def run(args):
    config = load_config(args.config)
    if args.telegram:
        telegram_config(config)  # Validar antes del trabajo; no hace peticiones.
    accounts = read_accounts(config, args.input_file)
    if args.limit:
        accounts = accounts[:args.limit]
    if not accounts:
        raise ConfigError("La fuente no contiene cuentas; no se ha iniciado ninguna consulta")
    print(f"Configuración y fuente válidas: {len(accounts)} cuentas únicas.", flush=True)
    if args.check_config:
        return 0
    try:
        from playwright.sync_api import sync_playwright
        import openpyxl  # Comprobar disponibilidad antes de consultar cuentas.
        from alcampo.browser import process_account
    except ImportError:
        raise ConfigError("Faltan dependencias. Ejecuta python -m pip install -r requirements.txt") from None

    output = args.output_dir or ROOT / config.get("output_dir", "resultados")
    progress_path = output / "progreso.json"
    report_path = output / "resultados.xlsx"
    key = fingerprint(accounts, config)
    state = {"version": 1, "fingerprint": key, "started_at": now(), "resultados": [], "complete": False}
    if args.resume:
        state = read_checkpoint(progress_path, key, {a.email for a in accounts})
    done = {row["cuenta"]: row for row in state["resultados"] if row["estado"] in FINAL_STATES}
    state["complete"] = False
    start = time.monotonic()
    budget = args.max_seconds or config["max_seconds"]
    failures = 0
    stop_reason = ""

    def save():
        state["resultados"] = list(done.values())
        state["updated_at"] = now()
        atomic_json(progress_path, state)

    save()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            try:
                for account in accounts:
                    if account.email in done:
                        continue
                    remaining = budget - (time.monotonic() - start)
                    if remaining <= 1:
                        stop_reason = "Tiempo máximo de ejecución alcanzado"
                        break
                    row = process_account(browser, account, config, remaining)
                    done[account.email] = row
                    save()
                    print(f"Procesadas {len(done)}/{len(accounts)}; último estado: {row['estado']}", flush=True)
                    failures = failures + 1 if row["estado"] in TECHNICAL_STATES else 0
                    if row["estado"] in {"LIMITE_SERVICIO", "VERIFICACION_MANUAL"}:
                        stop_reason = "El servicio requiere una pausa o verificación manual"
                        break
                    if failures >= config["max_consecutive_technical_errors"]:
                        stop_reason = "Se alcanzó el límite de errores técnicos consecutivos"
                        break
                    if len(done) < len(accounts):
                        time.sleep(min(config["pause_seconds"], max(0, budget - (time.monotonic() - start))))
            finally:
                browser.close()
    except KeyboardInterrupt:
        stop_reason = "Interrumpido por el usuario"
    except Exception:
        stop_reason = "Fallo de ejecución o navegador; revisa instalación y conectividad"

    state["complete"] = len(done) == len(accounts)
    state["stop_reason"] = stop_reason
    state["duration_this_invocation_seconds"] = round(time.monotonic() - start, 2)
    save()
    rows = [done.get(a.email) or result(a.email, "PENDIENTE", detail=stop_reason) for a in accounts]
    good = sum(r["estado"] == "SALDO_OK" for r in rows)
    technical = sum(r["estado"] in TECHNICAL_STATES for r in rows)
    metadata = {
        "Inicio UTC": state["started_at"], "Final UTC": now(),
        "Cuentas previstas": len(accounts), "Cuentas procesadas": len(done),
        "Saldos leídos": good, "Errores técnicos": technical,
        "Pendientes": len(accounts) - len(done), "Ejecución completa": state["complete"],
        "Duración esta ejecución (s)": state["duration_this_invocation_seconds"],
        "Motivo de parada": stop_reason or "Lista procesada",
        "Saldo total EUR": sum(r["saldo_centimos"] or 0 for r in rows if r["estado"] == "SALDO_OK") / 100,
    }
    export_excel(rows, report_path, metadata)
    print(f"Informe guardado: {report_path}")
    print(f"Saldos leídos: {good}; errores técnicos: {technical}; pendientes: {len(accounts)-len(done)}.")
    if args.telegram:
        caption = f"Alcampo: {len(done)}/{len(accounts)} procesadas; {good} saldos leídos. " + ("Informe completo." if state["complete"] else "INFORME PARCIAL.")
        send_excel(report_path, config, caption)
        print("Telegram confirmó el envío.")
    return 3 if stop_reason or not state["complete"] or technical else 0


def main():
    os.umask(0o077)
    try:
        return run(arguments())
    except ConfigError as error:
        print(f"Configuración: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("Fallo inesperado. Revisa permisos y dependencias; se conserva el progreso disponible.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
