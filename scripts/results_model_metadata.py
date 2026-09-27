"""Publisher-sourced static result labels; never infer identity from spelling."""

from datetime import date
import json
from pathlib import Path


METADATA_PATH = Path(__file__).resolve().parents[1] / "data/model-metadata.json"


def load_model_metadata(path: Path = METADATA_PATH) -> dict[str, dict]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    date.fromisoformat(registry["verified_on"])
    aliases = {}
    for model, values in registry["models"].items():
        if values["model_type"] not in {"open", "closed"}:
            raise ValueError(f"{model}: model_type must be open or closed")
        release = values["release_date"]
        if release is not None:
            if date.fromisoformat(release).isoformat() != release:
                raise ValueError(f"{model}: release_date must be YYYY-MM-DD")
        elif not values["notes"] or values["release_source"] is not None:
            raise ValueError(f"{model}: an unknown release needs an explanation")
        for field in ("access_source", "release_source"):
            if field == "release_source" and release is None:
                continue
            if not str(values[field]).startswith("https://"):
                raise ValueError(f"{model}: {field} must be an HTTPS publisher source")
        metadata = {key: value for key, value in values.items() if key != "aliases"}
        verified_on = values.get("verified_on", registry["verified_on"])
        date.fromisoformat(verified_on)
        metadata.update(model=model, verified_on=verified_on)
        for alias in [model, *values["aliases"]]:
            if not alias.strip() or alias in aliases:
                raise ValueError(f"duplicate or empty model alias: {alias!r}")
            aliases[alias] = metadata
    return aliases


def require_model_metadata(metadata: dict[str, dict], model: str) -> dict:
    try:
        return metadata[model]
    except KeyError as exc:
        raise ValueError(
            f"{model}: missing reviewed model metadata; add publisher sources "
            "and an explicit name/alias to data/model-metadata.json"
        ) from exc
