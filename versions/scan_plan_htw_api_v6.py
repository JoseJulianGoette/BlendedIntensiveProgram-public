from openai import OpenAI
from dotenv import load_dotenv
import os
from pathlib import Path
from PIL import Image
import pypdfium2 as pdfium
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import csv
import hashlib
import io
import json
import math
import re
import threading
import time

from models_v7 import Confidence, ImageData, Metadata, TrafficLight

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


# Supported file formats.
# PDFs are rendered to an image first (only the first page, see render_pdf_page).

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}


# Name of the result file (saved inside the image folder)

CSV_FILENAME = "plan_metadata_v6.csv"


# Same results as a list of ImageData objects (see models.py)

JSON_FILENAME = "plan_metadata_v6.json"


# Maximum length of the longest image side in pixels before sending.
# Smaller = fewer image tokens = faster model response.

MAX_SIDE = 3000


# JPEG quality for the image sent to the model (1-95)

JPEG_QUALITY = 85


# Optional: send only a crop of the image
# (for example, the title block in the bottom-right corner).
#
# Values are fractions of width/height:
# (left, top, right, bottom)
#
# None = send the entire image.
#
# Example: title block in the bottom-right:
# CROP_BOX = (0.6, 0.6, 1.0, 1.0)

CROP_BOX = None


# --- Speed ---------------------------------------------------


# Number of images processed simultaneously.
#
# With Thinking enabled, requests can take a long time.
# Too many parallel requests may queue on the server
# and eventually cause timeouts.

MAX_WORKERS = 2


# Model Thinking mode.
#
# True  = model thinks before answering
#         (potentially more accurate, but slower)
#
# False = Thinking is disabled
#
# None  = do not send a setting;
#         use the server default
#
# Disabled for reproducible results: with Thinking the model needs
# temperature > 0 (see build_request), so answers would vary per run.

ENABLE_THINKING = False


# --- Reproducibility ----------------------------------------


# Fixed sampling seed. Together with temperature 0 / top_p 1
# the same image should always give the same answer.

SEED = 42


# Force the answer into the JSON schema of models.Metadata
# (structured output via response_format).
#
# Set to False if the server does not support json_schema;
# the answer is then still parsed and validated against Metadata.

USE_JSON_SCHEMA = True


# --- Confidence (traffic light) -----------------------------


# Location, title and date are each rated by the probability of
# their least certain token (logprobs from the server):
#
#   probability >= CONFIDENCE_GREEN   -> green  (sure)
#   probability >= CONFIDENCE_YELLOW  -> yellow (check manually)
#   below, or field not found (null)  -> red    (probably wrong)
#
# Starting values - calibrate against manually checked plans.

CONFIDENCE_GREEN = 0.90

CONFIDENCE_YELLOW = 0.50


# Number of alternative tokens per position requested from the server.
# Needed because the same text can be split into tokens in different
# ways (" Ab"+"ort" vs " Abort") - those alternatives are counted
# as agreeing, not competing.

TOP_LOGPROBS = 5


# Maximum response length in tokens.
#
# IMPORTANT:
# When Thinking is enabled, the reasoning tokens count too.
# If this value is too small, the model may stop while thinking
# and never return the title.
#
# None = do not send a limit; use server default

MAX_TOKENS = None


# Number of seconds to wait for a response before cancelling

REQUEST_TIMEOUT = 300


# Number of times a failed request is automatically retried

MAX_RETRIES = 1


# Receive the response incrementally using streaming.
#
# This shows live progress and can help prevent proxy timeouts
# because data is continuously being received.

USE_STREAMING = True


# How often to print a progress message, in seconds

PROGRESS_INTERVAL = 10


# Send a short request without an image before processing starts
# to check the connection

CONNECTION_TEST = True


# Cache resized images so that future runs
# (for example with a different prompt)
# do not need to load and resize the large TIFF files again.

USE_CACHE = True

CACHE_DIRNAME = "_cache_resized"


