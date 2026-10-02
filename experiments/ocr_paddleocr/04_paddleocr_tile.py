import cv2
import json
import numpy as np
from math import ceil, log
from pathlib import Path
from time import perf_counter
from typing import Any

from paddleocr import PaddleOCR
from paddleocr import DocImgOrientationClassification, PaddleOCR

SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_PATH = SCRIPT_DIR / "00000018.TIF"
OUTPUT_DIR = SCRIPT_DIR / "paddle_output"
TILE_OUTPUT_DIR = OUTPUT_DIR / "tiles"
ORIENTATION_JSON_PATH = OUTPUT_DIR / "orientation_result.json"
ORIENTED_IMAGE_PATH = OUTPUT_DIR / "oriented_input.png"

ORIENTATION_MIN_SCORE = 0.70
MAX_TILES = 12
OVERLAP_X = 200
OVERLAP_Y = 200


def create_orientation_model() -> DocImgOrientationClassification:
    """Create the document orientation classification model."""

    return DocImgOrientationClassification(
        model_name="PP-LCNet_x1_0_doc_ori",
    )

def determine_orientation(
    model: DocImgOrientationClassification,
    image: np.ndarray,
) -> tuple[int, float]:
    """Determine the correction angle for the complete document image."""

    results = model.predict(
        input=image,
        batch_size=1,
    )

    result_list = list(results)

    if not result_list:
        raise RuntimeError(
            "The orientation model returned no result."
        )

    result = result_list[0]

    # Saving to an explicit filename makes the result easy to inspect
    # and avoids depending on internal Result-object attributes.
    result.save_to_json(str(ORIENTATION_JSON_PATH))

    with ORIENTATION_JSON_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    orientation_data = payload.get("res", payload)

    labels = orientation_data.get("label_names", [])
    scores = orientation_data.get("scores", [])

    if not labels:
        raise RuntimeError(
            "The orientation result contains no label_names."
        )

    if not scores:
        raise RuntimeError(
            "The orientation result contains no confidence scores."
        )

    angle = int(labels[0])
    score = float(scores[0])

    if angle not in {0, 90, 180, 270}:
        raise RuntimeError(
            f"Unsupported orientation angle: {angle}"
        )

    return angle, score



def rotate_image_clockwise(
    image: np.ndarray,
    angle: int,
) -> np.ndarray:
    """Rotate the complete document clockwise by the correction angle."""

    if angle == 0:
        return image.copy()

    if angle == 90:
        return cv2.rotate(
            image,
            cv2.ROTATE_90_CLOCKWISE,
        )

    if angle == 180:
        return cv2.rotate(
            image,
            cv2.ROTATE_180,
        )

    if angle == 270:
        return cv2.rotate(
            image,
            cv2.ROTATE_90_COUNTERCLOCKWISE,
        )

    raise ValueError(
        f"Unsupported rotation angle: {angle}"
    )
def orient_document(
    model: DocImgOrientationClassification,
    image: np.ndarray,
) -> tuple[np.ndarray, int, float]:
    """Determine and correct the orientation of the full document."""

    angle, score = determine_orientation(
        model=model,
        image=image,
    )

    print(
        f"Detected document orientation: "
        f"{angle}° (confidence={score:.4f})"
    )

    if score < ORIENTATION_MIN_SCORE:
        raise RuntimeError(
            "Document orientation confidence is too low: "
            f"{score:.4f} < {ORIENTATION_MIN_SCORE:.2f}"
        )

    oriented_image = rotate_image_clockwise(
        image=image,
        angle=angle,
    )

    success = cv2.imwrite(
        str(ORIENTED_IMAGE_PATH),
        oriented_image,
    )

    if not success:
        raise RuntimeError(
            f"Could not save oriented image: "
            f"{ORIENTED_IMAGE_PATH}"
        )

    return oriented_image, angle, score

def create_ocr_pipeline() -> PaddleOCR:
    """Create the OCR pipeline for already oriented tiles."""

    return PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

def load_image(image_path: Path) -> np.ndarray:
    """Load an image in color or report a useful file error."""

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    return image


def result_data(result: Any) -> dict[str, Any]:
    """Extract PaddleOCR's serializable result dictionary."""

    data = result.json
    if isinstance(data, str):
        data = json.loads(data)
    return data.get("res", data)


def tile_starts(length: int, tile_size: int, overlap: int) -> list[int]:
    """Return tile offsets that cover an axis, including its far edge."""

    if length <= tile_size:
        return [0]

    stride = tile_size - overlap
    starts = list(range(0, length - tile_size + 1, stride))
    last_start = length - tile_size
    if starts[-1] != last_start:
        starts.append(last_start)
    return starts


