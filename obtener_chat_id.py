"""Obtiene el ID de un grupo mediante un comando enviado al propio bot.

Se ejecuta manualmente desde GitHub Actions. No imprime tokens ni JSON.
"""
import os
import sys
import time

import requests


def api_call(session, token, method, **params):
    response = session.get(
        f"https://api.telegram.org/bot{token}/{method}",
        params=params,
        timeout=40,
    )
    data = response.json()
    if not response.ok or not data.get("ok"):
        description = data.get("description", "Error desconocido de Telegram")
        if "webhook" in description.lower():
            raise RuntimeError("Hay un webhook activo: getUpdates no puede utilizarse hasta desactivarlo.")
        if "conflict" in description.lower():
            raise RuntimeError("Otro proceso está consultando las actualizaciones de este bot.")
        raise RuntimeError(f"Telegram: {description}")
    return data["result"]


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Falta el secreto TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        return 1

    with requests.Session() as session:
        try:
            me = api_call(session, token, "getMe")
            username = me["username"]
            print(f"Abre tu grupo y escribe /id@{username}")
            print("Esperando el comando durante 90 segundos...")
            deadline = time.monotonic() + 90
            offset = None
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                params = {"timeout": min(20, max(1, int(remaining))), "allowed_updates": '["message"]'}
                if offset is not None:
                    params["offset"] = offset
                updates = api_call(session, token, "getUpdates", **params)
                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    chat = msg.get("chat") or {}
                    if chat.get("type") not in ("group", "supergroup"):
                        continue
                    command = (msg.get("text") or "").split(maxsplit=1)[0].lower()
                    if command not in ("/id", f"/id@{username.lower()}"):
                        continue
                    chat_id = chat["id"]
                    title = chat.get("title", "Grupo sin nombre")
                    api_call(
                        session, token, "sendMessage",
                        chat_id=chat_id,
                        text=f"📋 ID actual de «{title}»: \\n<code>{chat_id}</code>\\n\\nCópialo en el secreto TELEGRAM_CHAT_ID de GitHub.",
                        parse_mode="HTML",
                    )
                    print(f"ID enviado al grupo «{title}». Consulta Telegram.")
                    return 0
            print("No llegó ningún comando. Repite el workflow y envía /id@NombreDeTuBot mientras esté ejecutándose.")
            return 1
        except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
            print(f"No se pudo obtener el ID: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
