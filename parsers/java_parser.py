import re
import logging
from typing import List, Dict, Any
from pathlib import Path
from parsers.base_parser import BaseParser, CodeElement

logger = logging.getLogger(__name__)


class JavaParser(BaseParser):
    """Parser for Java code using regex and pattern matching."""
    
    def __init__(self):
        super().__init__()
        self.supported_extensions = [".java"]
    
    def can_parse(self, file_path: str) -> bool:
        return Path(file_path).suffix in self.supported_extensions
    
    def parse_file(self, file_path: str) -> List[CodeElement]:
        """Parse a Java file and extract code elements."""
        elements = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
            
            # Extract classes
            class_pattern = r"(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)"
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                end_line = self._find_class_end(content, match.start())
                
                element = CodeElement(
                    name=class_name,
                    element_type="class",
                    file_path=file_path,
                    line_start=start_line,
                    line_end=end_line,
                    code="\n".join(lines[start_line - 1:end_line]),
                    metadata={}
                )
                elements.append(element)
            
            # Extract methods
            method_pattern = r"(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>\[\]]+\s+)?(\w+)\s*\([^)]*\)\s*\{"
            for match in re.finditer(method_pattern, content):
                method_name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                end_line = self._find_method_end(content, match.start())
                
                element = CodeElement(
                    name=method_name,
                    element_type="method",
                    file_path=file_path,
                    line_start=start_line,
                    line_end=end_line,
                    code="\n".join(lines[start_line - 1:end_line]),
                    metadata={}
                )
                elements.append(element)
        
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
        
        return elements
    
    def _find_class_end(self, content: str, start_pos: int) -> int:
        """Find the end line of a class."""
        brace_count = 0
        in_class = False
        
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == "{":
                brace_count += 1
                in_class = True
            elif char == "}":
                brace_count -= 1
                if in_class and brace_count == 0:
                    return content[:i].count("\n") + 1
        
        return start_pos + 100  # Fallback
    
    def _find_method_end(self, content: str, start_pos: int) -> int:
        """Find the end line of a method."""
        return self._find_class_end(content, start_pos)
    
    def extract_imports(self, file_path: str) -> List[str]:
        """Extract import statements from a Java file."""
        imports = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Java imports
            import_pattern = r"import\s+(?:static\s+)?([\w.]+)\s*;"
            for match in re.finditer(import_pattern, content):
                imports.append(match.group(1))
        
        except Exception as e:
            logger.error(f"Error extracting imports from {file_path}: {e}")
        
        return imports
    
    def extract_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Extract dependencies from a Java file."""
        imports = self.extract_imports(file_path)
        
        # Categorize imports
        java_standard = []
        third_party = []
        local = []
        
        for imp in imports:
            if imp.startswith("java.") or imp.startswith("javax."):
                java_standard.append(imp)
            elif "." in imp:
                parts = imp.split(".")
                if len(parts) > 2:
                    third_party.append(imp)
                else:
                    local.append(imp)
            else:
                local.append(imp)
        
        return {
            "imports": imports,
            "java_standard": java_standard,
            "third_party": third_party,
            "local": local,
        }
