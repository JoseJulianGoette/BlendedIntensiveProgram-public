from openai import OpenAI
from dotenv import load_dotenv
import os
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import csv
import hashlib
import io
import re
import threading
import time

# Große Pläne lokal öffnen dürfen (die Dateien sind vertrauenswürdig)
Image.MAX_IMAGE_PIXELS = None

# ============================================================
# SETTINGS
# ============================================================

# HTW API key: read from the file .env in the project folder
# (see .env.example) - never write it into the code.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# "not-set": the client refuses to start without a key; the server
# then answers with an authentication error.
API_KEY = os.environ.get("HTW_API_KEY") or "not-set"

if API_KEY == "not-set":
    print("HTW_API_KEY is not set - copy .env.example to .env and enter the key.")

# HTW server address: also read from .env (HTW_BASE_URL).
# Without it, the ".invalid" address can never be reached, so no
# plan is sent anywhere (an empty address would make the client
# fall back to OpenAI's own servers).
BASE_URL = os.environ.get("HTW_BASE_URL") or "https://htw-base-url-not-set.invalid/v1"

if BASE_URL.endswith(".invalid/v1"):
    print("HTW_BASE_URL is not set - copy .env.example to .env and enter the server address.")

# Change this to a vision-capable model available on the server
MODEL = "qwen3.8-27b"

# Unterstützte Bildformate
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}

# Name der Ergebnisdatei (wird im Bildordner gespeichert)
CSV_FILENAME = "plan_titel.csv"

# Längste Bildseite in Pixeln, auf die vor dem Senden verkleinert wird.
# Kleiner = weniger Bild-Tokens = schnellere Antwort des Modells.
MAX_SIDE = 2000

# JPEG-Qualität für das gesendete Bild (1-95)
JPEG_QUALITY = 85

# Optional: nur einen Ausschnitt senden (z. B. das Schriftfeld unten rechts).
# Angaben als Anteil von Breite/Höhe: (links, oben, rechts, unten).
# None = ganzes Bild senden.
# Beispiel Schriftfeld unten rechts: CROP_BOX = (0.6, 0.6, 1.0, 1.0)
CROP_BOX = None

# --- Geschwindigkeit -----------------------------------------

# Wie viele Bilder gleichzeitig verarbeitet werden.
# Mit Thinking brauchen Anfragen lange; zu viele parallele Anfragen
# stauen sich auf dem Server und laufen dann in Timeouts.
MAX_WORKERS = 2

# Thinking-Modus des Modells.
#   True  = Modell denkt vor der Antwort nach (genauer, aber langsamer)
#   False = Thinking wird abgeschaltet
#   None  = nichts mitschicken, Server-Standard verwenden
ENABLE_THINKING = True

# Maximale Länge der Antwort in Tokens.
# ACHTUNG: Bei Thinking zählen die "Gedanken" mit! Ist der Wert zu klein,
# bricht das Modell mitten im Denken ab und liefert keinen Titel.
MAX_TOKENS = 4000

# Wie lange (Sekunden) auf eine Antwort gewartet wird, bevor abgebrochen wird
REQUEST_TIMEOUT = 300

# Wie oft eine fehlgeschlagene Anfrage automatisch wiederholt wird
MAX_RETRIES = 1

# Verkleinerte Bilder zwischenspeichern, damit weitere Durchläufe
# (z. B. mit anderem Prompt) die großen TIFFs nicht neu laden müssen.
USE_CACHE = True
CACHE_DIRNAME = "_cache_verkleinert"

PROMPT = (
  "Give me the title of this plan. remember that this are architectural plans of Metro stations. so the title is usually a name of a station. "
        "Answer only with the title itself, without any explanation, "
        "quotation marks or additional text."
)


# ============================================================
# CONNECT TO HTW API
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=REQUEST_TIMEOUT,
    max_retries=MAX_RETRIES,
)

print_lock = threading.Lock()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def fmt(value: float, digits: int = 2) -> str:
    """Zahl mit Dezimalkomma formatieren (für deutsches Excel)."""
    return f"{value:.{digits}f}".replace(".", ",")


def cache_key(image_path: Path) -> str:
    """Eindeutiger Name für die Cache-Datei, abhängig von Datei und Einstellungen."""
    stat = image_path.stat()
    raw = f"{image_path.name}|{stat.st_size}|{stat.st_mtime}|{MAX_SIDE}|{CROP_BOX}|{JPEG_QUALITY}"
    return hashlib.md5(raw.encode()).hexdigest()


