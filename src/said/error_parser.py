"""Parse and structure error messages into JSON format."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from said.schema import DependencyMap


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


def structure_dependency_error(
    error_message: str,
    error_class: str = "BuilderError",
    dependency_map: Optional[DependencyMap] = None,
    search_base: Optional[Path] = None,
    known_variables: Optional[Dict] = None,
) -> Dict:
    """Structure a dependency error into the desired JSON format.

    Args:
        error_message: The error message string.
        error_class: The error class name.
        dependency_map: Optional dependency map to analyze for variable producers.
        search_base: Optional base directory to search for variable files.
        known_variables: Optional dictionary of known variables.

    Returns:
        Dictionary with structured error information in the desired format.
    """
    parsed = parse_dependency_error(error_message)
    
    if parsed:
        # Build available resources as a dict: {resource: producing_task, variable: producing_task}
        available_resources_dict = {}
        
        # FIRST: Add variables and their producing tasks using the two-pass analyzer
        # This is the key enhancement - include ALL variables, not just resources
        if dependency_map:
            from said.variable_dependency_analyzer import build_producers_dictionary
            
            try:
                producers = build_producers_dictionary(
                    dependency_map, search_base=search_base, known_variables=known_variables
                )
                
                # Add ALL variables to available_resources_dict as {variable: producing_task}
                for var_name, var_producers in producers.items():
                    # Find task-based producers (prefer tasks over files)
                    task_producer = None
                    for producer in var_producers:
                        if producer.source_type == "task":
                            task_producer = producer.source_name
                            break
                    
                    if task_producer:
                        available_resources_dict[var_name] = task_producer
                    elif var_producers and var_producers[0].source_type == "inventory":
                        # Variables from inventory
                        available_resources_dict[var_name] = "inventory"
                    elif var_producers:
                        # If no task producer, use the first producer's source name
                        available_resources_dict[var_name] = var_producers[0].source_name
            except Exception:
                # If variable analysis fails, continue without variables
                pass
        
        # SECOND: Add resources from the error message (these are from task.provides)
        # These are the "resources" (not variables) that tasks provide
        for resource in parsed["available_resources"]:
            # Skip if we already added it as a variable
            if resource in available_resources_dict:
                continue
                
            # Find which task provides this resource
            if dependency_map:
                for task in dependency_map.tasks:
                    if resource in task.provides:
                        available_resources_dict[resource] = task.name
                        break
                # If not found in dependency_map, it might be a variable we haven't seen yet
                if resource not in available_resources_dict:
                    available_resources_dict[resource] = resource
            else:
                # If no dependency map, just use the resource name as-is
                available_resources_dict[resource] = resource
        
        # Structure as requested: message.invalid_dependency with dependency and available_resources
        # Format: message.invalid_dependency.dependency_name = {dependency: name, available_resources: {var: task, ...}}
        invalid_dependency_dict = {}
        for dep in parsed["invalid_dependencies"]:
            invalid_dependency_dict[dep] = {
                "dependency": dep,
                "available_resources": available_resources_dict
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
