
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

MODEL_DIR = PROJECT_DIR / "assets" / "master_models"
MODEL_DATA_FILE = PROJECT_DIR / "data" / "master_models.json"

ALLOWED_MODELS = {
    "WW-CHAR-01": "Female Model 01",
    "WW-CHAR-02": "Female Model 02",
    "WW-CHAR-03": "Male Model 01",
}


def load_models() -> list[dict]:
    """Load registered model profiles from local JSON storage."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not MODEL_DATA_FILE.exists():
        return []

    try:
        data = json.loads(MODEL_DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Model library JSON contains invalid data.") from exc

    if not isinstance(data, list):
        raise ValueError("Model library must contain a JSON list.")

    return data


def save_model(
    model_id: str,
    display_name: str,
    identity_notes: str,
    hair_rules: str,
    image_bytes: bytes,
    image_extension: str = ".png",
) -> dict:
    """Save a model reference and its profile."""
    if model_id not in ALLOWED_MODELS:
        raise ValueError("Unknown model ID.")

    if not display_name.strip():
        raise ValueError("Display name cannot be empty.")

    if not image_bytes:
        raise ValueError("Please upload a reference image.")

    extension = image_extension.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Use a PNG, JPG, JPEG, or WEBP image.")

    models = load_models()

    # One profile per model ID. Re-uploading updates that profile.
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    image_path = MODEL_DIR / f"{model_id}{extension}"

    # Remove an older image with a different extension for this ID.
    for old_path in MODEL_DIR.glob(f"{model_id}.*"):
        if old_path != image_path and old_path.is_file():
            old_path.unlink()

    image_path.write_bytes(image_bytes)

    profile = {
        "model_id": model_id,
        "display_name": display_name.strip(),
        "identity_notes": identity_notes.strip(),
        "hair_rules": hair_rules.strip(),
        "reference_image": str(image_path.relative_to(PROJECT_DIR)),
        "approval_status": "PENDING_APPROVAL",
        "created_or_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    existing_index = next(
        (
            index
            for index, item in enumerate(models)
            if item.get("model_id") == model_id
        ),
        None,
    )

    if existing_index is None:
        models.append(profile)
    else:
        # Preserve the original creation timestamp on updates.
        profile["created_or_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        models[existing_index] = profile

    temporary_path = MODEL_DATA_FILE.with_suffix(".tmp")

    try:
        temporary_path.write_text(
            json.dumps(models, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(MODEL_DATA_FILE)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return profile


def set_model_approval(model_id: str, approved: bool) -> dict:
    """Approve or return a registered model to pending status."""
    models = load_models()

    for profile in models:
        if profile.get("model_id") == model_id:
            profile["approval_status"] = (
                "APPROVED" if approved else "PENDING_APPROVAL"
            )
            profile["approval_updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            temporary_path = MODEL_DATA_FILE.with_suffix(".tmp")
            try:
                temporary_path.write_text(
                    json.dumps(models, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary_path.replace(MODEL_DATA_FILE)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

        
            return profile

    raise ValueError("Model not found in the library.")