def prepare_image(image_path: Path) -> tuple[bytes, dict]:
    """
    Öffnet ein Bild, schneidet optional einen Bereich aus, verkleinert es
    auf MAX_SIDE und gibt es als JPEG-Bytes zurück, plus Infos zur Skalierung.
    """
    with Image.open(image_path) as img:
        # Bei mehrseitigen TIFFs nur die erste Seite verwenden
        img.seek(0)
        orig_w, orig_h = img.size

        # Optionaler Ausschnitt
        if CROP_BOX is not None:
            l, t, r, b = CROP_BOX
            img = img.crop((int(l * orig_w), int(t * orig_h),
                            int(r * orig_w), int(b * orig_h)))
        crop_w, crop_h = img.size

        # Verkleinern: reducing_gap verkleinert erst grob (schnell)
        # und dann fein mit LANCZOS (gute Qualität)
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS, reducing_gap=3.0)
        sent_w, sent_h = img.size

        # JPEG kann nur RGB/Graustufen (TIFFs sind oft 1-Bit, CMYK oder RGBA)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY)

    info = {
        "orig_size": f"{orig_w}x{orig_h}",
        "crop_size": f"{crop_w}x{crop_h}",
        "sent_size": f"{sent_w}x{sent_h}",
        "scale": sent_w / crop_w,
        "orig_mpx": orig_w * orig_h / 1_000_000,
    }
    return buffer.getvalue(), info


def load_image(image_path: Path, cache_dir: Path | None) -> tuple[bytes, dict, bool]:
    """Holt das verkleinerte Bild aus dem Cache oder erzeugt es neu."""
    if cache_dir is not None:
        key = cache_key(image_path)
        jpg_file = cache_dir / f"{key}.jpg"
        info_file = cache_dir / f"{key}.txt"
        if jpg_file.exists() and info_file.exists():
            orig, crop, sent, scale, mpx = info_file.read_text().split(";")
            info = {"orig_size": orig, "crop_size": crop, "sent_size": sent,
                    "scale": float(scale), "orig_mpx": float(mpx)}
            return jpg_file.read_bytes(), info, True

    jpeg_bytes, info = prepare_image(image_path)

    if cache_dir is not None:
        jpg_file.write_bytes(jpeg_bytes)
        info_file.write_text(";".join([info["orig_size"], info["crop_size"],
                                       info["sent_size"], str(info["scale"]),
                                       str(info["orig_mpx"])]))
    return jpeg_bytes, info, False


def clean_answer(text: str) -> str:
    """Entfernt eventuelle <think>-Blöcke, Anführungszeichen und Zeilenumbrüche."""
    if text is None:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip().strip('"').strip("'").strip()
    text = " ".join(text.split())  # Zeilenumbrüche -> ein Leerzeichen
    return text


def ask_model(jpeg_bytes: bytes) -> str:
    """Schickt ein Bild an das Modell und gibt den erkannten Titel zurück."""
    image_base64 = base64.b64encode(jpeg_bytes).decode("utf-8")

    extra = {}
    if ENABLE_THINKING is not None:
        extra["extra_body"] = {"chat_template_kwargs": {"enable_thinking": ENABLE_THINKING}}

    # Qwen empfiehlt mit Thinking temperature 0.6; bei 0 kann sich das Modell
    # beim Denken in Wiederholungsschleifen verfangen (-> sehr lange Laufzeit).
    temperature = 0 if ENABLE_THINKING is False else 0.6

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=temperature,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ],
        **extra,
    )

    choice = response.choices[0]
    title = clean_answer(choice.message.content)

    if not title and choice.finish_reason == "length":
        raise RuntimeError(
            f"Antwort nach {MAX_TOKENS} Tokens abgeschnitten (Modell hat zu lange "
            f"nachgedacht) - MAX_TOKENS erhöhen"
        )
    return title


# ============================================================
# PROCESS ONE IMAGE
# ============================================================

CSV_FIELDS = [
    "Dateiname", "Titel", "Status",
    "Originalgroesse_px", "Originalgroesse_MP", "Ausschnitt_px", "Gesendet_px",
    "Skalierungsfaktor", "Skalierung_Prozent", "Gesendet_KB", "Aus_Cache",
    "Zeit_Vorbereitung_s", "Zeit_Modell_s", "Zeit_Gesamt_s",
]


