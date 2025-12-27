"""Audit logging system for PA Healthcare Agent compliance."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from threading import local
import json

from models.core import AuditEntry


class AuditLogger:
    """Centralized audit logging system for compliance tracking."""
    
    def __init__(self, logger_name: str = "pa_healthcare_agent.audit"):
        """Initialize the audit logger."""
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        
        # Thread-local storage for user context
        self._context = local()
        
        # In-memory audit trail storage (in production, this would be a database)
        self._audit_entries: List[AuditEntry] = []
        
        # Configure structured logging
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @contextmanager
    def user_context(self, user_id: str, session_id: Optional[str] = None):
        """Context manager to set user context for audit logging."""
        old_user_id = getattr(self._context, 'user_id', None)
        old_session_id = getattr(self._context, 'session_id', None)
        
        self._context.user_id = user_id
        self._context.session_id = session_id
        
        try:
            yield
        finally:
            self._context.user_id = old_user_id
            self._context.session_id = old_session_id
    
    def _get_current_user_id(self) -> str:
        """Get the current user ID from context."""
        user_id = getattr(self._context, 'user_id', None)
        return user_id if user_id is not None else 'system'
    
    def _get_current_session_id(self) -> Optional[str]:
        """Get the current session ID from context."""
        return getattr(self._context, 'session_id', None)
    
    def log_action(
        self,
        action_type: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
        phi_accessed: bool = False,
        justification: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> AuditEntry:
        """Log a system action with full audit trail."""
        # Use provided user_id or get from context
        effective_user_id = user_id or self._get_current_user_id()
        
        # Create audit entry
        entry = AuditEntry(
            user_id=effective_user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            phi_accessed=phi_accessed,
            justification=justification
        )
        
        # Add session context if available
        session_id = self._get_current_session_id()
        if session_id:
            entry.details['session_id'] = session_id
        
        # Store audit entry
        self._audit_entries.append(entry)
        
        # Log to structured logger
        log_data = {
            'timestamp': entry.timestamp.isoformat(),
            'user_id': entry.user_id,
            'action_type': entry.action_type,
            'resource_type': entry.resource_type,
            'resource_id': entry.resource_id,
            'phi_accessed': entry.phi_accessed,
            'justification': entry.justification,
            'details': entry.details
        }
        
        self.logger.info(f"AUDIT: {json.dumps(log_data)}")
        
        return entry
    
    def log_phi_access(
        self,
        resource_type: str,
        resource_id: str,
        justification: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> AuditEntry:
        """Log PHI access with required justification."""
        return self.log_action(
            action_type="phi_access",
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            phi_accessed=True,
            justification=justification,
            user_id=user_id
        )
    
    
    def log_workflow_transition(
        self,
        pa_request_id: str,
        old_status: str,
        new_status: str,
        user_id: Optional[str] = None
    ) -> AuditEntry:
        """Log PA workflow status transitions."""
        return self.log_action(
            action_type="workflow_transition",
            resource_type="pa_request",
            resource_id=pa_request_id,
            details={
                "old_status": old_status,
                "new_status": new_status
            },
            phi_accessed=False,
            user_id=user_id
        )
    
    def log_tool_call(
        self,
        resource_type: str,
        resource_id: str,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        tool_response: Optional[Dict[str, Any]],
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> AuditEntry:
        """Log important tool calls."""
        tool_details = {
            "tool_name": tool_name,            
            "tool_arguments": tool_arguments, 
            "tool_response": tool_response
        }
        if details:
            tool_details.update(details)
        
        return self.log_action(
            action_type="tool_call",
            resource_type=resource_type,
            resource_id=resource_id,
            details=tool_details,
            user_id=user_id
        )
    
    def get_audit_trail(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[AuditEntry]:
        """Retrieve audit entries based on filters."""
        filtered_entries = self._audit_entries
        
        if resource_type:
            filtered_entries = [e for e in filtered_entries if e.resource_type == resource_type]
        
        if resource_id:
            filtered_entries = [e for e in filtered_entries if e.resource_id == resource_id]
        
        if user_id:
            filtered_entries = [e for e in filtered_entries if e.user_id == user_id]
        
        if start_time:
            filtered_entries = [e for e in filtered_entries if e.timestamp >= start_time]
        
        if end_time:
            filtered_entries = [e for e in filtered_entries if e.timestamp <= end_time]
        
        return sorted(filtered_entries, key=lambda x: x.timestamp)
    
# Global audit logger instance
audit_logger = AuditLogger()