def choose_tile_layout(
    image_width: int,
    image_height: int,
) -> tuple[int, int, list[int], list[int]]:
    """Choose a near-square layout using no more than MAX_TILES tiles."""

    candidates = []
    for columns in range(1, MAX_TILES + 1):
        if MAX_TILES % columns:
            continue
        rows = MAX_TILES // columns
        tile_width = ceil(
            (image_width + OVERLAP_X * (columns - 1)) / columns
        )
        tile_height = ceil(
            (image_height + OVERLAP_Y * (rows - 1)) / rows
        )
        x_starts = tile_starts(image_width, tile_width, OVERLAP_X)
        y_starts = tile_starts(image_height, tile_height, OVERLAP_Y)
        tile_count = len(x_starts) * len(y_starts)
        aspect_difference = abs(log(tile_width / tile_height))
        candidates.append(
            (
                aspect_difference,
                -tile_count,
                tile_width,
                tile_height,
                x_starts,
                y_starts,
            )
        )

    _, _, tile_width, tile_height, x_starts, y_starts = min(candidates)
    return tile_width, tile_height, x_starts, y_starts


def process_tiles(
    ocr: PaddleOCR,
    image: np.ndarray,
    orientation_angle: int,
    orientation_score: float,
) -> tuple[list[dict[str, Any]], int, int, int]:
    """Run OCR on overlapping tiles and translate polygons to image space."""

    image_height, image_width = image.shape[:2]
    tile_width, tile_height, x_starts, y_starts = choose_tile_layout(
        image_width=image_width,
        image_height=image_height,
    )
    total_tiles = len(x_starts) * len(y_starts)
    entries: list[dict[str, Any]] = []
    tile_index = 0
    print(
        f"Processing {total_tiles} tiles at up to {tile_width}x{tile_height} px.",
        flush=True,
    )

    for tile_path in TILE_OUTPUT_DIR.glob("tile_*.png"):
        try:
            old_index = int(tile_path.stem.removeprefix("tile_"))
        except ValueError:
            continue
        if old_index >= total_tiles:
            tile_path.unlink()

    save_merged_json(
        entries=[],
        image=image,
        tile_count=total_tiles,
        tiles_completed=0,
        tile_width=tile_width,
        tile_height=tile_height,
        orientation_angle=orientation_angle,
        orientation_score=orientation_score,
    )

    for y in y_starts:
        for x in x_starts:
            tile_started = perf_counter()
            print(
                f"Tile {tile_index + 1}/{total_tiles}: "
                f"position=({x}, {y}); saving tile...",
                flush=True,
            )
            tile = image[y:min(y + tile_height, image_height),
                         x:min(x + tile_width, image_width)]
            tile_path = TILE_OUTPUT_DIR / f"tile_{tile_index:04d}.png"
            if not cv2.imwrite(str(tile_path), tile):
                raise OSError(f"Could not save tile image: {tile_path}")

            inference_started = perf_counter()
            print(
                f"Tile {tile_index + 1}/{total_tiles}: running OCR...",
                flush=True,
            )
            for result in ocr.predict(input=tile):
                data = result_data(result)
                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])
                polygons = data.get("rec_polys", data.get("dt_polys", []))

                for text, score, polygon in zip(texts, scores, polygons):
                    points = np.asarray(polygon, dtype=float).reshape(-1, 2)
                    points[:, 0] += x
                    points[:, 1] += y
                    entries.append(
                        {
                            "text": str(text),
                            "confidence": float(score),
                            "polygon": points.tolist(),
                            "tile_index": tile_index,
                        }
                    )

            print(
                f"Tile {tile_index + 1}/{total_tiles}: OCR finished in "
                f"{perf_counter() - inference_started:.1f}s; "
                f"{len(entries)} detections total "
                f"({perf_counter() - tile_started:.1f}s including save).",
                flush=True,
            )
            tile_index += 1
            save_merged_json(
                entries=merge_duplicate_entries(entries),
                image=image,
                tile_count=total_tiles,
                tiles_completed=tile_index,
                tile_width=tile_width,
                tile_height=tile_height,
                orientation_angle=orientation_angle,
                orientation_score=orientation_score,
            )
            print(
                f"Updated merged_result.json "
                f"({tile_index}/{total_tiles} tiles complete).",
                flush=True,
            )

    return entries, tile_index, tile_width, tile_height


