from openai import OpenAI
from dotenv import load_dotenv
import os
from pathlib import Path
from PIL import Image
import base64
import csv
import io
import re

# Große Pläne lokal öffnen dürfen (die Dateien sind vertrauenswürdig)
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

# Unterstützte Bildformate
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}

# Name der Ergebnisdatei (wird im Bildordner gespeichert)
CSV_FILENAME = "plan_titel.csv"

# Längste Bildseite in Pixeln, auf die vor dem Senden verkleinert wird
MAX_SIDE = 3000

# JPEG-Qualität für das gesendete Bild (1-95)
JPEG_QUALITY = 90

# Optional: nur einen Ausschnitt senden (z. B. das Schriftfeld unten rechts).
# Angaben als Anteil von Breite/Höhe: (links, oben, rechts, unten).
# None = ganzes Bild senden.
# Beispiel Schriftfeld unten rechts: CROP_BOX = (0.6, 0.6, 1.0, 1.0)
CROP_BOX = None

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
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def encode_image(image_path: Path) -> tuple[str, str]:
    """
    Öffnet ein Bild, schneidet optional einen Bereich aus, verkleinert es
    auf MAX_SIDE und gibt es als JPEG zurück: (mime_type, base64-String).
    """
    with Image.open(image_path) as img:
        # Bei mehrseitigen TIFFs nur die erste Seite verwenden
        img.seek(0)

        # Optionaler Ausschnitt
        if CROP_BOX is not None:
            w, h = img.size
            l, t, r, b = CROP_BOX
            img = img.crop((int(l * w), int(t * h), int(r * w), int(b * h)))

        # Verkleinern, Seitenverhältnis bleibt erhalten
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

        # JPEG kann nur RGB/Graustufen (TIFFs sind oft 1-Bit, CMYK oder RGBA)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY)

    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return "image/jpeg", image_base64


def clean_answer(text: str) -> str:
    """Entfernt eventuelle <think>-Blöcke, Anführungszeichen und Zeilenumbrüche."""
    if text is None:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip().strip('"').strip("'").strip()
    text = " ".join(text.split())  # Zeilenumbrüche -> ein Leerzeichen
    return text


def get_plan_title(image_path: Path) -> str:
    """Schickt ein Bild an das Modell und gibt den erkannten Titel zurück."""
    mime_type, image_base64 = encode_image(image_path)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}"
                        },
                    },
                ],
            }
        ],
    )

    return clean_answer(response.choices[0].message.content)


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

    print(f"\n{len(images)} Bilder gefunden. Starte Analyse...\n")

    results = []

    for i, image_path in enumerate(images, start=1):
        print(f"[{i}/{len(images)}] {image_path.name} ... ", end="", flush=True)
        try:
            title = get_plan_title(image_path)
            status = "OK"
            print(title)
        except Exception as e:
            title = ""
            status = f"FEHLER: {e}"
            print(status)

        results.append({
            "Dateiname": image_path.name,
            "Titel": title,
            "Status": status,
        })

    # ============================================================
    # WRITE CSV
    # ============================================================

    csv_path = folder / CSV_FILENAME

    # utf-8-sig + Semikolon, damit Excel (deutsch) Umlaute und Spalten korrekt anzeigt
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["Dateiname", "Titel", "Status"], delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    print("\n" + "=" * 60)
    print(f"Fertig! Ergebnisse gespeichert in: {csv_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()