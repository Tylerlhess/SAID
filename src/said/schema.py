"""Schema and validation for dependency map configuration.

This module defines data models for the dependency map structure and provides
validation logic to ensure configuration correctness.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set


class SchemaError(Exception):
    """Base exception for schema validation errors."""

    pass


@dataclass
class TaskMetadata:
    """Metadata for a single Ansible task in the dependency map.

    Attributes:
        name: Unique name/identifier for the task.
        provides: List of resources or capabilities this task provides.
        requires_vars: List of Ansible variable names required by this task.
        triggers: List of task names that should be triggered after this task.
        watch_files: List of file paths/patterns this task watches for changes.
        depends_on: List of resources (from 'provides' of other tasks) this task depends on.
    """

    name: str
    provides: List[str] = field(default_factory=list)
    requires_vars: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    watch_files: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate task metadata after initialization."""
        if not self.name or not isinstance(self.name, str):
            raise SchemaError("Task 'name' must be a non-empty string")

        # Ensure all list fields are lists
        if not isinstance(self.provides, list):
            raise SchemaError("Task 'provides' must be a list")
        if not isinstance(self.requires_vars, list):
            raise SchemaError("Task 'requires_vars' must be a list")
        if not isinstance(self.triggers, list):
            raise SchemaError("Task 'triggers' must be a list")
        if not isinstance(self.watch_files, list):
            raise SchemaError("Task 'watch_files' must be a list")
        if not isinstance(self.depends_on, list):
            raise SchemaError("Task 'depends_on' must be a list")

        # Ensure all list items are strings
        for field_name, field_value in [
            ("provides", self.provides),
            ("requires_vars", self.requires_vars),
            ("triggers", self.triggers),
            ("watch_files", self.watch_files),
            ("depends_on", self.depends_on),
        ]:
            if not all(isinstance(item, str) for item in field_value):
                raise SchemaError(f"All items in '{field_name}' must be strings")

        # Validate that provides is not empty (tasks should provide something)
        if not self.provides:
            raise SchemaError(
                f"Task '{self.name}' must provide at least one resource. "
                "Use a descriptive identifier for what this task provides."
            )


@dataclass
class DependencyMap:
    """Complete dependency map structure.

    Attributes:
        tasks: List of task metadata definitions.
    """

    tasks: List[TaskMetadata] = field(default_factory=list)

    def __post_init__(self):
        """Validate dependency map after initialization."""
        if not isinstance(self.tasks, list):
            raise SchemaError("Dependency map 'tasks' must be a list")

        if not self.tasks:
            raise SchemaError("Dependency map must contain at least one task")

        # Validate all tasks are TaskMetadata instances
        for task in self.tasks:
            if not isinstance(task, TaskMetadata):
                raise SchemaError(
                    f"All items in 'tasks' must be TaskMetadata instances, "
                    f"got {type(task).__name__}"
                )

        # Check for duplicate task names
        task_names = [task.name for task in self.tasks]
        if len(task_names) != len(set(task_names)):
            duplicates = [
                name for name in task_names if task_names.count(name) > 1
            ]
            raise SchemaError(
                f"Duplicate task names found: {set(duplicates)}. "
                "Each task must have a unique name."
            )

        # Validate that all 'triggers' reference existing task names
        all_task_names = set(task_names)
        for task in self.tasks:
            invalid_triggers = set(task.triggers) - all_task_names
            if invalid_triggers:
                raise SchemaError(
                    f"Task '{task.name}' triggers non-existent tasks: {invalid_triggers}"
                )

        # Validate that all 'depends_on' reference existing 'provides' values
        all_provides = set()
        for task in self.tasks:
            all_provides.update(task.provides)

        for task in self.tasks:
            invalid_deps = set(task.depends_on) - all_provides
            if invalid_deps:
                raise SchemaError(
                    f"Task '{task.name}' depends on non-existent resources: {invalid_deps}. "
                    "Available resources: " + ", ".join(sorted(all_provides))
                )

    def get_task_by_name(self, name: str) -> Optional[TaskMetadata]:
        """Get a task by its name.

        Args:
            name: Task name to look up.

        Returns:
            TaskMetadata instance if found, None otherwise.
        """
        for task in self.tasks:
            if task.name == name:
                return task
        return None

    def get_all_provides(self) -> Set[str]:
        """Get all resources provided by all tasks.

        Returns:
            Set of all resource names provided by tasks.
        """
        all_provides = set()
        for task in self.tasks:
            all_provides.update(task.provides)
        return all_provides

    def get_all_task_names(self) -> Set[str]:
        """Get all task names.

        Returns:
            Set of all task names.
        """
        return {task.name for task in self.tasks}


def validate_task_metadata(data: dict) -> TaskMetadata:
    """Create and validate a TaskMetadata instance from a dictionary.

    Args:
        data: Dictionary containing task metadata.

    Returns:
        Validated TaskMetadata instance.

    Raises:
        SchemaError: If validation fails.
    """
    try:
        return TaskMetadata(
            name=data.get("name", ""),
            provides=data.get("provides", []),
            requires_vars=data.get("requires_vars", []),
            triggers=data.get("triggers", []),
            watch_files=data.get("watch_files", []),
            depends_on=data.get("depends_on", []),
        )
    except SchemaError:
        raise
    except Exception as e:
        raise SchemaError(f"Failed to create TaskMetadata: {e}")


def validate_dependency_map(data: dict) -> DependencyMap:
    """Create and validate a DependencyMap instance from a dictionary.

    Args:
        data: Dictionary containing dependency map structure.

    Returns:
        Validated DependencyMap instance.

    Raises:
        SchemaError: If validation fails.
    """
    try:
        tasks_data = data.get("tasks", [])
        if not isinstance(tasks_data, list):
            raise SchemaError("'tasks' must be a list")

        tasks = []
        for i, task_data in enumerate(tasks_data):
            try:
                task = validate_task_metadata(task_data)
                tasks.append(task)
            except SchemaError as e:
                raise SchemaError(f"Error validating task at index {i}: {e}")

        return DependencyMap(tasks=tasks)
    except SchemaError:
        raise
    except Exception as e:
        raise SchemaError(f"Failed to create DependencyMap: {e}")
