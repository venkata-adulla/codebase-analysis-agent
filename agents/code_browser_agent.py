import logging
from typing import Dict, Any
from agents.base_agent import BaseAgent, AgentState
from core.config import get_settings
from services.code_parser import CodeParserService
from services.repository_manager import RepositoryManager

logger = logging.getLogger(__name__)
settings = get_settings()


class CodeBrowserAgent(BaseAgent):
    """Agent that recursively explores codebase and extracts structure."""
    
    def __init__(self):
        super().__init__(
            name="code_browser_agent",
            description="Recursively explores codebase and extracts structure"
        )
        self.parser_service = CodeParserService()
        self.repo_manager = RepositoryManager()
    
    def execute(self, state: AgentState) -> AgentState:
        """Execute code browsing."""
        repository_path = state.get("repository_path")
        if not repository_path:
            raise ValueError("repository_path not found in state")
        
        logger.info(f"Code browser agent analyzing: {repository_path}")
        
        # Get all code files
        code_files = self.repo_manager.list_files(
            repository_path,
            extensions=["py", "js", "jsx", "ts", "tsx", "java"]
        )
        
        # Parse files
        parsed_files = {}
        code_elements = []
        
        max_files = int(getattr(settings, "code_browser_max_files", 600) or 600)
        for file_path in code_files[:max_files]:
            try:
                elements = self.parser_service.parse_file(file_path)
                if elements:
                    parsed_files[file_path] = elements
                    code_elements.extend(elements)
            except Exception as e:
                logger.warning(f"Error parsing {file_path}: {e}")
        
        state.update("parsed_files", parsed_files)
        state.update("code_elements", [e.to_dict() for e in code_elements])
        state.update("total_elements", len(code_elements))
        
        # Extract imports
        all_imports = {}
        for file_path in code_files[:max_files]:
            try:
                imports = self.parser_service.extract_imports(file_path)
                if imports:
                    all_imports[file_path] = imports
            except Exception as e:
                logger.warning(f"Error extracting imports from {file_path}: {e}")
        
        state.update("imports", all_imports)
        
        state.add_history({
            "agent": self.name,
            "action": "browsed_codebase",
            "files_parsed": len(parsed_files),
            "elements_found": len(code_elements),
        })
        
        logger.info(f"Code browser agent completed: {len(parsed_files)} files, {len(code_elements)} elements")
        return state
