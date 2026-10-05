import re
import time
from urllib.parse import urlparse

from .core import balance_from_text, result


def page_issue(text):
    text = text.casefold()
    if any(x in text for x in ("tu cuenta ha sido bloqueada", "cuenta bloqueada")):
        return "CUENTA_BLOQUEADA"
    if any(x in text for x in ("usuario o contraseña incorrectos", "credenciales incorrectas")):
        return "AUTENTICACION_RECHAZADA"
    if any(x in text for x in ("verifica que eres humano", "verify you are human", "código de verificación", "introduce el código de seguridad")):
        return "VERIFICACION_MANUAL"
    return None


def http_issue(response):
    if response is None:
        return None
    if response.status == 429:
        return "LIMITE_SERVICIO"
    if response.status in (401, 403):
        return "VERIFICACION_MANUAL"
    if response.status >= 500:
        return "ERROR_SERVIDOR"
    if response.status >= 400:
        return "ERROR_RED"
    return None


def process_account(browser, account, config, remaining_seconds=None):
    from playwright.sync_api import Error, TimeoutError as PlaywrightTimeout

    context = None
    stage = "inicio"
    budget = config["timeout_ms"] / 1000 * 3
    if remaining_seconds is not None:
        budget = min(budget, remaining_seconds)
    deadline = time.monotonic() + budget

    def timeout():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PlaywrightTimeout("Presupuesto de tiempo agotado")
        return max(1, min(config["timeout_ms"], int(remaining * 1000)))

    try:
        context = browser.new_context(locale="es-ES")
        page = context.new_page()
        page.set_default_timeout(config["timeout_ms"])
        stage = "carga del formulario"
        issue = http_issue(page.goto(config["login_url"], wait_until="domcontentloaded", timeout=timeout()))
        if issue:
            return result(account.email, issue, detail=stage)
        issue = page_issue(page.locator("body").inner_text(timeout=timeout()))
        if issue:
            return result(account.email, issue, detail=stage)
        cookies = page.get_by_role("button", name=re.compile(r"^(Aceptar cookies|Aceptar todas|Aceptar)$", re.I))
        if cookies.count() and cookies.first.is_visible():
            cookies.first.click(timeout=min(timeout(), 2000))
        field = page.locator(config["email_selector"])
        field.wait_for(state="visible", timeout=timeout())
        trusted = {urlparse(config["login_url"]).hostname, *config.get("allowed_auth_hosts", [])}
        if urlparse(page.url).hostname not in trusted or urlparse(page.url).scheme != urlparse(config["login_url"]).scheme:
            return result(account.email, "CAMBIO_WEB", detail="Redirección a un dominio de acceso no configurado")
        field.fill(account.email, timeout=timeout())
        password = page.locator(config["password_selector"])
        password.fill(account.password, timeout=timeout())
        stage = "respuesta de autenticación"
        if config.get("submit_selector"):
            page.locator(config["submit_selector"]).click(timeout=timeout())
        else:
            password.press("Enter", timeout=timeout())

        destination = urlparse(config["balance_url"])
        while True:
            timeout()
            issue = page_issue(page.locator("body").inner_text(timeout=timeout()))
            if issue:
                return result(account.email, issue, detail=stage)
            current = urlparse(page.url)
            if (current.hostname == destination.hostname
                    and not any(word in current.path.lower() for word in ("login", "authentication", "authorization"))
                    and not page.locator(config["password_selector"]).is_visible()):
                break
            page.wait_for_timeout(min(250, timeout()))

        stage = "lectura del saldo"
        issue = http_issue(page.goto(config["balance_url"], wait_until="domcontentloaded", timeout=timeout()))
        if issue:
            return result(account.email, issue, detail=stage)
        while True:
            timeout()
            body = page.locator("body").inner_text(timeout=timeout())
            issue = page_issue(body)
            if issue:
                return result(account.email, issue, detail=stage)
            if page.locator(config["password_selector"]).is_visible():
                return result(account.email, "VERIFICACION_MANUAL", detail="La web ha solicitado iniciar sesión de nuevo")
            location = urlparse(page.url)
            if location.hostname == destination.hostname and location.path.rstrip("/") == destination.path.rstrip("/"):
                selected_text = page.locator(config["balance_selector"]).inner_text(timeout=timeout())
                cents = balance_from_text(selected_text)
                if cents is not None:
                    return result(account.email, "SALDO_OK", cents)
            page.wait_for_timeout(min(250, timeout()))
    except PlaywrightTimeout:
        if context is not None:
            try:
                issue = page_issue(page.locator("body").inner_text(timeout=500))
                if issue:
                    return result(account.email, issue, detail=stage)
            except Exception:
                pass
        return result(account.email, "TIMEOUT", detail=stage)
    except ValueError:
        return result(account.email, "CAMBIO_WEB", detail="Formato de saldo ambiguo o no reconocido")
    except Error:
        return result(account.email, "ERROR_TECNICO", detail=f"Fallo del navegador durante {stage}")
    except Exception:
        return result(account.email, "ERROR_TECNICO", detail=f"Fallo durante {stage}")
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
