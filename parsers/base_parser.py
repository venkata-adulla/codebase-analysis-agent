from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path


class CodeElement:
    """Represents a code element (function, class, etc.)."""
    
    def __init__(
        self,
        name: str,
        element_type: str,
        file_path: str,
        line_start: int,
        line_end: int,
        code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.element_type = element_type  # function, class, method, etc.
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.code = code
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.element_type,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code": self.code,
            "metadata": self.metadata,
        }


class BaseParser(ABC):
    """Base class for code parsers."""
    
    def __init__(self):
        self.supported_extensions: List[str] = []
    
    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can parse the given file."""
        pass
    
    @abstractmethod
    def parse_file(self, file_path: str) -> List[CodeElement]:
        """Parse a file and return code elements."""
        pass
    
    @abstractmethod
    def extract_imports(self, file_path: str) -> List[str]:
        """Extract import statements from a file."""
        pass
    
    @abstractmethod
    def extract_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Extract dependencies (imports, API calls, etc.) from a file."""
        pass
