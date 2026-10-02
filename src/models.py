"""
Data model for the information extracted from each plan image (v8+).

    ImageData
    ├── filename            : str
    ├── metadata            : Metadata            what the model read
    │                         ├── location : str | None
    │                         └── title    : str | None
    ├── location_confidence : Confidence | None   traffic light of the model
    ├── title_confidence    : Confidence | None
    ├── error               : str | None          entry kept + flagged red
    ├── analysis            : Analysis | None     which script, when, which file version (v10+)
    └── review              : Review | None       human review
                              ├── location, title             confirmed / corrected values
                              ├── location_level, title_level traffic light set by the reviewer
                              └── reviewed_at

    Confidence
    ├── level       : TrafficLight (green / yellow / red)
    └── probability : float | None

The model's values are never overwritten: a correction lives in
`review`, and value() / level() return the reviewed value if there is one.

The model only returns `Metadata` (its JSON schema is sent to the server
as the structured-output format). Everything else is added locally.

v5-v7 used a model with a date field: see models_v7.py.
"""

import unicodedata
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# Fields that are extracted, shown, searched and reviewed
FIELDS = ("location", "title")


class Metadata(BaseModel):

    # extra="forbid" -> "additionalProperties": false in the JSON schema,
    # required for strict structured output.
    model_config = ConfigDict(extra="forbid")

    location: str | None = Field(
        description=(
            "Place the plan refers to, usually the station name "
            "or street, exactly as written on the plan. null if not found."
        )
    )

    title: str | None = Field(
        description=(
            "Full title of the plan exactly as written on the plan. "
            "null if not found."
        )
    )


class TrafficLight(str, Enum):

    GREEN = "green"     # sure
    YELLOW = "yellow"   # check manually
    RED = "red"         # probably wrong or not found


# worst first
LEVEL_ORDER = [TrafficLight.RED, TrafficLight.YELLOW, TrafficLight.GREEN]


class Confidence(BaseModel):

    model_config = ConfigDict(extra="forbid")

    level: TrafficLight

    # Probability of the least certain token of the value (0-1).
    # None if the field was not found (-> level RED).
    probability: float | None = None


class Review(BaseModel):
    """
    Review by a human.

    location / title hold the value the reviewer confirmed or corrected
    ("" = not on the plan), so a new model version cannot silently change
    a confirmed value. None only in reviews saved by v8, which stored
    confirmed values as None (v9 fills them in, see pin_v8_reviews).
    """

    model_config = ConfigDict(extra="forbid")

    location: str | None = None

    title: str | None = None

    # Traffic light chosen by the reviewer
    location_level: TrafficLight | None = None

    title_level: TrafficLight | None = None

    # ISO timestamp
    reviewed_at: str | None = None


class Analysis(BaseModel):
    """Which script analysed which version of the file, and when (v10+)."""

    model_config = ConfigDict(extra="forbid")

    # e.g. "scan_plan_htw_api_v10.py"
    script: str

    # ISO timestamp
    at: str

    # Content hash of the file: detects a changed file even if the
    # modification time is unreliable (copied / moved folders)
    file_sha1: str

    # "size-mtime_ns": quick check, avoids hashing unchanged files
    file_stat: str


class ImageData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    filename: str

    metadata: Metadata

    # None if the server returned no logprobs
    location_confidence: Confidence | None = None

    title_confidence: Confidence | None = None

    # Error message if the image could not be analysed.
    # The entry is kept (all fields None) and flagged red.
    error: str | None = None

    analysis: Analysis | None = None

    review: Review | None = None


    def value(self, field: str) -> str | None:
        """Reviewed value if corrected, otherwise the model's value."""

        if self.review is not None and getattr(self.review, field) is not None:
            return getattr(self.review, field) or None

        return getattr(self.metadata, field)


    def level(self, field: str) -> TrafficLight | None:
        """Traffic light set by the reviewer, otherwise the model's."""

        if self.review is not None and getattr(self.review, f"{field}_level") is not None:
            return getattr(self.review, f"{field}_level")

        confidence = getattr(self, f"{field}_confidence")

        return confidence.level if confidence else None


    @property
    def overall_level(self) -> TrafficLight | None:
        """
        Worst traffic light of location and title.
        RED on an unreviewed error, None if a field has no rating.
        """

        if self.error and self.review is None:
            return TrafficLight.RED

        levels = [self.level(f) for f in FIELDS]

        if any(level is None for level in levels):
            return None

        return min(levels, key=LEVEL_ORDER.index)


    @property
    def review_status(self) -> str:
        """
        open / confirmed (reviewed, same as what the model read) /
        corrected (reviewed value differs from what the model read).
        """

        if self.review is None:
            return "open"

        for f in FIELDS:

            reviewed = getattr(self.review, f)

            if reviewed is not None and " ".join(reviewed.split()) != " ".join((getattr(self.metadata, f) or "").split()):
                return "corrected"

        return "confirmed"


    @property
    def filename_flags(self) -> list[str]:
        """
        Status notes written into the (German) filename by the archive,
        as English labels, e.g. "ungültig" -> "invalid".
        """

        # NFC: macOS often stores 'ü' decomposed as 'u' + '¨'
        name = unicodedata.normalize("NFC", self.filename).casefold()

        return [
            label
            for label, variants in FILENAME_FLAGS.items()
            if any(v in name for v in variants)
        ]


# English label shown in list / Excel -> German notes in filenames
FILENAME_FLAGS = {
    "invalid": ("ungültig", "ungueltig"),
    "superseded": ("überholt", "ueberholt"),
    "not realised": ("nicht realisiert", "nicht_realisiert"),
    "never built": ("nie gebaut", "nie_gebaut"),
}
