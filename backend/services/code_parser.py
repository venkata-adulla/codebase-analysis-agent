import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from parsers.base_parser import BaseParser, CodeElement
from parsers.python_parser import PythonParser
from parsers.javascript_parser import JavaScriptParser
from parsers.java_parser import JavaParser

logger = logging.getLogger(__name__)


class CodeParserService:
    """Service for parsing code files in multiple languages."""
    
    def __init__(self):
        self.parsers: List[BaseParser] = [
            PythonParser(),
            JavaScriptParser(),
            JavaParser(),
        ]
    
    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        """Get the appropriate parser for a file."""
        for parser in self.parsers:
            if parser.can_parse(file_path):
                return parser
        return None
    
    def parse_file(self, file_path: str) -> List[CodeElement]:
        """Parse a file and return code elements."""
        parser = self.get_parser(file_path)
        if not parser:
            logger.warning(f"No parser available for {file_path}")
            return []
        
        try:
            return parser.parse_file(file_path)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return []
    
    def extract_imports(self, file_path: str) -> List[str]:
        """Extract imports from a file."""
        parser = self.get_parser(file_path)
        if not parser:
            return []
        
        try:
            return parser.extract_imports(file_path)
        except Exception as e:
            logger.error(f"Error extracting imports from {file_path}: {e}")
            return []
    
    def extract_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Extract dependencies from a file."""
        parser = self.get_parser(file_path)
        if not parser:
            return {}
        
        try:
            return parser.extract_dependencies(file_path)
        except Exception as e:
            logger.error(f"Error extracting dependencies from {file_path}: {e}")
            return {}
    
    def parse_directory(
        self,
        directory_path: str,
        extensions: Optional[List[str]] = None
    ) -> Dict[str, List[CodeElement]]:
        """Parse all files in a directory."""
        results = {}
        path = Path(directory_path)
        
        if extensions:
            files = []
            for ext in extensions:
                files.extend(path.rglob(f"*{ext}"))
        else:
            files = list(path.rglob("*"))
        
        for file_path in files:
            if file_path.is_file():
                file_str = str(file_path)
                elements = self.parse_file(file_str)
                if elements:
                    results[file_str] = elements
        
        return results
