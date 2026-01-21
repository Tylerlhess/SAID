"""Error collection and reporting for dependency validation.

This module provides functionality to collect all dependency-related errors
and format them as JSON for programmatic consumption.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from said.schema import DependencyMap


@dataclass
class DependencyError:
    """Represents a single dependency error."""

    error_type: str  # e.g., "missing_variable", "missing_dependency", "circular_dependency"
    task_name: str
    message: str
    details: Dict = field(default_factory=dict)


@dataclass
class DependencyErrorReport:
    """Collection of all dependency errors."""

    errors: List[DependencyError] = field(default_factory=list)
    total_errors: int = 0
    error_summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert error report to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the error report.
        """
        return {
            "total_errors": self.total_errors,
            "error_summary": self.error_summary,
            "errors": [
                {
                    "error_type": err.error_type,
                    "task_name": err.task_name,
                    "message": err.message,
                    "details": err.details,
                }
                for err in self.errors
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert error report to JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent)


class DependencyErrorCollector:
    """Collects all dependency-related errors without stopping at first failure."""

    def __init__(self):
        """Initialize the error collector."""
        self.errors: List[DependencyError] = []

    def collect_missing_variables(
        self,
        validation_results: Dict[str, Set[str]],
        search_base: Optional[Path] = None,
        search_for_suggestions: bool = True,
    ) -> None:
        """Collect missing variable errors from validation results.

        Args:
            validation_results: Dictionary mapping task names to sets of missing variables.
            search_base: Base directory to search for variable definitions.
            search_for_suggestions: If True, search for where variables might be defined.
        """
        from said.variable_searcher import find_all_variable_suggestions

        # Collect all unique missing variables
        all_missing_vars = set()
        for missing_vars in validation_results.values():
            all_missing_vars.update(missing_vars)

        # Search for suggestions if requested
        suggestions = {}
        if search_for_suggestions and all_missing_vars:
            suggestions = find_all_variable_suggestions(all_missing_vars, search_base)

        for task_name, missing_vars in validation_results.items():
            if missing_vars:
                # Build suggestions for this task's missing variables
                task_suggestions = {}
                for var_name in missing_vars:
                    if var_name in suggestions:
                        task_suggestions[var_name] = suggestions[var_name]

                error_details = {
                    "missing_variables": sorted(list(missing_vars)),
                }
                if task_suggestions:
                    error_details["suggestions"] = task_suggestions

                self.errors.append(
                    DependencyError(
                        error_type="missing_variable",
                        task_name=task_name,
                        message=f"Task '{task_name}' requires variables that are not defined: {', '.join(sorted(missing_vars))}",
                        details=error_details,
                    )
                )

    def collect_missing_dependencies(
        self, dependency_map: DependencyMap
    ) -> None:
        """Collect missing dependency errors (tasks depending on non-existent resources).

        Args:
            dependency_map: The dependency map to validate.
        """
        # Build map of resources to tasks that provide them
        resource_to_tasks: Dict[str, List[str]] = {}
        for task in dependency_map.tasks:
            for resource in task.provides:
                if resource not in resource_to_tasks:
                    resource_to_tasks[resource] = []
                resource_to_tasks[resource].append(task.name)

        # Check for missing dependencies
        for task in dependency_map.tasks:
            for required_resource in task.depends_on:
                if required_resource not in resource_to_tasks:
                    self.errors.append(
                        DependencyError(
                            error_type="missing_dependency",
                            task_name=task.name,
                            message=f"Task '{task.name}' depends on resource '{required_resource}' but no task provides it",
                            details={
                                "required_resource": required_resource,
                                "available_resources": sorted(list(resource_to_tasks.keys())),
                            },
                        )
                    )

    def collect_missing_triggers(self, dependency_map: DependencyMap) -> None:
        """Collect missing trigger errors (tasks triggering non-existent tasks).

        Args:
            dependency_map: The dependency map to validate.
        """
        all_task_names = {task.name for task in dependency_map.tasks}

        for task in dependency_map.tasks:
            for triggered_task_name in task.triggers:
                if triggered_task_name not in all_task_names:
                    self.errors.append(
                        DependencyError(
                            error_type="missing_trigger",
                            task_name=task.name,
                            message=f"Task '{task.name}' triggers '{triggered_task_name}' but that task does not exist",
                            details={
                                "triggered_task": triggered_task_name,
                                "available_tasks": sorted(list(all_task_names)),
                            },
                        )
                    )

    def collect_circular_dependencies(
        self, dependency_map: DependencyMap
    ) -> None:
        """Collect circular dependency errors.

        Args:
            dependency_map: The dependency map to validate.
        """
        try:
            from said.dag_builder import CycleDetectedError, DependencyGraph

            try:
                graph = DependencyGraph(dependency_map)
                # If we get here, no cycles were detected
            except CycleDetectedError as e:
                # Extract cycle information from error message
                error_msg = str(e)
                # Try to parse cycles from the error message
                cycles = []
                if "Circular dependency" in error_msg:
                    # Extract cycle paths from error message
                    lines = error_msg.split("\n")
                    for line in lines:
                        if "->" in line and line.strip().startswith("-"):
                            cycle_path = line.strip()[2:].strip()  # Remove "- " prefix
                            cycles.append(cycle_path)

                self.errors.append(
                    DependencyError(
                        error_type="circular_dependency",
                        task_name="multiple",
                        message=error_msg,
                        details={
                            "error_details": error_msg,
                            "cycles": cycles if cycles else [error_msg],
                        },
                    )
                )
        except Exception as e:
            # Fallback for any other errors during cycle detection
            error_msg = str(e)
            if "circular" in error_msg.lower() or "cycle" in error_msg.lower():
                self.errors.append(
                    DependencyError(
                        error_type="circular_dependency",
                        task_name="multiple",
                        message=error_msg,
                        details={"error_details": error_msg},
                    )
                )

    def collect_invalid_task_references(
        self, task_names: Set[str], dependency_map: DependencyMap
    ) -> None:
        """Collect errors for task names that don't exist in the dependency map.

        Args:
            task_names: Set of task names to check.
            dependency_map: The dependency map to validate against.
        """
        all_task_names = {task.name for task in dependency_map.tasks}
        invalid_tasks = task_names - all_task_names

        for invalid_task in invalid_tasks:
            self.errors.append(
                DependencyError(
                    error_type="invalid_task_reference",
                    task_name=invalid_task,
                    message=f"Task '{invalid_task}' is referenced but does not exist in dependency map",
                    details={
                        "referenced_task": invalid_task,
                        "available_tasks": sorted(list(all_task_names)),
                    },
                )
            )

    def generate_report(self) -> DependencyErrorReport:
        """Generate a comprehensive error report.

        Returns:
            DependencyErrorReport with all collected errors.
        """
        # Count errors by type
        error_summary = {}
        for error in self.errors:
            error_summary[error.error_type] = error_summary.get(error.error_type, 0) + 1

        return DependencyErrorReport(
            errors=self.errors,
            total_errors=len(self.errors),
            error_summary=error_summary,
        )

    def has_errors(self) -> bool:
        """Check if any errors were collected.

        Returns:
            True if errors exist, False otherwise.
        """
        return len(self.errors) > 0


def validate_dependency_map_comprehensive(
    dependency_map: DependencyMap,
    task_names: Optional[Set[str]] = None,
    variables: Optional[Dict] = None,
    search_base: Optional[Path] = None,
    search_for_suggestions: bool = True,
) -> DependencyErrorReport:
    """Comprehensively validate a dependency map and collect all errors.

    This function checks for:
    - Missing variables
    - Missing dependencies (resources that don't exist)
    - Missing triggers (tasks that don't exist)
    - Circular dependencies
    - Invalid task references

    Args:
        dependency_map: The dependency map to validate.
        task_names: Optional set of task names to validate. If None, validates all tasks.
        variables: Optional dictionary of available variables for validation.
        search_base: Base directory to search for variable definitions. Defaults to current directory.
        search_for_suggestions: If True, search for where missing variables might be defined.

    Returns:
        DependencyErrorReport containing all discovered errors.
    """
    collector = DependencyErrorCollector()

    # Collect missing dependencies
    collector.collect_missing_dependencies(dependency_map)

    # Collect missing triggers
    collector.collect_missing_triggers(dependency_map)

    # Collect circular dependencies
    collector.collect_circular_dependencies(dependency_map)

    # Collect invalid task references if task_names provided
    if task_names:
        collector.collect_invalid_task_references(task_names, dependency_map)

    # Collect missing variables if variables provided
    if variables:
        from said.validator import VariableValidator

        validator = VariableValidator(variables)
        if task_names:
            validation_results = validator.validate_dependency_map(
                dependency_map, task_names
            )
        else:
            # Validate all tasks
            all_task_names = {task.name for task in dependency_map.tasks}
            validation_results = validator.validate_dependency_map(
                dependency_map, all_task_names
            )
        collector.collect_missing_variables(
            validation_results,
            search_base=search_base,
            search_for_suggestions=search_for_suggestions,
        )

    return collector.generate_report()