PROMPT = (
    "This is a scanned architectural plan of a metro (U-Bahn) station. "
    "Extract the following fields, mainly from the title block:\n"
    "- location: the place the plan refers to, usually the station name "
    "or street. Only the name itself, without words like 'Haltestelle', "
    "'Bahnhof' or 'U-Bahnhof'.\n"
    "- title: the full title of the plan.\n"
    "- date: the date of the plan, in ISO format YYYY-MM-DD, YYYY-MM or "
    "YYYY depending on the precision given on the plan.\n"
    "\n"
    "Rules:\n"
    "- Copy location and title exactly as written on the plan "
    "(keep umlauts and ß, do not translate, do not correct).\n"
    "- Do not guess. If a field is not on the plan, use null.\n"
    "- Answer only with a JSON object of the form "
    '{"location": ..., "title": ..., "date": ...} '
    "without any explanation or additional text."
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


# PDFium is not thread-safe -> only one PDF is rendered at a time

pdf_lock = threading.Lock()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def fmt(value: float, digits: int = 2) -> str:
    """Format a number using a decimal comma for Excel."""
    return f"{value:.{digits}f}".replace(".", ",")


def cache_key(image_path: Path) -> str:
    """Create a unique cache filename based on the file and current settings."""

    stat = image_path.stat()

    raw = (
        f"{image_path.name}|"
        f"{stat.st_size}|"
        f"{stat.st_mtime}|"
        f"{MAX_SIDE}|"
        f"{CROP_BOX}|"
        f"{JPEG_QUALITY}"
    )

    return hashlib.md5(raw.encode()).hexdigest()


def render_pdf_page(pdf_path: Path) -> Image.Image:
    """
    Render the first page of a PDF to an image.

    The resolution is chosen so that the (optionally cropped) area
    has MAX_SIDE pixels on its longest side - rendering larger would
    only be thrown away by the resize in prepare_image.
    """

    with pdf_lock:

        pdf = pdfium.PdfDocument(pdf_path)

        try:

            if len(pdf) > 1:

                log_print(
                    f"  !! {pdf_path.name}: {len(pdf)} pages, "
                    f"only the first page is used"
                )

            page = pdf[0]

            page_w, page_h = page.get_size()

            l, t, r, b = CROP_BOX or (0, 0, 1, 1)

            scale = MAX_SIDE / max(
                page_w * (r - l),
                page_h * (b - t)
            )

            # copy(): detach the image from PDFium's buffer
            # before the document is closed
            img = page.render(scale=scale).to_pil().copy()

        finally:

            pdf.close()

    return img


def open_first_page(image_path: Path) -> Image.Image:
    """
    Open an image or PDF and return its first page as a PIL image.
    """

    if image_path.suffix.lower() == ".pdf":
        return render_pdf_page(image_path)

    img = Image.open(image_path)

    # For multi-page TIFF files, use only the first page
    img.seek(0)

    return img


def prepare_image(image_path: Path) -> tuple[bytes, dict]:
    """
    Open an image (or PDF), optionally crop it, resize it to MAX_SIDE,
    and return it as JPEG bytes together with scaling information.
    """

    with open_first_page(image_path) as img:

        orig_w, orig_h = img.size


        # Optional crop
        if CROP_BOX is not None:

            l, t, r, b = CROP_BOX

            img = img.crop(
                (
                    int(l * orig_w),
                    int(t * orig_h),
                    int(r * orig_w),
                    int(b * orig_h),
                )
            )

        crop_w, crop_h = img.size


        # Resize:
        # reducing_gap first performs a quick reduction,
        # then LANCZOS performs a higher-quality resize.

        img.thumbnail(
            (MAX_SIDE, MAX_SIDE),
            Image.LANCZOS,
            reducing_gap=3.0
        )

        sent_w, sent_h = img.size


        # JPEG supports RGB / grayscale.
        # TIFF files are often 1-bit, CMYK, RGBA, etc.

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")


        buffer = io.BytesIO()

        img.save(
            buffer,
            format="JPEG",
            quality=JPEG_QUALITY
        )


    info = {
        "orig_size": f"{orig_w}x{orig_h}",
        "crop_size": f"{crop_w}x{crop_h}",
        "sent_size": f"{sent_w}x{sent_h}",
        "scale": sent_w / crop_w,
        "orig_mpx": orig_w * orig_h / 1_000_000,
    }

    return buffer.getvalue(), info


def load_image(
    image_path: Path,
    cache_dir: Path | None
) -> tuple[bytes, dict, bool]:
    """
    Load the resized image from the cache if available,
    otherwise create it.
    """

    if cache_dir is not None:

        key = cache_key(image_path)

        jpg_file = cache_dir / f"{key}.jpg"
        info_file = cache_dir / f"{key}.txt"

        if jpg_file.exists() and info_file.exists():

            orig, crop, sent, scale, mpx = (
                info_file.read_text().split(";")
            )

            info = {
                "orig_size": orig,
                "crop_size": crop,
                "sent_size": sent,
                "scale": float(scale),
                "orig_mpx": float(mpx),
            }

            return jpg_file.read_bytes(), info, True


    jpeg_bytes, info = prepare_image(image_path)


    if cache_dir is not None:

        jpg_file.write_bytes(jpeg_bytes)

        info_file.write_text(
            ";".join(
                [
                    info["orig_size"],
                    info["crop_size"],
                    info["sent_size"],
                    str(info["scale"]),
                    str(info["orig_mpx"]),
                ]
            )
        )


    return jpeg_bytes, info, False


def clean_answer(text: str) -> str:
    """
    Remove possible <think> blocks,
    quotation marks and line breaks.
    """

    if text is None:
        return ""

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL
    )

    text = text.strip().strip('"').strip("'").strip()

    # Replace line breaks / repeated whitespace with one space
    text = " ".join(text.split())

    return text


