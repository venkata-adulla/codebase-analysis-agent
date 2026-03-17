import re
import logging
from typing import List, Dict, Any
from pathlib import Path
from parsers.base_parser import BaseParser, CodeElement

logger = logging.getLogger(__name__)


class JavaScriptParser(BaseParser):
    """Parser for JavaScript/TypeScript code using regex and pattern matching."""
    
    def __init__(self):
        super().__init__()
        self.supported_extensions = [".js", ".jsx", ".ts", ".tsx"]
    
    def can_parse(self, file_path: str) -> bool:
        return Path(file_path).suffix in self.supported_extensions
    
    def parse_file(self, file_path: str) -> List[CodeElement]:
        """Parse a JavaScript/TypeScript file and extract code elements."""
        elements = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
            
            # Extract functions
            function_pattern = r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("
            for match in re.finditer(function_pattern, content):
                func_name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                # Find function end (simplified)
                end_line = self._find_function_end(content, match.start())
                
                element = CodeElement(
                    name=func_name,
                    element_type="function",
                    file_path=file_path,
                    line_start=start_line,
                    line_end=end_line,
                    code="\n".join(lines[start_line - 1:end_line]),
                    metadata={"is_async": "async" in match.group(0)}
                )
                elements.append(element)
            
            # Extract classes
            class_pattern = r"(?:export\s+)?class\s+(\w+)"
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
            
            # Extract arrow functions (exported)
            arrow_pattern = r"export\s+(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)\s*)?=>"
            for match in re.finditer(arrow_pattern, content):
                func_name = match.group(1)
                start_line = content[:match.start()].count("\n") + 1
                end_line = start_line + 10  # Simplified
                
                element = CodeElement(
                    name=func_name,
                    element_type="function",
                    file_path=file_path,
                    line_start=start_line,
                    line_end=end_line,
                    metadata={"is_arrow": True}
                )
                elements.append(element)
        
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
        
        return elements
    
    def _find_function_end(self, content: str, start_pos: int) -> int:
        """Find the end line of a function (simplified)."""
        brace_count = 0
        in_function = False
        
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == "{":
                brace_count += 1
                in_function = True
            elif char == "}":
                brace_count -= 1
                if in_function and brace_count == 0:
                    return content[:i].count("\n") + 1
        
        return start_pos + 50  # Fallback
    
    def _find_class_end(self, content: str, start_pos: int) -> int:
        """Find the end line of a class (simplified)."""
        return self._find_function_end(content, start_pos)
    
    def extract_imports(self, file_path: str) -> List[str]:
        """Extract import statements from a JavaScript/TypeScript file."""
        imports = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # ES6 imports
            import_pattern = r"import\s+(?:(?:\*\s+as\s+\w+)|(?:\{[^}]*\})|(?:\w+))\s+from\s+['\"]([^'\"]+)['\"]"
            for match in re.finditer(import_pattern, content):
                imports.append(match.group(1))
            
            # CommonJS requires
            require_pattern = r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
            for match in re.finditer(require_pattern, content):
                imports.append(match.group(1))
        
        except Exception as e:
            logger.error(f"Error extracting imports from {file_path}: {e}")
        
        return imports
    
    def extract_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Extract dependencies from a JavaScript/TypeScript file."""
        imports = self.extract_imports(file_path)
        
        # Categorize imports
        node_modules = []
        local = []
        external = []
        
        for imp in imports:
            if imp.startswith(".") or imp.startswith("/"):
                local.append(imp)
            elif "/" in imp and not imp.startswith("@"):
                external.append(imp)
            else:
                node_modules.append(imp)
        
        return {
            "imports": imports,
            "node_modules": node_modules,
            "local": local,
            "external": external,
        }
