import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from services.repository_manager import RepositoryManager
from services.code_parser import CodeParserService

logger = logging.getLogger(__name__)


class PlanningAgent(BaseAgent):
    """Agent that analyzes codebase structure and creates execution plans."""
    
    def __init__(self):
        super().__init__(
            name="planning_agent",
            description="Analyzes codebase structure and creates execution plans"
        )
        self.repo_manager = RepositoryManager()
        self.parser_service = CodeParserService()
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute planning analysis."""
        repository_path = state.get("repository_path")
        if not repository_path:
            raise ValueError("repository_path not found in state")
        
        logger.info(f"Planning agent analyzing: {repository_path}")
        
        # Get repository info
        repo_info = self.repo_manager.get_repository_info(repository_path)
        state.update("repository_info", repo_info)
        
        # List files
        files = self.repo_manager.list_files(repository_path)
        state.update("total_files", len(files))
        
        # Identify languages
        languages = self._identify_languages(files)
        state.update("languages", languages)
        
        # Create analysis plan
        plan = self._create_plan(repository_path, files, languages)
        state.update("analysis_plan", plan)
        
        state.add_history({
            "agent": self.name,
            "action": "created_analysis_plan",
            "plan_steps": len(plan.get("steps", [])),
        })
        
        logger.info(f"Planning agent completed: {len(plan.get('steps', []))} steps")
        return state
    
    def _identify_languages(self, files: list) -> Dict[str, int]:
        """Identify programming languages in the codebase."""
        languages = {}
        
        for file_path in files:
            ext = file_path.split(".")[-1] if "." in file_path else ""
            
            lang_map = {
                "py": "python",
                "js": "javascript",
                "jsx": "javascript",
                "ts": "typescript",
                "tsx": "typescript",
                "java": "java",
                "go": "go",
                "rb": "ruby",
                "php": "php",
            }
            
            if ext in lang_map:
                lang = lang_map[ext]
                languages[lang] = languages.get(lang, 0) + 1
        
        return languages
    
    def _create_plan(
        self,
        repository_path: str,
        files: list,
        languages: Dict[str, int]
    ) -> Dict[str, Any]:
        """Create an analysis execution plan."""
        steps = []
        
        # Step 1: Code browsing
        steps.append({
            "step": 1,
            "agent": "code_browser_agent",
            "description": "Browse codebase and extract structure",
            "estimated_time": len(files) * 0.1,  # seconds
        })
        
        # Step 2: Dependency mapping
        steps.append({
            "step": 2,
            "agent": "dependency_mapper_agent",
            "description": "Map dependencies between services",
            "estimated_time": len(files) * 0.2,
        })
        
        # Step 3: Documentation generation
        steps.append({
            "step": 3,
            "agent": "documentation_agent",
            "description": "Generate service documentation",
            "estimated_time": len(languages) * 30,  # seconds per language
        })
        
        # Step 4: Impact analysis preparation
        steps.append({
            "step": 4,
            "agent": "impact_agent",
            "description": "Prepare impact analysis capabilities",
            "estimated_time": 60,
        })
        
        return {
            "repository_path": repository_path,
            "total_files": len(files),
            "languages": languages,
            "steps": steps,
            "estimated_total_time": sum(s["estimated_time"] for s in steps),
        }