def log_print(msg: str):

    with print_lock:
        print(msg, flush=True)


def parse_metadata(text: str) -> Metadata:
    """
    Extract the JSON object from the model answer
    and validate it against the Metadata model.
    """

    if text is None:
        text = ""

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL
    )

    # Tolerate ```json fences or text around the object
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end < start:
        raise ValueError(
            f"No JSON object in answer: {text.strip()[:200]!r}"
        )

    # strict=False: allow raw line breaks inside strings
    # (multi-line titles on the plan)
    metadata = Metadata.model_validate(
        json.loads(text[start:end + 1], strict=False)
    )

    # Same whitespace cleanup as clean_answer; empty strings -> None
    for field in Metadata.model_fields:

        value = getattr(metadata, field)

        if value is not None:
            value = " ".join(value.split()) or None
            setattr(metadata, field, value)

    return metadata


def build_request(
    messages: list,
    max_tokens: int,
    thinking,
    response_format: dict | None = None
) -> dict:
    """
    Build the shared request parameters.
    """

    params = {
        "model": MODEL,
        "messages": messages,
        "seed": SEED,
    }


    if response_format is not None:
        params["response_format"] = response_format


    if max_tokens is not None:
        params["max_tokens"] = max_tokens


    if thinking is not None:

        params["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": thinking
            }
        }


    # Qwen recommends temperature 0.6 when Thinking is enabled.
    # With temperature 0, the model may get stuck in repetitive
    # reasoning loops, causing very long runtimes.
    #
    # Without Thinking: temperature 0 + top_p 1 (greedy decoding)
    # so that the same image always gives the same answer.

    params["temperature"] = (
        0 if thinking is False else 0.6
    )

    params["top_p"] = 1


    return params


def token_entry(t) -> tuple:
    """(token, logprob, alternatives) from one logprobs entry."""

    return (
        t.token,
        t.logprob,
        [
            (a.token, a.logprob)
            for a in (t.top_logprobs or [])
        ]
    )


