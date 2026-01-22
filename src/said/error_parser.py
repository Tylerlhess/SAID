"""Parse and structure error messages into JSON format."""

import re
from typing import Dict, List, Optional


def parse_dependency_error(error_message: str) -> Optional[Dict]:
    """Parse a dependency error message and extract structured information.

    Parses messages like:
    "Task 'task_name' depends on non-existent resources: {'resource1', 'resource2'}. Available resources: res1, res2, res3"
    or
    "Invalid dependency map structure: Task 'task_name' depends on non-existent resources: {'resource1'}. Available resources: res1, res2"

    Args:
        error_message: The error message string to parse.

    Returns:
        Dictionary with structured error information, or None if parsing fails.
    """
    # Pattern to match: Task 'name' depends on non-existent resources: {set}. Available resources: list
    # Also handle "Invalid dependency map structure: " prefix
    # Task name can contain spaces, so we match everything between single quotes
    # Invalid deps can be in set format: {'dep1', 'dep2'} or just {dep1}
    pattern = r"(?:Invalid dependency map structure: )?Task '([^']+)' depends on non-existent resources: \{([^}]+)\}\. Available resources: (.+)"
    match = re.search(pattern, error_message)
    
    if match:
        task_name = match.group(1)
        invalid_deps_str = match.group(2)
        available_resources_str = match.group(3)
        
        # Parse invalid dependencies (remove quotes, split by comma)
        # Handle both 'resource' and "resource" formats, and set format {'dep1', 'dep2'}
        invalid_deps = []
        # Remove outer braces if present and split by comma
        deps_cleaned = invalid_deps_str.strip()
        # Split by comma, but be careful with quoted strings
        # Simple approach: split by comma and clean each
        for dep in deps_cleaned.split(","):
            dep = dep.strip().strip("'\"")
            if dep:
                invalid_deps.append(dep)
        
        # Parse available resources (split by comma)
        available_resources = [res.strip() for res in available_resources_str.split(",") if res.strip()]
        
        return {
            "task_name": task_name,
            "invalid_dependencies": invalid_deps,
            "available_resources": available_resources,
        }
    
    return None


def structure_dependency_error(error_message: str, error_class: str = "BuilderError") -> Dict:
    """Structure a dependency error into the desired JSON format.

    Args:
        error_message: The error message string.
        error_class: The error class name.

    Returns:
        Dictionary with structured error information in the desired format.
    """
    parsed = parse_dependency_error(error_message)
    
    if parsed:
        # Structure as requested: message.invalid_dependency with dependency and available_resources
        # Format: message.invalid_dependency.dependency_name = {dependency: name, available_resources: [...]}
        invalid_dependency_dict = {}
        for dep in parsed["invalid_dependencies"]:
            invalid_dependency_dict[dep] = {
                "dependency": dep,
                "available_resources": parsed["available_resources"]
            }
        
        result = {
            "error_type": "invalid_dependency",
            "task_name": parsed["task_name"],
            "message": {
                "invalid_dependency": invalid_dependency_dict
            },
            "details": {
                "error_class": error_class,
            }
        }
        
        return result
    
    # If parsing fails, return basic structure
    return {
        "error_type": "builder_error",
        "task_name": "build",
        "message": error_message,
        "details": {
            "error_class": error_class,
        }
    }
