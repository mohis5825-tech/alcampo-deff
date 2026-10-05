# Alcampo: consulta de cuentas propias

Proyecto corregido del ZIP pequeño. Lee una hoja Google Sheets o un JSON local, consulta las cuentas secuencialmente con Playwright y genera un Excel con saldos numéricos, estados separados y resumen. Guarda el progreso después de cada cuenta. Telegram es opcional.

Los datos de configuración no secretos recuperados de los archivos están en `config.json`: ID de hoja y destino de Telegram. La ruta de acceso y los selectores se han tomado de la otra implementación adjunta. Su funcionamiento contra la web real queda pendiente de una comprobación con tu cuenta; las pruebas incluidas usan datos ficticios y una web local.

## Empezar

Requiere Python 3.12. Descomprime el ZIP y abre una terminal dentro de `script_alcampo_py-main`.

```bash
python -m venv .venv
```

Activa el entorno con `source .venv/bin/activate` en Linux/macOS o `.venv\Scripts\Activate.ps1` en PowerShell. En sistemas donde Python se invoque como `python3`, sustituye el primer comando por `python3 -m venv .venv`.

```bash
python -m pip install -r requirements-lock.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
```

En Linux, si Chromium necesita bibliotecas del sistema: `python -m playwright install --with-deps chromium`.

**Con Google Sheets:** configura la credencial siguiendo `CONFIGURACION.md` y ejecuta:

```bash
python script.py --check-config
python script.py --limit 1 --headed
python script.py
```

**Sin Google:** extrae `script_alcampo_activacion telegram/accounts.json` del ZIP grande que ya tienes y coloca una copia local como `accounts.json` en esta carpeta. No necesitas cuenta de servicio de Google en este modo.

```bash
python script.py --input-file accounts.json --check-config
python script.py --input-file accounts.json --limit 1 --headed
python script.py --input-file accounts.json
```

No se ha incluido una segunda copia de las contraseñas en este proyecto. Los ejemplos de los tests son ficticios. `--check-config` valida y lee la fuente elegida; con Google sí conecta a Sheets, pero no visita Alcampo ni envía mensajes.

## Resultados y reanudación

Se crean `resultados/resultados.xlsx` y `resultados/progreso.json`. Ambos contienen información personal de las cuentas, aunque no contraseñas. El Excel incluye todas las cuentas previstas; las no consultadas figuran como `PENDIENTE`.

```bash
python script.py --resume
python script.py --input-file accounts.json --resume
python script.py --max-seconds 1800 --output-dir resultados
```

Para reanudar, utiliza la misma fuente, selección `--limit`, configuración y carpeta de resultados. Se conservan los resultados terminales anteriores (saldo leído, autenticación rechazada o cuenta bloqueada) y se vuelven a intentar los errores técnicos. Solo se admiten puntos de recuperación de las últimas 24 horas. El resultado conservado mantiene su fecha original: reanudar no equivale a actualizar los saldos ya leídos. Ejecutar sin `--resume` comienza una consulta nueva y reemplaza los archivos de resultados actuales.

Se detiene el lote ante limitación del servicio, verificación manual o una sucesión configurable de errores técnicos. No sortea CAPTCHA ni cambia de IP. El límite de tiempo se aplica a las consultas; exportación, cierre del navegador y notificación pueden añadir unos segundos.

El código de salida permite detectar problemas: `0` lista procesada sin errores técnicos; `1` fallo inesperado; `2` configuración/fuente/notificación incorrecta; `3` interrupción, consulta incompleta o errores técnicos. Un rechazo explícito de autenticación es un resultado de cuenta, no un fallo del programa.

## Telegram y GitHub Actions

Telegram solo se activa con `--telegram`. Después de configurar el token:

```bash
python script.py --telegram
python script.py --input-file accounts.json --telegram
```

Comprueba el destino `telegram_chat_id` recuperado del ZIP antes de activar los envíos. `CHAT_ID` puede sobrescribirlo. No hay tokens incrustados ni destinos de respaldo ocultos. El envío tiene límites de tiempo y valida la confirmación de Telegram; si falla, el Excel permanece guardado.

El workflow está preparado para consultar cada hora, en el minuto 17, evita ejecuciones simultáneas y permite ejecución manual. Utiliza Google Sheets. Para cambiar la frecuencia, edita `schedule` en `.github/workflows/comprobar-cuentas.yml`; la expresión cron está en UTC. En GitHub, Telegram está activado por defecto para las ejecuciones programadas y manuales. Debes guardar `BOT_TOKEN` antes de activar el workflow. Puedes desmarcar la opción en una ejecución manual o establecer la variable `SEND_TELEGRAM=false` para desactivar los envíos programados.

Los artefactos de Actions conservan informe y progreso durante un día, incluso si la consulta falla. Solo quien tenga acceso autorizado al repositorio debe acceder a ellos. Para recuperar una ejecución de Actions, descarga su artefacto y utiliza el `progreso.json` en tu carpeta de resultados con `--resume`; el workflow no recupera automáticamente artefactos de otras ejecuciones.

## Pruebas y límites

`tests/test_project.py` cubre importes, entradas, Sheets simulado, errores HTTP, exportación Excel, Telegram simulado y reanudación. Las pruebas no llaman a servicios externos.

Las pruebas de Chromium utilizan exclusivamente un servidor ficticio en `127.0.0.1`. Se activan en Linux/macOS con:

```bash
ALCAMPO_BROWSER_TESTS=1 python -m unittest discover -s tests -v
```

En PowerShell, establece antes `$env:ALCAMPO_BROWSER_TESTS='1'`.

La primera consulta real con `--limit 1 --headed` permite comprobar si la web conserva los selectores adjuntos. Si aparece `TIMEOUT` o `CAMBIO_WEB`, revisa el campo `detalle` del Excel. Una captura del formulario y de la zona de saldo, ocultando información personal, permite ajustar la integración sin compartir tus contraseñas.

`requirements-lock.txt` contiene el entorno Python validado; `requirements.txt` enumera las dependencias directas. No se usa pandas, Firebase ni Selenium en esta versión.