def run_request(
    params: dict,
    label: str
) -> tuple[str, str, dict]:
    """
    Execute a request with or without streaming.

    Returns:
        response_text,
        finish_reason,
        statistics
    """

    stats = {
        "first_token_s": None,
        "reasoning_chunks": 0,
        "content_chunks": 0,
        # [(token, logprob, [(alt_token, alt_logprob), ...]), ...]
        # if params contain logprobs=True
        "logprobs": [],
    }

    t0 = time.perf_counter()


    # --------------------------------------------------------
    # NON-STREAMING
    # --------------------------------------------------------

    if not USE_STREAMING:

        response = client.chat.completions.create(**params)

        choice = response.choices[0]

        stats["first_token_s"] = (
            time.perf_counter() - t0
        )

        if choice.logprobs and choice.logprobs.content:

            stats["logprobs"] = [
                token_entry(t)
                for t in choice.logprobs.content
            ]

        return (
            choice.message.content or "",
            choice.finish_reason,
            stats
        )


    # --------------------------------------------------------
    # STREAMING
    # --------------------------------------------------------

    stream = client.chat.completions.create(
        **params,
        stream=True
    )

    parts = []

    finish_reason = None

    last_report = t0


    for chunk in stream:

        if not chunk.choices:
            continue


        choice = chunk.choices[0]

        delta = choice.delta


        # Depending on the server, reasoning may appear in:
        #
        # reasoning_content
        # reasoning
        #
        # or directly inside content as <think>...</think>

        reasoning = (
            getattr(delta, "reasoning_content", None)
            or getattr(delta, "reasoning", None)
        )

        content = delta.content


        if (
            (reasoning or content)
            and stats["first_token_s"] is None
        ):

            stats["first_token_s"] = (
                time.perf_counter() - t0
            )

            log_print(
                f"  -> {label}: first response after "
                f"{stats['first_token_s']:.1f}s"
            )


        if reasoning:
            stats["reasoning_chunks"] += 1


        if content:

            stats["content_chunks"] += 1

            parts.append(content)


        if choice.logprobs and choice.logprobs.content:

            stats["logprobs"].extend(
                token_entry(t)
                for t in choice.logprobs.content
            )


        if choice.finish_reason:
            finish_reason = choice.finish_reason


        now = time.perf_counter()


        if now - last_report >= PROGRESS_INTERVAL:

            last_report = now

            log_print(
                f"  .. {label}: {now - t0:.0f}s, "
                f"{stats['reasoning_chunks'] + stats['content_chunks']} "
                f"tokens received"
            )


    return "".join(parts), finish_reason, stats


def field_probability(
    token_logprobs: list,
    field: str
) -> float | None:
    """
    Probability of the least certain token of a JSON string value
    (e.g. field="title") in the model answer.

    None if the field is null / empty or not in the answer.
    """

    # Rebuild the answer from the tokens and remember
    # which characters belong to which token.
    text = "".join(
        token
        for token, _, _ in token_logprobs
    )

    spans = []

    pos = 0

    for token, logprob, alternatives in token_logprobs:

        # Probability that the model produces the same text here:
        # the chosen token plus every alternative that is only a
        # different split of the same text (" Abort" vs " Ab"+"ort").
        rest = text[pos:]

        same_text = {
            alt_token: alt_logprob
            for alt_token, alt_logprob in alternatives
            if alt_token and rest.startswith(alt_token)
        }

        same_text[token] = logprob

        probability = min(
            1.0,
            sum(math.exp(lp) for lp in same_text.values())
        )

        spans.append(
            (pos, pos + len(token), probability)
        )

        pos += len(token)


    # Last match, in case reasoning tokens come first
    matches = list(
        re.finditer(
            rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"',
            text
        )
    )

    if not matches:
        return None

    start, end = matches[-1].span(1)


    # Every token that overlaps the value
    probabilities = [
        probability
        for a, b, probability in spans
        if a < end and b > start
    ]

    if not probabilities:
        return None

    return min(probabilities)


