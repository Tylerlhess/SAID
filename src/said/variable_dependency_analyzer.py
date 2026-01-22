"""Two-pass variable dependency analysis.

This module implements a two-pass process to build proper task dependencies
based on variable production and consumption:

1. First pass: Build a "producers" dictionary mapping variables to what produces them
2. Second pass: Map each task's required variables to the tasks that produce them
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from said.schema import DependencyMap, TaskMetadata
from said.variable_searcher import find_variable_suggestions


class VariableProducer:
    """Represents a source that produces a variable."""

    def __init__(self, source_type: str, source_name: str, source_path: Optional[str] = None):
        """Initialize a variable producer.

        Args:
            source_type: Type of source ('task', 'group_vars', 'host_vars', 'inventory', 'role_defaults', 'role_vars', 'playbook')
            source_name: Name of the source (task name, file path, etc.)
            source_path: Optional path to the source file.
        """
        self.source_type = source_type
        self.source_name = source_name
        self.source_path = source_path

    def __repr__(self):
        return f"VariableProducer(type={self.source_type}, name={self.source_name}, path={self.source_path})"

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_path": self.source_path,
        }


def build_producers_dictionary(
    dependency_map: DependencyMap,
    search_base: Optional[Path] = None,
    known_variables: Optional[Dict] = None,
) -> Dict[str, List[VariableProducer]]:
    """First pass: Build a dictionary of all variable producers.

    This function analyzes:
    - Tasks that register variables (via 'register' in Ansible) - inferred from depends_on
    - Tasks that set facts (via 'set_fact' module)
    - Variable files (group_vars, host_vars, inventory, role defaults/vars)
    - Playbook vars sections

    Args:
        dependency_map: The dependency map containing all tasks.
        search_base: Base directory to search for variable files.
        known_variables: Optional dictionary of known variables from inventory/vars.

    Returns:
        Dictionary mapping variable names to lists of VariableProducer objects.
    """
    producers: Dict[str, List[VariableProducer]] = {}

    # Add known variables from inventory/vars files
    if known_variables:
        for var_name in known_variables.keys():
            if var_name not in producers:
                producers[var_name] = []
            # Mark as provided by inventory/vars
            producers[var_name].append(
                VariableProducer(
                    source_type="inventory",
                    source_name="inventory_vars",
                    source_path=None,
                )
            )

    # Build a reverse map: for each task, what variables might it produce?
    # We can infer this from:
    # 1. Tasks that other tasks depend on (they might produce variables)
    # 2. Tasks with "provides" that match variable names
    task_to_variables: Dict[str, Set[str]] = {}
    for task in dependency_map.tasks:
        # Check if task's "provides" includes variable-like names
        for provided in task.provides:
            # If provided looks like a variable name (not a resource name)
            if provided and not provided.startswith("_"):
                if task.name not in task_to_variables:
                    task_to_variables[task.name] = set()
                task_to_variables[task.name].add(provided)

    # Search for variables in files if search_base provided
    if search_base:
        # Get all unique variables from all tasks
        all_variables = set()
        for task in dependency_map.tasks:
            all_variables.update(task.requires_vars)

        # Search for each variable in files
        for var_name in all_variables:
            suggestions = find_variable_suggestions(var_name, search_base)
            for category, files in suggestions.items():
                for file_info in files:
                    if var_name not in producers:
                        producers[var_name] = []
                    producers[var_name].append(
                        VariableProducer(
                            source_type=category,
                            source_name=var_name,
                            source_path=file_info.get("file"),
                        )
                    )

    # Add task-based producers (from task_to_variables map)
    for task_name, variables in task_to_variables.items():
        for var_name in variables:
            if var_name not in producers:
                producers[var_name] = []
            producers[var_name].append(
                VariableProducer(
                    source_type="task",
                    source_name=task_name,
                    source_path=None,
                )
            )

    return producers


def map_variable_dependencies_to_tasks(
    dependency_map: DependencyMap,
    producers: Dict[str, List[VariableProducer]],
) -> Dict[str, Set[str]]:
    """Second pass: Map each task's required variables to producing tasks.

    For each task, identify its required variables, then use the producers
    dictionary to find which tasks (or variable files) provide those variables.
    Build a mapping of task_name -> set of task names it depends on.

    Args:
        dependency_map: The dependency map containing all tasks.
        producers: Dictionary mapping variables to their producers.

    Returns:
        Dictionary mapping task names to sets of task names they depend on
        (based on variable dependencies).
    """
    task_dependencies: Dict[str, Set[str]] = {}

    # Build a map of task names for quick lookup
    task_name_map = {task.name: task for task in dependency_map.tasks}

    for task in dependency_map.tasks:
        task_deps = set()

        # For each required variable, find tasks that produce it
        for required_var in task.requires_vars:
            if required_var in producers:
                for producer in producers[required_var]:
                    # If producer is a task, add it as a dependency
                    if producer.source_type == "task":
                        if producer.source_name in task_name_map:
                            task_deps.add(producer.source_name)
                    # For variable files, we could create virtual tasks or
                    # just note that the variable is available from files
                    # For now, we'll focus on task-to-task dependencies

        # Also check existing depends_on (from provides/depends_on relationships)
        for resource in task.depends_on:
            # Find tasks that provide this resource
            for other_task in dependency_map.tasks:
                if resource in other_task.provides:
                    task_deps.add(other_task.name)

        task_dependencies[task.name] = task_deps

    return task_dependencies


def analyze_variable_dependencies_comprehensive(
    dependency_map: DependencyMap,
    search_base: Optional[Path] = None,
    known_variables: Optional[Dict] = None,
) -> Dict[str, Dict]:
    """Comprehensive two-pass variable dependency analysis.

    This function:
    1. Builds a producers dictionary (first pass)
    2. Maps variable dependencies to task dependencies (second pass)
    3. Returns a comprehensive analysis

    Args:
        dependency_map: The dependency map containing all tasks.
        search_base: Base directory to search for variable files.
        known_variables: Optional dictionary of known variables.

    Returns:
        Dictionary containing:
        - 'producers': Dictionary mapping variables to their producers
        - 'task_dependencies': Dictionary mapping tasks to their variable-based dependencies
        - 'missing_variables': Dictionary mapping tasks to variables they need but can't find producers for
    """
    # First pass: Build producers dictionary
    producers = build_producers_dictionary(dependency_map, search_base, known_variables)

    # Second pass: Map variable dependencies to tasks
    task_dependencies = map_variable_dependencies_to_tasks(dependency_map, producers)

    # Identify missing variables (variables needed but no producers found)
    missing_variables: Dict[str, Set[str]] = {}
    for task in dependency_map.tasks:
        missing = set()
        for required_var in task.requires_vars:
            if required_var not in producers:
                missing.add(required_var)
        if missing:
            missing_variables[task.name] = missing

    return {
        "producers": {var: [p.to_dict() for p in prods] for var, prods in producers.items()},
        "task_dependencies": {task: list(deps) for task, deps in task_dependencies.items()},
        "missing_variables": {task: list(vars) for task, vars in missing_variables.items()},
    }
