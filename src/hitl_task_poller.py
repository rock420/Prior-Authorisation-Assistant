"""
HITL Task Polling Service Mock

Polls for completed HITL tasks and resumes the workflow
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from .models.hitl import HITLTask, TaskStatus, TaskType
from .integrations.provider import check_hitl_task_status
from .agent.requirement.state import RequireItemResult, RequireItemStatus, DocumentInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Suppress verbose polling logs


class PollingState(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TrackedTask:
    """Tracks a HITL task for status polling."""
    task_id: str
    pa_request_id: str
    last_status: TaskStatus = TaskStatus.PENDING
    last_checked: Optional[datetime] = None
    check_count: int = 0
    polling_state: PollingState = PollingState.ACTIVE
    error_message: Optional[str] = None


class HITLTaskPoller:
    """Polls HITL task status and triggers workflow continuation."""
    
    def __init__(
        self,
        poll_interval_seconds: int = 30,
        max_retries: int = 3,
    ):
        self.poll_interval = poll_interval_seconds
        self.max_retries = max_retries
        self._tracked_tasks: Dict[str, TrackedTask] = {}
        self._running = False
        self._workflow = None
    
    def add_task(self, task: HITLTask) -> None:
        """Add a HITL task to track."""
        if task.task_id not in self._tracked_tasks:
            self._tracked_tasks[task.task_id] = TrackedTask(
                task_id=task.task_id,
                pa_request_id=task.pa_request_id
            )
            logger.info(f"Added task {task.task_id} for tracking (PA: {task.pa_request_id})")
    
    def remove_task(self, task_id: str) -> None:
        """Remove a task from tracking."""
        if task_id in self._tracked_tasks:
            del self._tracked_tasks[task_id]
            logger.info(f"Removed task {task_id} from tracking")
    
    async def _check_status(self, tracked: TrackedTask) -> Optional[HITLTask]:
        """Check status for a single task."""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                task = check_hitl_task_status(tracked.task_id)
                tracked.last_checked = datetime.now(UTC)
                tracked.check_count += 1
                return task
            except Exception as e:
                retry_count += 1
                logger.warning(
                    f"Error checking status for {tracked.task_id} "
                    f"(attempt {retry_count}/{self.max_retries}): {e}"
                )
                if retry_count < self.max_retries:
                    await asyncio.sleep(2 * retry_count)
        
        tracked.error_message = f"Status check failed after {self.max_retries} retries"
        return None
    
    async def _handle_status_change(self, tracked: TrackedTask, task: HITLTask) -> None:
        """Handle a status change by invoking the workflow."""
        logger.info(
            f"Status change detected for {tracked.task_id}: "
            f"{tracked.last_status} -> {task.status}"
        )
        
        if self._workflow is None:
            from .agent.workflow import create_workflow
            self._workflow = create_workflow()

        config = {"configurable": {"thread_id": tracked.pa_request_id}}
        if task.task_type == TaskType.REQUIRE_DOCUMENTS:
            requirement_result: List[RequireItemResult] = self._workflow.get_state(config).values["requirement_result"]
            for item in requirement_result:
                if item.item_id in task.resolution_data.keys():
                    item.status = RequireItemStatus.FOUND
                    item.documents = [DocumentInfo(**doc) for doc in task.resolution_data[item.item_id].get("documents", [])]
                    item.information = task.resolution_data[item.item_id].get("information", None)
            self._workflow.update_state(config, {"awaiting_clinician_input": False, "pending_hitl_task": None, "requirement_result": requirement_result})


        try:
            asyncio.create_task(self._invoke_workflow(config, tracked.pa_request_id))
            
            logger.info(f"Workflow invocation scheduled for task {tracked.task_id}")
            tracked.polling_state = PollingState.COMPLETED
                
        except Exception as e:
            logger.error(f"Error scheduling workflow for {tracked.task_id}: {e}")
            tracked.polling_state = PollingState.ERROR
            tracked.error_message = str(e)
    
    async def _invoke_workflow(self, config: dict, pa_request_id: str) -> None:
        try:
            await self._workflow.ainvoke(None, config=config)
            logger.info(f"Workflow completed for PA {pa_request_id}")
        except Exception as e:
            logger.error(f"Workflow execution failed for PA {pa_request_id}: {e}")
            logger.exception("Full traceback:")
    
    async def _poll_once(self) -> None:
        """Perform one polling cycle for all active tasks."""
        active_tasks = [
            t for t in self._tracked_tasks.values()
            if t.polling_state == PollingState.ACTIVE
        ]
        
        for tracked in active_tasks:
            task = await self._check_status(tracked)
            if task is None:
                continue
            
            # Check for status change to COMPLETED
            if task.status == TaskStatus.COMPLETED and tracked.last_status != TaskStatus.COMPLETED:
                await self._handle_status_change(tracked, task)
            
            tracked.last_status = task.status
    
    async def start(self) -> None:
        """Start the polling loop."""
        self._running = True
        logger.info(f"HITL Task Poller started (interval: {self.poll_interval}s)")
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"Error in polling cycle: {e}")
            
            self._cleanup_completed()
            await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("HITL Task Poller stopped")
    
    def _cleanup_completed(self) -> None:
        """Remove completed tasks from tracking."""
        completed = [
            tid for tid, t in self._tracked_tasks.items()
            if t.polling_state == PollingState.COMPLETED
        ]
        for tid in completed:
            del self._tracked_tasks[tid]
            logger.info(f"Cleaned up completed task {tid}")


_poller: Optional[HITLTaskPoller] = None


def get_poller(
    poll_interval_seconds: int = 30,
    max_retries: int = 3
) -> HITLTaskPoller:
    """Get or create the global poller instance."""
    global _poller
    if _poller is None:
        _poller = HITLTaskPoller(poll_interval_seconds=poll_interval_seconds, max_retries=max_retries)
    return _poller


async def start_hitl_polling_service(
    poll_interval: int = 30,
    max_retries: int = 3
) -> HITLTaskPoller:
    """Start the HITL task polling service."""
    poller = get_poller(poll_interval_seconds=poll_interval, max_retries=max_retries)
    asyncio.create_task(poller.start())
    return poller


def track_hitl_task(task: HITLTask) -> None:
    """Add a task to be tracked by the poller."""
    poller = get_poller()
    poller.add_task(task)