def rate_field(
    metadata: Metadata,
    token_logprobs: list,
    field: str
) -> Confidence | None:
    """
    Traffic light for one Metadata field
    (see CONFIDENCE_GREEN / _YELLOW).

    None if the server returned no logprobs.
    """

    if not token_logprobs:
        return None


    if getattr(metadata, field) is None:

        return Confidence(level=TrafficLight.RED)


    probability = field_probability(
        token_logprobs,
        field
    )

    if probability is None:
        return None


    if probability >= CONFIDENCE_GREEN:
        level = TrafficLight.GREEN

    elif probability >= CONFIDENCE_YELLOW:
        level = TrafficLight.YELLOW

    else:
        level = TrafficLight.RED


    return Confidence(
        level=level,
        probability=round(probability, 4)
    )


def ask_model(
    jpeg_bytes: bytes,
    label: str
) -> tuple[Metadata, dict[str, Confidence | None], dict]:
    """
    Send one image to the model and return
    (metadata, {field: confidence}, statistics).
    """

    image_base64 = base64.b64encode(
        jpeg_bytes
    ).decode("utf-8")


    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": PROMPT
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:image/jpeg;base64,"
                            f"{image_base64}"
                        )
                    },
                },
            ],
        }
    ]


    response_format = None

    if USE_JSON_SCHEMA:

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "Metadata",
                "schema": Metadata.model_json_schema(),
                "strict": True,
            },
        }


    params = build_request(
        messages,
        MAX_TOKENS,
        ENABLE_THINKING,
        response_format
    )

    # Token probabilities for the traffic lights
    params["logprobs"] = True

    params["top_logprobs"] = TOP_LOGPROBS


    text, finish_reason, stats = run_request(
        params,
        label
    )


    if finish_reason == "length":

        raise RuntimeError(
            f"Response was cut off after "
            f"{MAX_TOKENS or 'server maximum'} tokens - "
            f"increase MAX_TOKENS"
        )


    metadata = parse_metadata(text)


    confidences = {
        field: rate_field(metadata, stats["logprobs"], field)
        for field in Metadata.model_fields
    }


    return metadata, confidences, stats


def connection_test() -> bool:
    """
    Send a short request without an image
    to test the server and model.
    """

    print(
        "Connection test "
        "(without image, without Thinking)...",
        flush=True
    )


    t0 = time.perf_counter()


    try:

        params = build_request(
            [
                {
                    "role": "user",
                    "content": "Answer only with the word OK."
                }
            ],
            20,
            False
        )


        text, _, _ = run_request(
            params,
            "Test"
        )


        print(
            f"  Response: {clean_answer(text)!r} "
            f"after {time.perf_counter() - t0:.1f}s\n"
        )


        return True


    except Exception as e:

        print(
            f"  ERROR after "
            f"{time.perf_counter() - t0:.1f}s: "
            f"{type(e).__name__}: {e}"
        )

        print(
            "  -> Check server, BASE_URL, "
            "API_KEY or MODEL.\n"
        )

        return False


# ============================================================
# PROCESS ONE IMAGE
# ============================================================

CSV_FIELDS = [
    "Filename",
    "Location",
    "Location_confidence",
    "Location_probability",
    "Title",
    "Title_confidence",
    "Title_probability",
    "Date",
    "Date_confidence",
    "Date_probability",
    "Status",
    "Original_size_px",
    "Original_size_MP",
    "Crop_size_px",
    "Sent_size_px",
    "Scale_factor",
    "Scale_percent",
    "Sent_KB",
    "From_cache",
    "Preparation_time_s",
    "First_response_time_s",
    "Model_time_s",
    "Total_time_s",
]


TRAFFIC_LIGHT_SYMBOLS = {
    TrafficLight.GREEN: "🟢",
    TrafficLight.YELLOW: "🟡",
    TrafficLight.RED: "🔴",
}


