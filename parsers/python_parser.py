import ast
import logging
import sys
from typing import List, Dict, Any
from pathlib import Path
from parsers.base_parser import BaseParser, CodeElement

logger = logging.getLogger(__name__)
STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", ())) | {
    "argparse", "ast", "collections", "csv", "datetime", "functools", "hashlib",
    "inspect", "itertools", "json", "logging", "math", "os", "pathlib", "re",
    "subprocess", "sys", "typing", "unittest", "urllib",
}


class PythonParser(BaseParser):
    """Parser for Python code using AST."""
    
    def __init__(self):
        super().__init__()
        self.supported_extensions = [".py"]
    
    def can_parse(self, file_path: str) -> bool:
        return Path(file_path).suffix in self.supported_extensions
    
    def parse_file(self, file_path: str) -> List[CodeElement]:
        """Parse a Python file and extract code elements."""
        elements = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tree = ast.parse(content, filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    element = CodeElement(
                        name=node.name,
                        element_type="function",
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        code=ast.get_source_segment(content, node),
                        metadata={
                            "args": [arg.arg for arg in node.args.args],
                            "decorators": [ast.unparse(d) for d in node.decorator_list],
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                        }
                    )
                    elements.append(element)
                
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    element = CodeElement(
                        name=node.name,
                        element_type="class",
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        code=ast.get_source_segment(content, node),
                        metadata={
                            "bases": [ast.unparse(b) for b in node.bases],
                            "decorators": [ast.unparse(d) for d in node.decorator_list],
                            "methods": methods,
                        }
                    )
                    elements.append(element)
        
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
        
        return elements
    
    def extract_imports(self, file_path: str) -> List[str]:
        """Extract import statements from a Python file."""
        imports = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tree = ast.parse(content, filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    prefix = "." * int(getattr(node, "level", 0) or 0)
                    if node.module:
                        imports.append(f"{prefix}{node.module}")
                        for alias in node.names:
                            if alias.name != "*":
                                imports.append(f"{prefix}{node.module}.{alias.name}")
                    else:
                        for alias in node.names:
                            if alias.name != "*":
                                imports.append(f"{prefix}{alias.name}")
        
        except Exception as e:
            logger.error(f"Error extracting imports from {file_path}: {e}")
        
        return imports
    
    def extract_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Extract dependencies from a Python file."""
        imports = self.extract_imports(file_path)
        
        # Categorize imports
        standard_library = []
        third_party = []
        local = []
        
        for imp in imports:
            if imp.startswith("."):
                local.append(imp)
                continue

            root = imp.split(".", 1)[0]
            if root in STDLIB_MODULES:
                standard_library.append(imp)
            elif "." in imp:
                third_party.append(imp)
            else:
                third_party.append(imp)
        
        return {
            "imports": imports,
            "standard_library": standard_library,
            "third_party": third_party,
            "local": local,
        }
