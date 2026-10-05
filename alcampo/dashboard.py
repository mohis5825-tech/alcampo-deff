"""Genera un panel estático seguro para publicar como artefacto o GitHub Pages."""
from __future__ import annotations

import json
import os
from pathlib import Path


def mask_account(email: str) -> str:
    """Enmascara el identificador sin ocultar el dominio."""
    local, separator, domain = str(email).partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def _safe_rows(rows):
    """Solo incluye cuentas con saldo leído correctamente."""
    safe = []
    for row in rows:
        saldo = row.get("saldo_centimos")
        if row.get("estado") != "SALDO_OK" or not isinstance(saldo, int) or isinstance(saldo, bool):
            continue
        safe.append({
            "cuenta": mask_account(row.get("cuenta", "")),
            "estado": "SALDO_OK",
            "saldo_eur": saldo / 100,
            "comprobado": row.get("comprobado", ""),
        })
    return sorted(safe, key=lambda item: (-item["saldo_eur"], item["cuenta"]))


def export_dashboard(rows, metadata, directory: Path):
    """Escribe ``index.html`` y ``dashboard.json`` sin contraseñas ni detalles privados."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    public_rows = _safe_rows(rows)
    data = {
        "generated_at": metadata.get("Final UTC", ""),
        "warning": "Solo se publican cuentas con saldo leído; los correos están enmascarados y no hay contraseñas.",
        "summary": {
            "total_saldo_eur": round(sum(row["saldo_eur"] for row in public_rows), 2),
            "saldos_leidos": len(public_rows),
            "cuentas_publicadas": len(public_rows),
            "cuentas_previstas": len(rows),
            "cuentas_procesadas": sum(row.get("estado") != "PENDIENTE" for row in rows),
            "cuentas_excluidas": len(rows) - len(public_rows),
            "errores_tecnicos": sum(row.get("estado") in _TECHNICAL_STATES for row in rows),
        },
        "rows": public_rows,
    }
    temporary = directory / ".dashboard.json.tmp"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, directory / "dashboard.json")
    (directory / "index.html").write_text(_HTML, encoding="utf-8")


_TECHNICAL_STATES = {
    "TIMEOUT", "ERROR_RED", "ERROR_SERVIDOR", "CAMBIO_WEB",
    "ERROR_TECNICO", "VERIFICACION_MANUAL", "LIMITE_SERVICIO",
}


_HTML = r'''<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alcampo · Resumen</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #10141a; color: #edf2f7; }
    main { max-width: 1100px; margin: auto; padding: 28px 18px 48px; }
    h1 { margin: 0 0 6px; }
    .muted { color: #aab5c1; }
    .warning { margin: 18px 0; padding: 12px 14px; border: 1px solid #6b531d;
      border-radius: 8px; background: #302714; color: #ffe7a3; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit,minmax(170px,1fr)); gap: 12px; }
    .card { padding: 16px; border: 1px solid #2d3744; border-radius: 10px; background: #171d25; }
    .label { color: #aab5c1; font-size: .9rem; }
    .value { font-size: 1.55rem; font-weight: 700; margin-top: 6px; }
    table { width: 100%; margin-top: 24px; border-collapse: collapse; background: #171d25; }
    th, td { padding: 10px; border-bottom: 1px solid #2d3744; text-align: left; }
    th { color: #aab5c1; }
    .ok { color: #7ee2a8; }
    @media (max-width: 650px) { th:nth-child(4), td:nth-child(4) { display: none; } }
  </style>
</head>
<body>
<main>
  <h1>Alcampo</h1>
  <div id="updated" class="muted">Cargando…</div>
  <div id="warning" class="warning"></div>
  <section id="cards" class="cards"></section>
  <table>
    <thead><tr><th>Cuenta</th><th>Estado</th><th>Saldo</th><th>Comprobado UTC</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
</main>
<script>
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  const money = value => value == null ? "—" : new Intl.NumberFormat("es-ES", {style:"currency", currency:"EUR"}).format(value);
  const labels = [["total_saldo_eur", "Saldo total"], ["cuentas_publicadas", "Cuentas publicadas"], ["cuentas_excluidas", "Cuentas excluidas"], ["errores_tecnicos", "Errores técnicos"]];
  fetch("dashboard.json", {cache: "no-store"}).then(response => response.json()).then(data => {
    document.getElementById("updated").textContent = `Actualizado: ${data.generated_at || "sin fecha"}`;
    document.getElementById("warning").textContent = data.warning;
    document.getElementById("cards").innerHTML = labels.map(([key, label]) => `<div class="card"><div class="label">${label}</div><div class="value">${key === "total_saldo_eur" ? money(data.summary[key]) : data.summary[key]}</div></div>`).join("");
    document.getElementById("rows").innerHTML = data.rows.map(row => `<tr><td>${esc(row.cuenta)}</td><td class="ok">SALDO_OK</td><td>${money(row.saldo_eur)}</td><td>${esc(row.comprobado)}</td></tr>`).join("");
  }).catch(() => { document.getElementById("warning").textContent = "No se pudo cargar el informe."; });
</script>
</body>
</html>
'''
