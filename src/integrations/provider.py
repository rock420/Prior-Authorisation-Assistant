"""Provider tools backed by mock JSON data."""

import json
from pathlib import Path

from ..models.core import ProviderInfo
from ..models.hitl import HITLTask, TaskType

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


def get_provider_details(provider_id: str) -> ProviderInfo:
    """
    Get provider details by provider_id.
    """
    providers = _load_json("providers.json")
    provider = providers.get(provider_id)
    
    if not provider:
        raise ValueError(f"Provider {provider_id} not found and no default available")

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

def create_task_for_staff(type: TaskType, task: HITLTask):
    """
    Save a HITL task to a JSON file for staff processing.
    """
    tasks_file = _DATA_DIR / "staff_tasks.json"
    
    if tasks_file.exists():
        with open(tasks_file) as f:
            tasks = json.load(f)
    else:
        tasks = []
    
    tasks.append(task.model_dump(mode="json"))
    
    with open(tasks_file, "w") as f:
        json.dump(tasks, f, indent=2, default=str)

def check_hitl_task_status(task_id: str) -> HITLTask:
    """
    Check the status of a HITL task.
    """
    tasks_file = _DATA_DIR / "staff_tasks.json"

    if not tasks_file.exists():
        return None

    with open(tasks_file) as f:
        tasks = json.load(f)

    for task in tasks:
        if task["task_id"] == task_id:
            return HITLTask(**task)

    return None
