from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Account:
    email: str
    password: str = field(repr=False)


STATES = {
    "SALDO_OK", "AUTENTICACION_RECHAZADA", "CUENTA_BLOQUEADA",
    "VERIFICACION_MANUAL", "LIMITE_SERVICIO", "TIMEOUT", "ERROR_RED",
    "ERROR_SERVIDOR", "CAMBIO_WEB", "ERROR_TECNICO", "PENDIENTE",
}
FINAL_STATES = {"SALDO_OK", "AUTENTICACION_RECHAZADA", "CUENTA_BLOQUEADA"}
TECHNICAL_STATES = STATES - FINAL_STATES - {"PENDIENTE"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def result(email, state, cents=None, detail=""):
    if state not in STATES or (state == "SALDO_OK" and type(cents) is not int):
        raise ValueError("Resultado no válido")
    return {"cuenta": email, "estado": state, "saldo_centimos": cents,
            "moneda": "EUR", "comprobado": now(), "detalle": detail}


def money_cents(text: str) -> int:
    """Euros españoles: acepta miles, coma decimal y punto decimal sin miles.

    Rechaza mezclas ambiguas, cifras parciales y más de dos decimales.
    """
    value = text.strip().replace("€", "").strip()
    value = value.replace("\u00a0", " ").replace("\u202f", " ")
    if re.fullmatch(r"[+-]?\d{1,3}(?:[. ]\d{3})+(?:,\d{1,2})?", value):
        value = value.replace(".", "").replace(" ", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d+(?:,\d{1,2})?", value):
        value = value.replace(",", ".")
    elif not re.fullmatch(r"[+-]?\d+\.\d{1,2}", value):
        raise ValueError("Importe ausente, ambiguo o con formato no admitido")
    return int(Decimal(value) * 100)


def balance_from_text(text: str) -> int | None:
    candidates = re.findall(r"Tu\s+Saldo\s+es\s*([+\-\d.,\s\u00a0\u202f]+)\s*€", text, re.I)
    if not candidates:
        return None
    values = {money_cents(candidate) for candidate in candidates}
    if len(values) != 1:
        raise ValueError("La página muestra varios saldos diferentes")
    return values.pop()


def normalize_key(text):
    text = unicodedata.normalize("NFKD", str(text).strip().lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def accounts_from_rows(rows):
    if not isinstance(rows, list):
        raise ConfigError("La fuente debe contener una lista de registros")
    accounts = {}
    for index, row in enumerate(rows, 2):
        if not isinstance(row, dict):
            raise ConfigError(f"Fila {index}: se esperaba un objeto")
        normalized = {}
        for key, value in row.items():
            key = normalize_key(key)
            if key in normalized:
                raise ConfigError(f"Fila {index}: cabeceras equivalentes duplicadas")
            normalized[key] = value
        if not any(v not in (None, "") for v in normalized.values()):
            continue
        email = next((normalized[k] for k in ("correo electronico", "email", "correo", "usuario") if k in normalized), None)
        password = next((normalized[k] for k in ("contrasena", "password", "clave") if k in normalized), None)
        if not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            raise ConfigError(f"Fila {index}: falta un correo válido")
        if not isinstance(password, str) or not password:
            raise ConfigError(f"Fila {index}: la contraseña debe ser texto no vacío; usa formato texto en la hoja")
        email = email.strip()
        key = email.casefold()
        account = Account(email, password)  # No alterar espacios ni caracteres de la contraseña.
        if key in accounts and accounts[key].password != password:
            raise ConfigError(f"Fila {index}: cuenta duplicada con contraseñas distintas")
        accounts.setdefault(key, account)
    return list(accounts.values())


def sheet_key(value):
    value = str(value).strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    key = match.group(1) if match else value.split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", key):
        raise ConfigError("SHEET_ID debe ser el ID de la hoja o su URL completa")
    return key


def load_config(path: Path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigError("No se puede leer config.json; comprueba la ruta y su sintaxis") from None
    if not isinstance(config, dict):
        raise ConfigError("config.json debe contener un objeto")
    config["_config_dir"] = str(path.resolve().parent)
    for env, key in (("SHEET_ID", "sheet_id"), ("WORKSHEET", "worksheet"), ("CHAT_ID", "telegram_chat_id")):
        if os.environ.get(env):
            config[key] = os.environ[env]
    for key in ("login_url", "balance_url"):
        parsed = urlparse(config.get(key, ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ConfigError(f"{key} debe ser una URL HTTPS sin credenciales")
    for key in ("email_selector", "password_selector", "balance_selector"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ConfigError(f"Falta {key}")
    for key in ("timeout_ms", "max_consecutive_technical_errors", "max_seconds"):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ConfigError(f"{key} debe ser un entero positivo")
    pause = config.get("pause_seconds")
    if type(pause) not in (int, float) or not 0 <= pause <= 3600:
        raise ConfigError("pause_seconds debe estar entre 0 y 3600")
    hosts = config.get("allowed_auth_hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(h, str) and re.fullmatch(r"[A-Za-z0-9.-]+", h) for h in hosts):
        raise ConfigError("allowed_auth_hosts debe ser una lista de nombres de host exactos")
    if not isinstance(config.get("output_dir", "resultados"), str):
        raise ConfigError("output_dir debe ser una ruta de carpeta")
    return config


def fingerprint(accounts, config):
    settings = {k: config.get(k) for k in ("login_url", "balance_url", "email_selector", "password_selector", "balance_selector", "submit_selector", "allowed_auth_hosts")}
    raw = json.dumps({"cuentas": sorted(a.email for a in accounts), "config": settings}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()  # Nunca hash de contraseñas.


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".progreso-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_checkpoint(path, expected_fingerprint, emails):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != 1 or data["fingerprint"] != expected_fingerprint:
            raise ValueError
        age = datetime.now(timezone.utc) - datetime.fromisoformat(data["started_at"])
        if not 0 <= age.total_seconds() <= 86400:
            raise ValueError
        rows = data["resultados"]
        if not isinstance(rows, list):
            raise ValueError
        found = set()
        for row in rows:
            if row["cuenta"] not in emails or row["cuenta"] in found or row["estado"] not in STATES:
                raise ValueError
            if row["estado"] == "SALDO_OK" and type(row["saldo_centimos"]) is not int:
                raise ValueError
            found.add(row["cuenta"])
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigError("No se puede reanudar: progreso incompatible, dañado o de hace más de 24 horas") from None
