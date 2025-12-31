"""Data models for Human-in-the-Loop (HITL) operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class TaskType(str, Enum):
    """Types of HITL tasks."""
    CLINICAL_REVIEW = "clinical_review"
    REQUIRE_DOCUMENTS = "require_documents"
    DOCUMENTATION_REVIEW = "documentation_review"
    APPEAL_REVIEW = "appeal_review"
    AMBIGUOUS_RESPONSE = "ambiguous_response"
    URGENT_REQUEST = "urgent_request"
    COMPLIANCE_REVIEW = "compliance_review"
    TECHNICAL_ESCALATION = "technical_escalation"
    MISSING_DATA = "missing_data"


class TaskPriority(str, Enum):
    """Priority levels for HITL tasks."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENT = "emergent"


class TaskStatus(str, Enum):
    """Status of HITL tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


class HITLTask(BaseModel):
    """Human intervention task with context and tracking."""
    task_id: str = Field(..., description="Unique task identifier")
    pa_request_id: str = Field(..., description="Associated PA request ID")
    task_type: TaskType = Field(..., description="Type of intervention required")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="Task priority")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    
    title: str = Field(..., description="Brief task title")
    description: str = Field(..., description="Detailed task description")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="Additional context information")
    
    assigned_to: str = Field(..., description="Staff member assigned to task")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Task creation timestamp")
    
    due_date: Optional[datetime] = Field(None, description="Task due date")
    completed_at: Optional[datetime] = Field(None, description="When task was completed")
    
    resolution_notes: Optional[str] = Field(None, description="Notes about task resolution")
    resolution_data: Optional[Dict[str, Any]] = Field(None, description="Data associated with task resolution")
    
    escalation_count: int = Field(default=0, description="Number of times task has been escalated")
    escalation_history: List[Dict[str, Any]] = Field(default_factory=list, description="History of escalations")

    def escalate(self, reason: str, escalated_to: Optional[str] = None) -> None:
        """Escalate the task to higher priority or different staff."""
        self.escalation_count += 1
        self.escalation_history.append({
            "timestamp": datetime.utcnow(),
            "reason": reason,
            "escalated_to": escalated_to,
            "previous_assignee": self.assigned_to
        })
        if escalated_to:
            self.assigned_to = escalated_to
        # Increase priority if not already at maximum
        if self.priority != TaskPriority.EMERGENT:
            priority_order = [TaskPriority.LOW, TaskPriority.NORMAL, TaskPriority.HIGH, TaskPriority.URGENT, TaskPriority.EMERGENT]
            current_index = priority_order.index(self.priority)
            if current_index < len(priority_order) - 1:
                self.priority = priority_order[current_index + 1]

    def complete(self, resolution_notes: str, resolution_data: Optional[Dict[str, Any]] = None) -> None:
        """Mark task as completed with resolution details."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.resolution_notes = resolution_notes
        self.resolution_data = resolution_data or {}
