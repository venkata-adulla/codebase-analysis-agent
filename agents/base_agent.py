from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid


class AgentState:
    """State container for agent execution."""
    
    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        self.data = initial_data or {}
        self.history: List[Dict[str, Any]] = []
        self.checkpoints: List[Dict[str, Any]] = []
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def update(self, key: str, value: Any):
        """Update state data."""
        self.data[key] = value
        self.updated_at = datetime.utcnow()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get state data."""
        return self.data.get(key, default)
    
    def add_history(self, entry: Dict[str, Any]):
        """Add entry to history."""
        entry["timestamp"] = datetime.utcnow().isoformat()
        self.history.append(entry)
    
    def add_checkpoint(self, checkpoint: Dict[str, Any]):
        """Add a checkpoint requiring human review."""
        checkpoint["id"] = str(uuid.uuid4())
        checkpoint["timestamp"] = datetime.utcnow().isoformat()
        checkpoint["status"] = "pending"
        self.checkpoints.append(checkpoint)
        return checkpoint["id"]


class BaseAgent(ABC):
    """Base class for all agents."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        """Execute the agent's task."""
        pass
    
    def should_request_human_review(
        self,
        state: AgentState,
        reason: str,
        question: str,
        options: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if human review is needed and add checkpoint."""
        # Simple heuristic: if state has ambiguous data, request review
        checkpoint_id = state.add_checkpoint({
            "agent": self.name,
            "reason": reason,
            "question": question,
            "options": options,
            "context": context if context is not None else state.data.copy(),
        })
        return True
