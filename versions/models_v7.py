"""
FROZEN data model of v5-v7 (with date). Current model: models.py (v8+).

Data model for the information extracted from each plan image.

    ImageData
    ├── filename            : str
    ├── metadata            : Metadata
    │                         ├── location : str | None
    │                         ├── title    : str | None
    │                         └── date     : str | None
    ├── location_confidence : Confidence | None   (v6)
    ├── title_confidence    : Confidence | None   (v5, v6)
    ├── date_confidence     : Confidence | None   (v6)
    └── error               : str | None          (v7, entry kept + flagged)

    Confidence
    ├── level       : TrafficLight (green / yellow / red)
    └── probability : float | None

The model only returns `Metadata` (its JSON schema is sent to the server
as the structured-output format). `filename` is known locally and the
`*_confidence` fields are computed locally from the token probabilities
(logprobs) of the answer; all are added afterwards when building
`ImageData`.

Planned next step (not implemented yet):
these fields are extracted from every image and will later be
cleaned up / normalised and displayed (e.g. table, map, timeline).
"""

import unicodedata
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    date: str | None = Field(
        description=(
            "Date of the plan in ISO format: YYYY-MM-DD, YYYY-MM or YYYY "
            "depending on the precision on the plan. null if not found."
        )
    )


class TrafficLight(str, Enum):

    GREEN = "green"     # model is sure
    YELLOW = "yellow"   # check manually
    RED = "red"         # probably wrong or not found


class Confidence(BaseModel):

    model_config = ConfigDict(extra="forbid")

    level: TrafficLight

    # Probability of the least certain token of the value (0-1).
    # None if the field was not found (-> level RED).
    probability: float | None = None


class ImageData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    filename: str

    metadata: Metadata

    # None if the server returned no logprobs
    # (or, for location/date, when written by v5)
    location_confidence: Confidence | None = None

    title_confidence: Confidence | None = None

    date_confidence: Confidence | None = None

    # v7: error message if the image could not be analysed.
    # The entry is kept (all fields None) and flagged red.
    error: str | None = None


    @property
    def overall_level(self) -> TrafficLight | None:
        """
        Worst traffic light of the searchable fields (location, title).
        RED on error, None if there are no confidences (no logprobs).
        """

        if self.error:
            return TrafficLight.RED

        confidences = [self.location_confidence, self.title_confidence]

        if any(c is None for c in confidences):
            return None

        order = [TrafficLight.RED, TrafficLight.YELLOW, TrafficLight.GREEN]

        return min(
            (c.level for c in confidences),
            key=order.index
        )


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