def process_image(image_path: Path, cache_dir: Path | None) -> dict:
    row = {field: "" for field in CSV_FIELDS}
    row["Dateiname"] = image_path.name
    log = [image_path.name]
    t_prep = t_model = 0.0
    t0 = time.perf_counter()

    try:
        # Schritt 1: Bild laden, ausschneiden, verkleinern (oder aus Cache)
        jpeg_bytes, info, from_cache = load_image(image_path, cache_dir)
        t_prep = time.perf_counter() - t0
        kb = len(jpeg_bytes) / 1024

        row.update({
            "Originalgroesse_px": info["orig_size"],
            "Originalgroesse_MP": fmt(info["orig_mpx"], 1),
            "Ausschnitt_px": info["crop_size"],
            "Gesendet_px": info["sent_size"],
            "Skalierungsfaktor": fmt(info["scale"], 4),
            "Skalierung_Prozent": fmt(info["scale"] * 100, 1),
            "Gesendet_KB": fmt(kb, 0),
            "Aus_Cache": "ja" if from_cache else "nein",
        })
        log.append(f"    {info['orig_size']} -> {info['sent_size']} "
                   f"(Faktor {info['scale']:.3f}, {kb:.0f} KB"
                   f"{', aus Cache' if from_cache else ''})")

        # Schritt 2: Anfrage ans Modell
        t1 = time.perf_counter()
        title = ask_model(jpeg_bytes)
        t_model = time.perf_counter() - t1

        row["Titel"] = title
        row["Status"] = "OK"
        log.append(f"    Titel: {title}")

    except Exception as e:
        if t_prep == 0.0:
            t_prep = time.perf_counter() - t0
        else:
            t_model = time.perf_counter() - t0 - t_prep
        row["Status"] = f"FEHLER: {e}"
        log.append(f"    {row['Status']}")

    t_total = time.perf_counter() - t0
    row["Zeit_Vorbereitung_s"] = fmt(t_prep)
    row["Zeit_Modell_s"] = fmt(t_model)
    row["Zeit_Gesamt_s"] = fmt(t_total)
    log.append(f"    Zeit: {t_prep:.2f}s Vorbereitung + {t_model:.2f}s Modell "
               f"= {t_total:.2f}s")

    row["_t_prep"], row["_t_model"] = t_prep, t_model
    row["_log"] = "\n".join(log)
    return row


# ============================================================
# MAIN
# ============================================================

def main():
    folder = Path(input("Pfad zum Bildordner: ").strip().strip('"'))

    if not folder.is_dir():
        print(f"Ordner nicht gefunden: {folder}")
        return

    images = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not images:
        print("Keine Bilder im Ordner gefunden.")
        return

    cache_dir = None
    if USE_CACHE:
        cache_dir = folder / CACHE_DIRNAME
        cache_dir.mkdir(exist_ok=True)

    print(f"\n{len(images)} Bilder gefunden. Starte Analyse...")
    print(f"MAX_SIDE={MAX_SIDE}, CROP_BOX={CROP_BOX}, MAX_WORKERS={MAX_WORKERS}, "
          f"ENABLE_THINKING={ENABLE_THINKING}, TIMEOUT={REQUEST_TIMEOUT}s, USE_CACHE={USE_CACHE}\n")

    results = []
    run_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(process_image, p, cache_dir) for p in images]
        for done, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            results.append(row)
            with print_lock:
                print(f"[{done}/{len(images)}] {row['_log']}\n")

    run_total = time.perf_counter() - run_start

    # Wieder nach Dateiname sortieren (Threads werden in beliebiger Reihenfolge fertig)
    results.sort(key=lambda r: r["Dateiname"])

    # ============================================================
    # WRITE CSV
    # ============================================================

    csv_path = folder / CSV_FILENAME

    # utf-8-sig + Semikolon, damit Excel (deutsch) Umlaute und Spalten korrekt anzeigt
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    ok_count = sum(1 for r in results if r["Status"] == "OK")
    sum_prep = sum(r["_t_prep"] for r in results)
    sum_model = sum(r["_t_model"] for r in results)

    print("=" * 60)
    print(f"Fertig! {ok_count}/{len(results)} erfolgreich")
    print(f"Gesamtzeit (Wanduhr): {run_total:.1f}s  |  "
          f"{run_total / len(results):.1f}s pro Bild")
    print(f"Summe Vorbereitung: {sum_prep:.1f}s  |  Summe Modell: {sum_model:.1f}s")
    print(f"Ergebnisse gespeichert in: {csv_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()