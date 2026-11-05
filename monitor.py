"""Monitor configurable de documentos HTML y notificaciones a Telegram."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".csv", ".zip", ".7z", ".rtf"]
MAX_BYTES = 45 * 1024 * 1024
HEADERS = {"User-Agent": "DocumentosMonitor/1.1", "Accept-Language": "es-ES,es;q=0.9"}


def load_sources(path):
    sources = json.loads(Path(path).read_text(encoding="utf-8"))["sources"]
    if not isinstance(sources, list):
        raise ValueError("'sources' debe ser una lista")
    ids = set()
    for source in sources:
        if not all(source.get(k) for k in ("id", "name", "url")):
            raise ValueError("Cada fuente necesita id, name y url")
        sid = source["id"]
        if not re.fullmatch("[a-z0-9][a-z0-9_-]{0,63}", sid) or sid in ids:
            raise ValueError("ID inválido o duplicado: " + sid)
        parsed = urlparse(source["url"])
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("URL inválida: " + source["url"])
        ids.add(sid)
    return sources


def get(url, timeout=30):
    for attempt in range(2):
        try:
            result = requests.get(url, timeout=timeout, headers=HEADERS)
            result.raise_for_status()
            return result
        except requests.RequestException:
            if attempt:
                raise
            time.sleep(5)


def discover(source, html=None):
    if html is None:
        html = get(source["url"]).text
    soup = BeautifulSoup(html, "html.parser")
    extensions = tuple(x.lower() for x in source.get("extensions", DEFAULT_EXTENSIONS))
    markers = tuple(x.lower() for x in source.get("download_markers", []))
    found = {}
    for link in soup.select(source.get("selector", "a[href]")):
        href = link.get("href")
        if not href:
            continue
        url = urljoin(source["url"], href).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        path = unquote(parsed.path).lower()
        query = unquote(parsed.query).lower()
        link_type = link.get("type", "").lower()
        is_document = (
            path.endswith(extensions)
            or any(x in query for x in extensions)
            or any(x in path for x in markers)
            or link.has_attr("download")
            or (link_type.startswith("application/") and "html" not in link_type)
        )
        if not is_document:
            continue
        title = (link.get_text(" ", strip=True)
                 or link.get("aria-label", "").strip()
                 or link.get("title", "").strip()
                 or unquote(Path(parsed.path).name)
                 or "Documento")
        key = hashlib.sha256((source["id"] + "|" + url).encode()).hexdigest()[:24]
        found[key] = {"title": title, "url": url}
    return found


def save_state(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def send_document(source, item, token, chat):
    response = get(item["url"], timeout=90)
    content_type = response.headers.get("Content-Type", "application/octet-stream").lower()
    if "text/html" in content_type:
        raise ValueError("El enlace devuelve HTML: " + item["url"])
    if len(response.content) > MAX_BYTES:
        raise ValueError("Documento demasiado grande")
    filename = unquote(Path(urlparse(item["url"]).path).name) or "documento"
    filename = re.sub(r'[\\/:*?"<>|]+', "-", filename).strip(". ")[:130] or "documento"
    if "." not in filename:
        filename += ".pdf" if "pdf" in content_type else ".bin"
    caption = ("Nuevo documento · " + source["name"] + "\n" + item["title"] + "\n" + item["url"])[:1000]
    result = requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data={"chat_id": chat, "caption": caption},
        files={"document": (filename, response.content, content_type)}, timeout=120)
    result.raise_for_status()
    if not result.json().get("ok"):
        raise RuntimeError("Telegram no confirmó el envío")


def send_test(token, chat):
    result = requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data={"chat_id": chat, "caption": "Prueba de monitor genérico"},
        files={"document": ("prueba.txt", b"Monitor conectado a Telegram.", "text/plain")},
        timeout=30)
    result.raise_for_status()
    if not result.json().get("ok"):
        raise RuntimeError("Telegram no confirmó la prueba")


def run(sources, state_path, dry_run=False, token="", default_chat=""):
    state_path = Path(state_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    errors = []
    for source in sources:
        if not source.get("enabled", False):
            continue
        sid = source["id"]
        try:
            found = discover(source)
            print(f"{sid}: {len(found)} documentos encontrados")
            if dry_run:
                print(f"{sid}: simulación; sin envíos ni estado")
                continue
            previous = state.get(sid)
            # Formato antiguo: lista sin URL de origen. Se migra con un
            # inventario seguro para evitar envíos masivos por cambio de web.
            if (previous is None or isinstance(previous, list)
                    or not isinstance(previous, dict)
                    or previous.get("url") != source["url"]):
                reason = "URL modificada" if isinstance(previous, dict) and previous.get("url") != source["url"] else "inventario inicial o migración"
                state[sid] = {"url": source["url"], "processed": sorted(found)}
                save_state(state_path, state)
                print(f"{sid}: {reason}; {len(found)} documentos registrados sin enviar históricos")
                continue
            seen = set(previous["processed"])
            for key, item in found.items():
                if key in seen:
                    continue
                chat = source.get("chat_id") or default_chat
                if not token or not chat:
                    raise ValueError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
                send_document(source, item, token, str(chat))
                seen.add(key)
                state[sid]["processed"] = sorted(seen)
                save_state(state_path, state)
                print(f"{sid}: enviado {item['title']}")
        except Exception as error:
            errors.append(sid)
            print(f"ERROR {sid}: {type(error).__name__}: {error}", file=sys.stderr)
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="sources.json")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if args.send_test:
        if not token or not chat:
            parser.error("Configura primero los secretos de Telegram")
        send_test(token, chat)
        print("Mensaje de prueba enviado")
    errors = run(load_sources(args.config), args.state, args.dry_run, token, chat)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
