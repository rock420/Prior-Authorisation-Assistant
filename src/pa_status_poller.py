"""
PA Status Polling Service

A mock service that will poll status periodically with retry/backoff and trigger the workflow if there is a status change
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from .models.integration import PAStatus, PAStatusResponse
from .integrations.payer_service import check_pa_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PollingState(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TrackedSubmission:
    """Tracks a PA submission for status polling."""
    pa_request_id: str
    submission_id: str
    last_status: PAStatus = PAStatus.PENDING
    last_checked: Optional[datetime] = None
    check_count: int = 0
    polling_state: PollingState = PollingState.ACTIVE
    error_message: Optional[str] = None


class PAStatusPoller:
    """
    Polls PA submission status and triggers workflow continuation.
    """
    
    def __init__(
        self,
        poll_interval_seconds: int = 60,
        max_retries: int = 3,
    ):
        self.poll_interval = poll_interval_seconds
        self.max_retries = max_retries
        self._tracked_submissions: Dict[str, TrackedSubmission] = {}
        self._running = False
        self._workflow = None
    
    def add_submission(self, pa_request_id: str, submission_id: str) -> None:
        """Add a PA submission to track."""
        if submission_id not in self._tracked_submissions:
            self._tracked_submissions[submission_id] = TrackedSubmission(
                pa_request_id=pa_request_id,
                submission_id=submission_id
            )
            logger.info(f"Added submission {submission_id} for tracking (PA: {pa_request_id})")
    
    def remove_submission(self, submission_id: str) -> None:
        """Remove a submission from tracking."""
        if submission_id in self._tracked_submissions:
            del self._tracked_submissions[submission_id]
            logger.info(f"Removed submission {submission_id} from tracking")
    
    async def _check_status(self, tracked: TrackedSubmission) -> Optional[PAStatusResponse]:
        """Check status for a single submission."""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                status = check_pa_status(tracked.submission_id)
                tracked.last_checked = datetime.now(UTC)
                tracked.check_count += 1
                return status
            except Exception as e:
                retry_count += 1
                logger.warning(
                    f"Error checking status for {tracked.submission_id} "
                    f"(attempt {retry_count}/{self.max_retries}): {e}"
                )
                if retry_count < self.max_retries:
                    await asyncio.sleep(2*(retry_count))  # delay with backoff before retry
        
        tracked.error_message = f"Last statuc check failed after {self.max_retries} retries"
        return None
    
    async def _handle_status_change(
        self, 
        tracked: TrackedSubmission, 
        status: PAStatusResponse
    ) -> None:
        """Handle a status change by invoking the workflow."""
        logger.info(
            f"Status change detected for {tracked.submission_id}: "
            f"{tracked.last_status} -> {status.status}"
        )
        
        # Initialize workflow if needed
        if self._workflow is None:
            from .agent.workflow import create_workflow
            self._workflow = create_workflow()
        
        config = {"configurable": {"thread_id": tracked.pa_request_id}}
        
        try:
            # Update state with new status
            self._workflow.update_state(
                config, 
                {"status": status}
            )
        
            asyncio.create_task(self._invoke_workflow(config, tracked.pa_request_id))

            logger.info(f"Workflow invocation scheduled for PA {tracked.pa_request_id}")
            tracked.polling_state = PollingState.COMPLETED #need error handling
                
        except Exception as e:
            logger.error(f"Error scheduling workflow for {tracked.pa_request_id}: {e}")
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
        """Perform one polling cycle for all active submissions."""
        active_submissions = [
            s for s in self._tracked_submissions.values()
            if s.polling_state == PollingState.ACTIVE
        ]
        
        for tracked in active_submissions:
            status = await self._check_status(tracked)
            if status is None:
                continue
            
            # Check for status change from PENDING
            if status.status != PAStatus.PENDING:
                await self._handle_status_change(tracked, status)
            
            tracked.last_status = status.status
    
    async def start(self) -> None:
        """Start the polling loop."""
        self._running = True
        logger.info(f"PA Status Poller started (interval: {self.poll_interval}s)")
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"Error in polling cycle: {e}")
            
            # Clean up completed/errored submissions
            self._cleanup_completed()
            
            # Wait for next poll interval
            await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("PA Status Poller stopped")
    
    def _cleanup_completed(self) -> None:
        """Remove completed submissions from tracking."""
        completed = [
            sid for sid, s in self._tracked_submissions.items()
            if s.polling_state == PollingState.COMPLETED
        ]
        for sid in completed:
            del self._tracked_submissions[sid]
            logger.info(f"Cleaned up completed submission {sid}")


# Global poller instance
_poller: Optional[PAStatusPoller] = None


def get_poller(
    poll_interval_seconds: int = 30,
    max_retries: int = 3
) -> PAStatusPoller:
    """Get or create the global poller instance."""
    global _poller
    if _poller is None:
        _poller = PAStatusPoller(poll_interval_seconds=poll_interval_seconds, max_retries=max_retries)
    return _poller


async def start_PA_polling_service(
    poll_interval: int = 30,
    max_retries: int = 3
) -> PAStatusPoller:
    """Start the PA status polling service."""
    poller = get_poller(poll_interval_seconds=poll_interval, max_retries=max_retries)
    asyncio.create_task(poller.start())
    return poller


def track_submission(pa_request_id: str, submission_id: str) -> None:
    """Add a submission to be tracked by the poller."""
    poller = get_poller()
    poller.add_submission(pa_request_id, submission_id)