def polygon_iou(first: list[list[float]], second: list[list[float]]) -> float:
    """Calculate bounding-box intersection over union for two polygons."""

    first_points = np.asarray(first, dtype=float)
    second_points = np.asarray(second, dtype=float)
    first_min = first_points.min(axis=0)
    first_max = first_points.max(axis=0)
    second_min = second_points.min(axis=0)
    second_max = second_points.max(axis=0)

    intersection_min = np.maximum(first_min, second_min)
    intersection_max = np.minimum(first_max, second_max)
    intersection_size = np.maximum(intersection_max - intersection_min, 0)
    intersection_area = float(intersection_size[0] * intersection_size[1])
    first_area = float(np.prod(np.maximum(first_max - first_min, 0)))
    second_area = float(np.prod(np.maximum(second_max - second_min, 0)))
    union_area = first_area + second_area - intersection_area
    return intersection_area / union_area if union_area else 0.0


def merge_duplicate_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the higher-confidence copy of overlapping duplicate detections."""

    merged: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: item["confidence"], reverse=True):
        normalized_text = entry["text"].strip().casefold()
        duplicate = any(
            normalized_text == existing["text"].strip().casefold()
            and polygon_iou(entry["polygon"], existing["polygon"]) >= 0.5
            for existing in merged
        )
        if not duplicate:
            merged.append(entry)
    return merged


def save_merged_visualization(
    image: np.ndarray,
    entries: list[dict[str, Any]],
) -> Path:
    """Save the merged detections overlaid on the oriented source image."""

    visualization = image.copy()
    for entry in entries:
        polygon = np.asarray(entry["polygon"], dtype=np.int32)
        cv2.polylines(visualization, [polygon], True, (0, 180, 0), 2)
        x, y = polygon[0]
        cv2.putText(
            visualization,
            entry["text"],
            (int(x), max(int(y) - 5, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )

    output_path = OUTPUT_DIR / "merged_visualization.png"
    if not cv2.imwrite(str(output_path), visualization):
        raise OSError(f"Could not save visualization: {output_path}")
    return output_path


def save_merged_json(
    entries: list[dict],
    image: np.ndarray,
    tile_count: int,
    tiles_completed: int,
    tile_width: int,
    tile_height: int,
    orientation_angle: int,
    orientation_score: float,
) -> Path:
    """Write the combined OCR result."""

    output_path = OUTPUT_DIR / "merged_result.json"

    image_height, image_width = image.shape[:2]

    payload = {
        "input_path": str(IMAGE_PATH),
        "coordinate_system": "oriented_image",
        "oriented_image_path": str(ORIENTED_IMAGE_PATH),
        "orientation": {
            "correction_angle_clockwise": orientation_angle,
            "confidence": orientation_score,
        },
        "image_width": image_width,
        "image_height": image_height,
        "tile_width": tile_width,
        "tile_height": tile_height,
        "overlap_x": OVERLAP_X,
        "overlap_y": OVERLAP_Y,
        "tile_count": tile_count,
        "tiles_completed": tiles_completed,
        "recognition_count": len(entries),
        "results": entries,
    }

    temporary_path = output_path.with_suffix(".json.tmp")
    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )
    temporary_path.replace(output_path)

    return output_path

def main() -> None:
    """Orient the document, run tiled OCR and export the results."""

    OUTPUT_DIR.mkdir(exist_ok=True)
    TILE_OUTPUT_DIR.mkdir(exist_ok=True)

    original_image = load_image(IMAGE_PATH)

    orientation_model = create_orientation_model()

    oriented_image, orientation_angle, orientation_score = (
        orient_document(
            model=orientation_model,
            image=original_image,
        )
    )

    ocr = create_ocr_pipeline()

    raw_entries, tile_count, tile_width, tile_height = process_tiles(
        ocr=ocr,
        image=oriented_image,
        orientation_angle=orientation_angle,
        orientation_score=orientation_score,
    )

    merged_entries = merge_duplicate_entries(raw_entries)

    merged_json_path = save_merged_json(
        entries=merged_entries,
        image=oriented_image,
        tile_count=tile_count,
        tiles_completed=tile_count,
        tile_width=tile_width,
        tile_height=tile_height,
        orientation_angle=orientation_angle,
        orientation_score=orientation_score,
    )

    merged_image_path = save_merged_visualization(
        image=oriented_image,
        entries=merged_entries,
    )

    print()
    print(f"Orientation angle: {orientation_angle}°")
    print(f"Orientation confidence: {orientation_score:.4f}")
    print(f"Processed tiles: {tile_count}")
    print(f"Raw detections: {len(raw_entries)}")
    print(f"Merged detections: {len(merged_entries)}")
    print(f"Saved oriented image to: {ORIENTED_IMAGE_PATH}")
    print(f"Saved merged JSON to: {merged_json_path}")
    print(f"Saved visualization to: {merged_image_path}")


if __name__ == "__main__":
    main()
