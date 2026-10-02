from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os
import base64
import mimetypes

# ============================================================
# SETTINGS
# ============================================================

# HTW API key: read from the file .env in the project folder
# (see .env.example) - never write it into the code.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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


# ============================================================
# CONNECT TO HTW API
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


# ============================================================
# LOAD IMAGE
# ============================================================

image_path = input("Enter the path to your image: ").strip()

mime_type, _ = mimetypes.guess_type(image_path)

if mime_type is None:
    mime_type = "image/jpeg"

with open(image_path, "rb") as image_file:
    image_base64 = base64.b64encode(image_file.read()).decode("utf-8")


# ============================================================
# SEND IMAGE TO MODEL
# ============================================================

print("\nAnalyzing image...\n")

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "give me the Title of this plan"
                    ),
                },
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

# ============================================================
# PRINT RESULT
# ============================================================

print("=" * 60)
print("IMAGE DESCRIPTION")
print("=" * 60)

print(response.choices[0].message.content)