def confidence_symbol(confidence: Confidence | None) -> str:
    """Traffic light + probability for the console, e.g. '🟡 59%'."""

    if confidence is None:
        return "(no logprobs from server)"

    text = TRAFFIC_LIGHT_SYMBOLS[confidence.level]

    if confidence.probability is not None:
        text += f" {confidence.probability:.0%}"

    return text


def process_image(
    image_path: Path,
    cache_dir: Path | None
) -> dict:

    row = {
        field: ""
        for field in CSV_FIELDS
    }

    row["Filename"] = image_path.name

    log = [image_path.name]

    t_prep = t_model = 0.0

    t0 = time.perf_counter()


    try:

        # Step 1:
        # Load image, optionally crop it,
        # resize it, or load it from cache.

        jpeg_bytes, info, from_cache = load_image(
            image_path,
            cache_dir
        )

        t_prep = (
            time.perf_counter() - t0
        )

        kb = len(jpeg_bytes) / 1024


        row.update(
            {
                "Original_size_px": info["orig_size"],
                "Original_size_MP": fmt(
                    info["orig_mpx"],
                    1
                ),
                "Crop_size_px": info["crop_size"],
                "Sent_size_px": info["sent_size"],
                "Scale_factor": fmt(
                    info["scale"],
                    4
                ),
                "Scale_percent": fmt(
                    info["scale"] * 100,
                    1
                ),
                "Sent_KB": fmt(
                    kb,
                    0
                ),
                "From_cache": (
                    "yes"
                    if from_cache
                    else "no"
                ),
            }
        )


        log.append(
            f"    {info['orig_size']} "
            f"-> {info['sent_size']} "
            f"(factor {info['scale']:.3f}, "
            f"{kb:.0f} KB"
            f"{', from cache' if from_cache else ''})"
        )


        # Step 2:
        # Send the request to the model.

        log_print(
            f"  >> {image_path.name}: "
            f"sent to model "
            f"({info['sent_size']}, "
            f"{kb:.0f} KB)"
        )


        t1 = time.perf_counter()


        metadata, confidences, stats = ask_model(
            jpeg_bytes,
            image_path.name
        )


        t_model = (
            time.perf_counter() - t1
        )


        if stats["first_token_s"] is not None:

            row["First_response_time_s"] = fmt(
                stats["first_token_s"]
            )


        # "location" -> columns Location, Location_confidence,
        # Location_probability (same for title and date)
        for field, confidence in confidences.items():

            column = field.capitalize()

            row[column] = getattr(metadata, field) or ""

            if confidence is not None:

                row[f"{column}_confidence"] = (
                    confidence.level.value
                )

                if confidence.probability is not None:

                    row[f"{column}_probability"] = fmt(
                        confidence.probability,
                        4
                    )


            log.append(
                f"    {column}: {getattr(metadata, field)}  "
                f"{confidence_symbol(confidence)}"
            )


        row["Status"] = "OK"

        row["_image_data"] = ImageData(
            filename=image_path.name,
            metadata=metadata,
            location_confidence=confidences["location"],
            title_confidence=confidences["title"],
            date_confidence=confidences["date"]
        )


    except Exception as e:

        if t_prep == 0.0:

            t_prep = (
                time.perf_counter() - t0
            )

        else:

            t_model = (
                time.perf_counter()
                - t0
                - t_prep
            )


        row["Status"] = (
            f"ERROR "
            f"({type(e).__name__}): {e}"
        )


        log.append(
            f"    {row['Status']}"
        )


    t_total = (
        time.perf_counter() - t0
    )


    row["Preparation_time_s"] = fmt(
        t_prep
    )

    row["Model_time_s"] = fmt(
        t_model
    )

    row["Total_time_s"] = fmt(
        t_total
    )


    log.append(
        f"    Time: "
        f"{t_prep:.2f}s preparation + "
        f"{t_model:.2f}s model "
        f"= {t_total:.2f}s"
    )


    row["_t_prep"] = t_prep

    row["_t_model"] = t_model

    row["_log"] = "\n".join(log)


    return row


