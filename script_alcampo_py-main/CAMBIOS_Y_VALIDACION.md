# Cambios y validación

Fecha: 5 de octubre de 2026. Basado en el ZIP pequeño y en las rutas/selectores de la otra implementación adjunta.

Cambios realizados:

- ID de Sheets normalizado; selección correcta de pestaña y lectura sin convertir contraseñas numéricas.
- Entrada alternativa desde JSON local y validación de cabeceras, campos y duplicados.
- Sustitución de la URL de autorización con parámetros de sesión por la ruta de acceso de la otra implementación.
- Selectores explícitos de correo y contraseña; comprobación de la página de fidelización y de su texto de saldo.
- Un contexto de navegador nuevo por cuenta, sin mezclar sesiones.
- Estados separados para rechazo de autenticación, bloqueo, verificación manual, límite del servicio, timeout, fallo técnico y cuentas pendientes.
- Dinero calculado en céntimos enteros; miles, decimales y signos comprobados.
- Excel ordenado, con importe numérico, resumen y tratamiento de texto para evitar fórmulas procedentes de datos externos.
- Guardado atómico de progreso tras cada cuenta y reanudación explícita hasta 24 horas.
- Parada ante límites del servicio o verificación manual; presupuesto de tiempo y protección ante errores consecutivos.
- Telegram opcional, con timeout, verificación de respuesta y envío de la ruta de Excel realmente generada.
- Secretos mediante entorno o archivo local excluido de Git. Ninguna contraseña de los adjuntos se ha añadido al nuevo paquete.
- Workflow horario sin solapamiento, con pruebas y recuperación de informes parciales como artefactos de corta duración.
- Eliminación de pandas y fijación de las dependencias del entorno probado.

Validación realizada:

| Comprobación | Resultado |
|---|---|
| Instalación del entorno Python 3.12 con las versiones incluidas | Correcta |
| Compatibilidad declarada de dependencias, `pip check` | Sin conflictos |
| Pruebas unitarias y de integración simulada | 15 superadas |
| Excel generado y reabierto con openpyxl | Importes numéricos, orden, cero y texto de fórmula comprobados |
| Google Sheets | Simulado: selección de pestaña y conservación de texto comprobadas |
| Telegram | Simulado: respuesta rechazada, timeout configurado, ruta y ocultación de token comprobados |
| Reanudación y finalización parcial | Comprobadas con datos ficticios |
| Chromium contra web ficticia local | 5 pruebas incluidas; no ejecutadas aquí |
| Inicio de sesión contra Alcampo real | Pendiente de comprobación por el usuario |

La descarga de Chromium en este entorno devolvió archivos inválidos, tanto para el navegador completo como para su variante headless. Por ese motivo no se presentan las cinco pruebas de navegador como superadas. El workflow las ejecuta después de instalar Chromium. Tampoco se han realizado consultas reales a las cuentas, peticiones con la credencial de Google ni envíos a Telegram.

Para validar la integración real, configura tu fuente y ejecuta `python script.py --limit 1 --headed`, añadiendo `--input-file accounts.json` si usas el archivo local. Si la web ha cambiado, el detalle del resultado y una captura con los datos personales ocultos permitirán ajustar la configuración. Los secretos no necesitan compartirse con el asistente.

## Preparación para publicación

Workflow preparado para ejecución horaria en el minuto 17 y Telegram activado por defecto, a petición del usuario. La publicación y activación real están pendientes de conectar GitHub, seleccionar el repositorio y configurar sus secretos. El token se valida antes de consultar las cuentas. Se puede desactivar Telegram con SEND_TELEGRAM=false.
