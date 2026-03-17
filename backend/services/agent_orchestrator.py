import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from agents.base_agent import BaseAgent, AgentState
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AgentOrchestrator:
    """Orchestrates multi-agent workflows."""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.active_runs: Dict[str, Dict[str, Any]] = {}
    
    def register_agent(self, agent: BaseAgent):
        """Register an agent."""
        self.agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")
    
    def create_run(self, repository_id: str, initial_data: Optional[Dict[str, Any]] = None) -> str:
        """Create a new analysis run."""
        run_id = str(uuid.uuid4())
        self.active_runs[run_id] = {
            "id": run_id,
            "repository_id": repository_id,
            "status": "running",
            "state": AgentState(initial_data),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        logger.info(f"Created analysis run: {run_id}")
        return run_id
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run information."""
        return self.active_runs.get(run_id)
    
    def execute_agent(
        self,
        run_id: str,
        agent_name: str
    ) -> Dict[str, Any]:
        """Execute a specific agent."""
        if run_id not in self.active_runs:
            raise ValueError(f"Run {run_id} not found")
        
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} not found")
        
        run = self.active_runs[run_id]
        agent = self.agents[agent_name]
        
        try:
            logger.info(f"Executing agent {agent_name} for run {run_id}")
            updated_state = agent.execute(run["state"])
            run["state"] = updated_state
            run["updated_at"] = datetime.utcnow()
            
            return {
                "run_id": run_id,
                "agent": agent_name,
                "status": "completed",
                "checkpoints": updated_state.checkpoints,
            }
        except Exception as e:
            logger.error(f"Error executing agent {agent_name}: {e}")
            run["status"] = "failed"
            raise
    
    def execute_workflow(
        self,
        run_id: str,
        agent_sequence: List[str]
    ) -> Dict[str, Any]:
        """Execute a sequence of agents."""
        results = []
        
        for agent_name in agent_sequence:
            if agent_name not in self.agents:
                logger.warning(f"Agent {agent_name} not found, skipping")
                continue
            
            result = self.execute_agent(run_id, agent_name)
            results.append(result)
            
            # Check for pending checkpoints
            run = self.active_runs[run_id]
            pending_checkpoints = [
                cp for cp in run["state"].checkpoints
                if cp.get("status") == "pending"
            ]
            
            if pending_checkpoints:
                logger.info(f"Pausing workflow for {len(pending_checkpoints)} checkpoints")
                return {
                    "run_id": run_id,
                    "status": "paused",
                    "checkpoints": pending_checkpoints,
                    "completed_agents": results,
                }
        
        run = self.active_runs[run_id]
        run["status"] = "completed"
        
        return {
            "run_id": run_id,
            "status": "completed",
            "results": results,
        }
    
    def resolve_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Resolve a human review checkpoint."""
        if run_id not in self.active_runs:
            raise ValueError(f"Run {run_id} not found")
        
        run = self.active_runs[run_id]
        state = run["state"]
        
        for checkpoint in state.checkpoints:
            if checkpoint["id"] == checkpoint_id:
                checkpoint["status"] = "resolved"
                checkpoint["response"] = response
                checkpoint["resolved_at"] = datetime.utcnow().isoformat()
                checkpoint["metadata"] = metadata or {}
                logger.info(f"Resolved checkpoint {checkpoint_id}")
                return
        
        raise ValueError(f"Checkpoint {checkpoint_id} not found")
