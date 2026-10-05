import base64
import json
import os
from pathlib import Path

from .core import ConfigError, accounts_from_rows, sheet_key


def read_accounts(config, input_file=None):
    if input_file:
        try:
            rows = json.loads(Path(input_file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ConfigError("No se puede leer el JSON local de cuentas") from None
        return accounts_from_rows(rows)
    key = sheet_key(config.get("sheet_id", ""))
    try:
        import gspread
    except ImportError:
        raise ConfigError("Falta gspread: instala requirements.txt") from None
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    try:
        if os.environ.get("GOOGLE_CREDS_B64"):
            credentials = json.loads(base64.b64decode(os.environ["GOOGLE_CREDS_B64"], validate=True))
            client = gspread.service_account_from_dict(credentials, scopes=scopes)
        else:
            credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or str(Path(config.get("_config_dir", ".")) / "credenciales.json")
            if not Path(credentials_path).is_file():
                raise ConfigError("Falta credenciales.json o GOOGLE_CREDS_B64. Consulta CONFIGURACION.md; también puedes usar --input-file")
            client = gspread.service_account(filename=credentials_path, scopes=scopes)
        client.set_timeout(30)
        book = client.open_by_key(key)
        worksheet = book.worksheet(config["worksheet"]) if config.get("worksheet") else book.sheet1
        rows = worksheet.get_all_records(numericise_ignore=["all"])
    except ConfigError:
        raise
    except Exception:
        raise ConfigError("No se puede leer Google Sheets. Revisa la credencial, las APIs, la pestaña y el permiso de lector de la cuenta de servicio") from None
    return accounts_from_rows(rows)