# ============================================================
# MAIN
# ============================================================

def main():

    folder = Path(
        input(
            "Path to image folder: "
        ).strip().strip('"')
    )


    if not folder.is_dir():

        print(
            f"Folder not found: {folder}"
        )

        return


    images = sorted(
        p
        for p in folder.iterdir()
        if (
            p.is_file()
            and p.suffix.lower()
            in IMAGE_EXTENSIONS
        )
    )


    if not images:

        print(
            "No images found in the folder."
        )

        return


    if CONNECTION_TEST and not connection_test():

        return


    cache_dir = None


    if USE_CACHE:

        cache_dir = (
            folder / CACHE_DIRNAME
        )

        cache_dir.mkdir(
            exist_ok=True
        )


    print(
        f"\n{len(images)} images found. "
        f"Starting analysis..."
    )


    print(
        f"MAX_SIDE={MAX_SIDE}, "
        f"CROP_BOX={CROP_BOX}, "
        f"MAX_WORKERS={MAX_WORKERS}, "
        f"ENABLE_THINKING={ENABLE_THINKING}, "
        f"TIMEOUT={REQUEST_TIMEOUT}s, "
        f"USE_CACHE={USE_CACHE}\n"
    )


    results = []

    run_start = (
        time.perf_counter()
    )


    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as pool:

        futures = [
            pool.submit(
                process_image,
                p,
                cache_dir
            )
            for p in images
        ]


        for done, future in enumerate(
            as_completed(futures),
            start=1
        ):

            row = future.result()

            results.append(row)


            log_print(
                f"\n[{done}/{len(images)}] "
                f"{row['_log']}\n"
            )


    run_total = (
        time.perf_counter()
        - run_start
    )


    # Sort again by filename because threads
    # may finish in a different order.

    results.sort(
        key=lambda r: r["Filename"]
    )


    # ========================================================
    # WRITE CSV
    # ========================================================

    csv_path = (
        folder / CSV_FILENAME
    )


    # UTF-8-SIG + semicolon so Excel correctly
    # recognizes special characters and columns.

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
            delimiter=";",
            extrasaction="ignore"
        )


        writer.writeheader()

        writer.writerows(results)


    # ========================================================
    # WRITE JSON (list of ImageData, only successful images)
    # ========================================================

    json_path = (
        folder / JSON_FILENAME
    )

    image_data = [
        r["_image_data"].model_dump()
        for r in results
        if "_image_data" in r
    ]

    json_path.write_text(
        json.dumps(
            image_data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


    ok_count = sum(
        1
        for r in results
        if r["Status"] == "OK"
    )


    sum_prep = sum(
        r["_t_prep"]
        for r in results
    )


    sum_model = sum(
        r["_t_model"]
        for r in results
    )


    print("=" * 60)


    print(
        f"Finished! "
        f"{ok_count}/{len(results)} successful"
    )


    for field in Metadata.model_fields:

        column = field.capitalize()

        print(
            f"{column + ' confidence:':22}"
            + "  ".join(
                f"{symbol} {sum(1 for r in results if r[f'{column}_confidence'] == level.value)}"
                for level, symbol in TRAFFIC_LIGHT_SYMBOLS.items()
            )
        )


    print(
        f"Total wall-clock time: "
        f"{run_total:.1f}s  |  "
        f"{run_total / len(results):.1f}s "
        f"per image"
    )


    print(
        f"Total preparation time: "
        f"{sum_prep:.1f}s  |  "
        f"Total model time: "
        f"{sum_model:.1f}s"
    )


    print(
        f"Results saved to: "
        f"{csv_path}\n"
        f"                  "
        f"{json_path}"
    )


    print("=" * 60)


if __name__ == "__main__":
    main()