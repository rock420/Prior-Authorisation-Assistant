"""Provider tools backed by mock JSON data."""

import json
from pathlib import Path

from ..models.core import ProviderInfo

_DATA_DIR = Path(__file__).parent / "mock_data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


def get_provider_details() -> ProviderInfo:
    """
    Get provider details
    """
    provider = _load_json("providers.json")

    return ProviderInfo(
        provider_id=provider["provider_id"],
        npi=provider["npi"],
        name=provider["name"],
        organization=provider["organization"],
        phone=provider["phone"],
        email=provider.get("email"),
        address=provider["address"],
        license_number=provider["license_number"],
    )
