# Monitor genérico de documentos

Monitor automático de múltiples páginas HTML para detectar enlaces a documentos y enviar **archivos adjuntos** a Telegram.

Inspirado en [age-documentos-monitor](https://github.com/sergioopo/age-documentos-monitor), pero independiente del ranking AGE.

## Arquitectura
cron-job.org → GitHub Actions → Python → sitios web → Telegram; el estado se guarda en `state.json` mediante commits de GitHub Actions.

## Añadir webs
Edita `sources.json` e incorpora un objeto por cada fuente:

```json
{
  "id": "mi-portal",
  "name": "Mi portal",
  "url": "https://example.org/documentos",
  "selector": "main a[href]",
  "extensions": [".pdf", ".docx", ".xlsx", ".zip"],
  "download_markers": ["/download/", "/documents/"],
  "enabled": true
}
```

- `id`: único y estable; identifica el historial de cada web.
- `url`: página HTML de inicio.
- `selector`: selector CSS de enlaces descargables; por defecto `a[href]`.
- `extensions`: tipos permitidos; `download_markers`: fragmentos de ruta para enlaces sin extensión.
- `enabled`: activa la fuente (el ejemplo está desactivado).
- `chat_id` opcional permite otro chat de Telegram para una fuente.

La **primera ejecución** crea un inventario sin mandar documentos antiguos. Las siguientes envían solo enlaces nuevos. Los identificadores combinan fuente y URL.\n\nSi modificas la **URL** de una fuente manteniendo el mismo `id`, el monitor detecta el cambio, crea automáticamente un **nuevo inventario inicial** y **no envía** los documentos históricos de la nueva página. El estado guarda la URL y los identificadores por fuente. Al actualizar desde una versión anterior con listas simples, se reconstruye el inventario inicial de cada fuente por seguridad.

## Configurar Telegram
1. Crea un bot usando **@BotFather** y `/newbot`, añádelo a tu grupo.
2. Obtén el ID del grupo, por ejemplo con `getUpdates` después de enviar un comando al bot. No difundas el token del bot.
3. En el repositorio, añade **Settings → Secrets and variables → Actions**: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
4. En **Actions → Monitor genérico de documentos → Run workflow**, usa `send_test=true` para enviar un archivo de prueba. Usa `dry_run=true` para probar extracción sin enviar.

## Automatizar con cron-job.org
Tras configurar una fuente real y los secretos, crea una tarea en https://cron-job.org cada 5 minutos:

- Método: `POST`
- URL: `https://api.github.com/repos/TU_USUARIO/TU_REPOSITORIO/actions/workflows/monitor.yml/dispatches`
- Body JSON: `{"ref":"main","inputs":{"dry_run":"false","send_test":"false"}}`
- Headers: `Authorization: Bearer TU_TOKEN`, `Accept: application/vnd.github+json`, `Content-Type: application/json`, `User-Agent: documentos-monitor`.

El token GitHub debe tener acceso **solo a este repositorio** y permiso **Actions: Read and write**. No lo publiques. Comprueba el resultado real del workflow en GitHub, no solo el HTTP del disparador.

## Ejecución local y pruebas
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python monitor.py --dry-run
python monitor.py
```

Opcional: `--config ruta.json` y `--state ruta.json`.

## Limitaciones y precauciones
- Pensado para **HTML estático**; no ejecuta JavaScript, no recorre páginas interiores ni resuelve CAPTCHA.
- Detecta cambios de **URL**, no de contenido si se reemplaza un archivo en la misma URL.
- Las descargas se mantienen en memoria y se rechazan las mayores de 45 MiB.
- Un fallo después de enviar pero antes del commit de estado puede provocar un reenvío.
- Respeta condiciones de uso, frecuencia y permisos de cada web.
- GitHub Actions necesita permiso para escribir en contenidos si debe guardar `state.json`.
- No hay fuentes reales activas, secretos ni cronjob configurados por defecto.
