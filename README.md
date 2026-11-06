# Monitor genérico de documentos

Monitor automático de páginas HTML para detectar **documentos descargables y enlaces nuevos**. Envía los documentos como adjuntos y las páginas como mensajes de Telegram.

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
  "mode": "both",
  "link_include": [],
  "link_exclude": [],
  "extensions": [".pdf", ".docx", ".xlsx", ".zip", ".rtf"],
  "download_markers": ["/download/", "/documents/"],
  "enabled": true
}
```

- `id`: único y estable; identifica el historial de cada web.
- `url`: página HTML de inicio.
- `selector`: selector CSS de enlaces descargables; por defecto `a[href]`.
- `extensions`: tipos permitidos; `download_markers`: fragmentos de ruta para enlaces sin extensión. También se detectan enlaces con atributo HTML `download` o con `type="application/..."` (excepto HTML), igual que en el monitor original.
- `mode`: `documents` (predeterminado, compatible con las fuentes antiguas), `links` (solo páginas web) o `both` (ambos).
- `link_include` y `link_exclude`: listas opcionales de palabras que se buscan en el título o URL **solo de enlaces web**; por ejemplo `["convocatoria", "resolución"]`. Las coincidencias no distinguen mayúsculas. Una lista vacía no filtra.
- En modo `both`, los PDF se envían como adjuntos y las páginas HTML como mensajes con título y URL. **No se abren las páginas secundarias** ni se buscan documentos dentro de ellas.
- El selector debe apuntar a los enlaces relevantes: con `a[href]` podrían notificarse menús y enlaces de navegación. Ajusta el selector y los filtros.
- `enabled`: activa la fuente (el ejemplo está desactivado).
- `chat_id` opcional permite otro chat de Telegram para una fuente.

La **primera ejecución** crea un inventario sin mandar documentos o enlaces antiguos. Las siguientes envían solo enlaces nuevos. Los identificadores combinan fuente y URL. Al activar un nuevo tipo cambiando `mode`, los enlaces o documentos de ese tipo ya presentes se inventarían sin enviar avisos históricos; las novedades posteriores sí se notifican.\n\nSi modificas la **URL** de una fuente manteniendo el mismo `id`, el monitor detecta el cambio, crea automáticamente un **nuevo inventario inicial** y **no envía** los documentos históricos de la nueva página. El estado guarda la URL y los identificadores por fuente. Al actualizar desde una versión anterior con listas simples, se reconstruye el inventario inicial de cada fuente por seguridad.

## Reintentos y registro semanal
Las consultas web, descargas y envíos a Telegram tienen **hasta 3 intentos**, con esperas de **5 y 15 segundos** ante errores de conexión o HTTP temporales (408, 429, 500, 502, 503, 504). Los errores permanentes como 401, 403 y 404 no se reintentan inmediatamente. En Telegram, un error 429 respeta el tiempo `retry_after` comunicado por la API (hasta 120 segundos).

Cada fuente mantiene en `state.json` `heartbeat_week` (semana UTC), `last_success` (última ejecución correcta), `last_documents_found` (cantidad de elementos detectados, incluidos enlaces) y, si falla, `last_error`. El último éxito se conserva cuando ocurre un fallo. No se envían mensajes semanales adicionales.

El inventario inicial sigue sin enviar documentos antiguos y `dry_run` no modifica el estado. Los reintentos de Telegram pueden generar duplicados si Telegram recibe el archivo pero se pierde su respuesta.

## Configurar Telegram
1. Crea un bot usando **@BotFather** y `/newbot`, añádelo a tu grupo.
2. Guarda primero el secreto `TELEGRAM_BOT_TOKEN`. Ve a **Actions → Obtener ID de Telegram → Run workflow**. Mientras se ejecuta, envía al grupo `/id@NombreDeTuBot` (sustituye el nombre por el de tu bot). El bot responderá **en el propio grupo** con su ID, sin mostrar JSON. Copia el número completo, incluido el signo negativo.\n   - El workflow escucha durante 90 segundos; si termina antes, ejecútalo otra vez. No se requiere `TELEGRAM_CHAT_ID` para este paso.\n   - Funciona en grupos y supergrupos. Si Telegram convierte el grupo en supergrupo, el ID puede cambiar: repite el procedimiento y actualiza el secreto `TELEGRAM_CHAT_ID`.\n   - No ejecutes simultáneamente otro consumidor de `getUpdates` ni mantengas un webhook activo para el mismo bot. No difundas el token del bot.
3. En **Settings → Secrets and variables → Actions**, añade `TELEGRAM_CHAT_ID` con el número que te respondió el bot (el token ya se guardó en el paso anterior).
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
