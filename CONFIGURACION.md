# Datos que necesitas configurar

Para preparar y probar el proyecto no hace falta compartir ningún secreto. Para ejecutarlo, elige la fuente:

| Modo | Google | Telegram |
|---|---|---|
| JSON local con tus cuentas | No hace falta | Opcional |
| Google Sheets | Cuenta de servicio con acceso de lector a tu hoja | Opcional |

El ID de la hoja ya está corregido en `config.json`. Si la pestaña correcta no es la primera, escribe su nombre exacto en `worksheet`. Las columnas pueden llamarse `Correo electrónico` y `Contraseña`, o `email` y `password`. Configura las columnas como texto para conservar contraseñas numéricas y ceros iniciales. No se recortan espacios de las contraseñas.

## Conseguir la credencial de Google

1. Entra en [Google Cloud Console](https://console.cloud.google.com/), con tu cuenta, y selecciona o crea un proyecto.
2. En APIs y servicios, habilita Google Sheets API y Google Drive API.
3. Crea una cuenta de servicio. En su apartado Claves, crea una clave de tipo JSON si la política de tu organización lo permite.
4. Descarga el JSON como `credenciales.json` y colócalo en la carpeta del proyecto. Alternativamente, configura `GOOGLE_APPLICATION_CREDENTIALS` con su ruta. No lo añadas a Git ni lo envíes por chat.
5. Dentro del JSON, copia el valor `client_email`. Comparte tu hoja de Google con ese correo, con permiso de **Lector**. No es necesario hacer pública la hoja.
6. Ejecuta `python script.py --check-config`.

El programa pide únicamente acceso de lectura a Sheets y no modifica la hoja. Referencia: [autenticación de gspread](https://docs.gspread.org/en/latest/oauth2.html).

## Guardar la credencial en GitHub Actions

En tu repositorio: **Settings → Secrets and variables → Actions → New repository secret**. Crea `GOOGLE_CREDS_B64` con el JSON codificado en base64. Base64 es una codificación, no un cifrado: el valor también debe mantenerse privado.

Para crear un archivo local con ese valor, desde la carpeta del proyecto:

```bash
python -c "import base64,pathlib; p=pathlib.Path; p('google_creds.b64').write_text(base64.b64encode(p('credenciales.json').read_bytes()).decode())"
```

Copia el contenido de `google_creds.b64` al secret y elimina ese archivo local cuando termines. Está excluido por `.gitignore`. El workflow carga el secret en memoria sin escribir la clave JSON en el runner.

Opcionalmente, crea las variables de repositorio `SHEET_ID` y `WORKSHEET` para sobrescribir `config.json`. No necesitas subir el JSON de las cuentas cuando usas Sheets.

## Telegram, solo si quieres recibir el Excel

El token que aparecía incrustado en los archivos no se reutiliza. Si era tu bot, regenera su token desde [BotFather](https://t.me/BotFather). Inicia una conversación con el bot, o añádelo al grupo de destino y concede los permisos de envío necesarios.

El `telegram_chat_id` del ZIP anterior está conservado en `config.json`; verifica que siga siendo el destino correcto. Si necesitas otro ID, puedes identificar el `chat.id` de un mensaje recibido mediante `getUpdates` de la [API oficial de Telegram](https://core.telegram.org/bots/api#getupdates). No introduzcas el token en sitios de terceros.

En GitHub, crea los secrets `BOT_TOKEN` y `CHAT_ID`. El workflow tiene activado el envío de informes por defecto. Puedes desmarcarlo en una ejecución manual o establecer la variable de repositorio `SEND_TELEGRAM=false` para desactivar los envíos programados.

En Linux/macOS, puedes cargar el token localmente sin escribirlo en el historial de comandos:

```bash
read -rs -p 'Token nuevo del bot: ' BOT_TOKEN
export BOT_TOKEN
python script.py --telegram
unset BOT_TOKEN
```

En PowerShell:

```powershell
$env:BOT_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Token nuevo del bot' -AsSecureString)).Password
python script.py --telegram
Remove-Item Env:BOT_TOKEN
```

La clave de Google y el token solo se necesitan en el equipo o runner que ejecuta el programa. No es necesario enviarlos al asistente. Referencias: [token de bot](https://core.telegram.org/bots/tutorial#obtain-your-bot-token) y [secrets de GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
