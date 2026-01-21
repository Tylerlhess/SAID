"""Variable validation for Ansible tasks.

This module provides functionality to validate that all required variables
are present before task execution, integrating with Ansible hostvars or inventory.
"""

from typing import Dict, List, Set

from said.schema import DependencyMap, TaskMetadata


class ValidationError(Exception):
    """Base exception for validation errors."""

    pass


class MissingVariableError(ValidationError):
    """Raised when a required variable is missing."""

    def __init__(self, task_name: str, missing_vars: Set[str]):
        """Initialize the error with task name and missing variables.

        Args:
            task_name: Name of the task with missing variables.
            missing_vars: Set of variable names that are missing.
        """
        self.task_name = task_name
        self.missing_vars = missing_vars
        super().__init__(
            f"Task '{task_name}' requires variables that are not defined: "
            f"{', '.join(sorted(missing_vars))}"
        )


class VariableValidator:
    """Validates that required variables are present for tasks."""

    def __init__(self, variables: Dict[str, any]):
        """Initialize the variable validator.

        Args:
            variables: Dictionary of available variables (e.g., from Ansible hostvars).
                      Keys are variable names, values are their values.
        """
        self.variables = variables or {}

    def validate_task(self, task: TaskMetadata) -> List[str]:
        """Validate that all required variables for a task are present.

        Args:
            task: The task to validate.

        Returns:
            List of missing variable names (empty if all are present).

        Raises:
            ValidationError: If validation fails.
        """
        missing = []

        for var_name in task.requires_vars:
            if var_name not in self.variables:
                missing.append(var_name)
            elif self.variables[var_name] is None:
                # Treat None as missing
                missing.append(var_name)

        return missing

    def validate_tasks(
        self, tasks: List[TaskMetadata]
    ) -> Dict[str, Set[str]]:
        """Validate multiple tasks and return all missing variables.

        Args:
            tasks: List of tasks to validate.

        Returns:
            Dictionary mapping task names to sets of missing variable names.
            Tasks with no missing variables will have empty sets.
        """
        results = {}

        for task in tasks:
            missing = self.validate_task(task)
            results[task.name] = set(missing)

        return results

    def validate_dependency_map(
        self, dependency_map: DependencyMap, task_names: Set[str]
    ) -> Dict[str, Set[str]]:
        """Validate required variables for a set of tasks from a dependency map.

        Args:
            dependency_map: The dependency map containing tasks.
            task_names: Set of task names to validate.

        Returns:
            Dictionary mapping task names to sets of missing variable names.

        Raises:
            ValidationError: If any task is not found in the dependency map.
        """
        tasks_to_validate = []

        for task_name in task_names:
            task = dependency_map.get_task_by_name(task_name)
            if task is None:
                raise ValidationError(
                    f"Task '{task_name}' not found in dependency map"
                )
            tasks_to_validate.append(task)

        return self.validate_tasks(tasks_to_validate)

    def check_all_required(
        self, dependency_map: DependencyMap, task_names: Set[str]
    ) -> None:
        """Check that all required variables are present, raising an error if not.

        Args:
            dependency_map: The dependency map containing tasks.
            task_names: Set of task names to validate.

        Raises:
            MissingVariableError: If any required variables are missing.
            ValidationError: If any task is not found.
        """
        validation_results = self.validate_dependency_map(
            dependency_map, task_names
        )

        # Collect all errors
        errors = []
        for task_name, missing_vars in validation_results.items():
            if missing_vars:
                errors.append((task_name, missing_vars))

        if errors:
            # If multiple tasks have errors, raise for the first one
            # (caller can check all if needed)
            task_name, missing_vars = errors[0]
            raise MissingVariableError(task_name, missing_vars)


def validate_variables(
    dependency_map: DependencyMap,
    task_names: Set[str],
    variables: Dict[str, any],
) -> Dict[str, Set[str]]:
    """Convenience function to validate variables for tasks.

    Args:
        dependency_map: The dependency map containing tasks.
        task_names: Set of task names to validate.
        variables: Dictionary of available variables.

    Returns:
        Dictionary mapping task names to sets of missing variable names.
    """
    validator = VariableValidator(variables)
    return validator.validate_dependency_map(dependency_map, task_names)


def check_variables_required(
    dependency_map: DependencyMap,
    task_names: Set[str],
    variables: Dict[str, any],
) -> None:
    """Convenience function to check required variables, raising an error if missing.

    Args:
        dependency_map: The dependency map containing tasks.
        task_names: Set of task names to validate.
        variables: Dictionary of available variables.

    Raises:
        MissingVariableError: If any required variables are missing.
    """
    validator = VariableValidator(variables)
    validator.check_all_required(dependency_map, task_names)


def load_variables_from_ansible_inventory(
    inventory_path: str,
) -> Dict[str, any]:
    """Load variables from an Ansible inventory file.

    This is a basic implementation that reads YAML/INI inventory files.
    For production use, consider using ansible-inventory command or
    Ansible's inventory API.

    Args:
        inventory_path: Path to the Ansible inventory file.

    Returns:
        Dictionary of variables (simplified - may need enhancement for production).

    Raises:
        ValidationError: If the inventory file cannot be read or parsed.
    """
    import yaml
    from pathlib import Path

    inventory_file = Path(inventory_path)

    if not inventory_file.exists():
        raise ValidationError(f"Inventory file not found: {inventory_path}")

    try:
        with open(inventory_file, "r", encoding="utf-8") as f:
            # This is a simplified parser - real Ansible inventory parsing
            # is more complex and may require ansible-inventory command
            content = yaml.safe_load(f)
            if isinstance(content, dict):
                # Extract variables from inventory structure
                # This is a basic implementation
                variables = {}
                if "all" in content and "vars" in content["all"]:
                    variables.update(content["all"]["vars"])
                return variables
            return {}
    except Exception as e:
        raise ValidationError(f"Failed to load inventory file: {e}")
