"""Unit tests for validator module."""

import pytest

from said.schema import DependencyMap, TaskMetadata
from said.validator import (
    MissingVariableError,
    ValidationError,
    VariableValidator,
    check_variables_required,
    validate_variables,
)


class TestVariableValidator:
    """Test cases for VariableValidator class."""

    def test_validate_task_all_present(self):
        """Test validating a task with all variables present."""
        task = TaskMetadata(
            name="task1",
            provides=["resource1"],
            requires_vars=["var1", "var2"],
        )
        variables = {"var1": "value1", "var2": "value2"}

        validator = VariableValidator(variables)
        missing = validator.validate_task(task)
        assert len(missing) == 0

    def test_validate_task_missing_variables(self):
        """Test validating a task with missing variables."""
        task = TaskMetadata(
            name="task1",
            provides=["resource1"],
            requires_vars=["var1", "var2", "var3"],
        )
        variables = {"var1": "value1"}  # Missing var2 and var3

        validator = VariableValidator(variables)
        missing = validator.validate_task(task)
        assert "var2" in missing
        assert "var3" in missing
        assert "var1" not in missing

    def test_validate_task_none_value(self):
        """Test that None values are treated as missing."""
        task = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        variables = {"var1": None}

        validator = VariableValidator(variables)
        missing = validator.validate_task(task)
        assert "var1" in missing

    def test_validate_task_no_required_vars(self):
        """Test validating a task with no required variables."""
        task = TaskMetadata(name="task1", provides=["resource1"])
        variables = {}

        validator = VariableValidator(variables)
        missing = validator.validate_task(task)
        assert len(missing) == 0

    def test_validate_tasks(self):
        """Test validating multiple tasks."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], requires_vars=["var2"]
        )
        variables = {"var1": "value1"}  # Missing var2

        validator = VariableValidator(variables)
        results = validator.validate_tasks([task1, task2])

        assert len(results["task1"]) == 0
        assert "var2" in results["task2"]

    def test_validate_dependency_map(self):
        """Test validating tasks from a dependency map."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], requires_vars=["var2"]
        )
        dep_map = DependencyMap(tasks=[task1, task2])
        variables = {"var1": "value1"}  # Missing var2

        validator = VariableValidator(variables)
        results = validator.validate_dependency_map(dep_map, {"task1", "task2"})

        assert len(results["task1"]) == 0
        assert "var2" in results["task2"]

    def test_validate_dependency_map_invalid_task(self):
        """Test validating with invalid task name."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}

        validator = VariableValidator(variables)

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_dependency_map(dep_map, {"nonexistent"})
        assert "not found" in str(exc_info.value).lower()

    def test_check_all_required_success(self):
        """Test check_all_required when all variables are present."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}

        validator = VariableValidator(variables)
        # Should not raise
        validator.check_all_required(dep_map, {"task1"})

    def test_check_all_required_failure(self):
        """Test check_all_required when variables are missing."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1", "var2"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}  # Missing var2

        validator = VariableValidator(variables)

        with pytest.raises(MissingVariableError) as exc_info:
            validator.check_all_required(dep_map, {"task1"})
        assert "var2" in str(exc_info.value)
        assert exc_info.value.task_name == "task1"
        assert "var2" in exc_info.value.missing_vars


class TestValidateVariablesFunction:
    """Test cases for validate_variables convenience function."""

    def test_validate_variables_function(self):
        """Test the validate_variables convenience function."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}

        results = validate_variables(dep_map, {"task1"}, variables)
        assert len(results["task1"]) == 0

    def test_validate_variables_missing(self):
        """Test validate_variables with missing variables."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1", "var2"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}  # Missing var2

        results = validate_variables(dep_map, {"task1"}, variables)
        assert "var2" in results["task1"]


class TestCheckVariablesRequiredFunction:
    """Test cases for check_variables_required convenience function."""

    def test_check_variables_required_success(self):
        """Test check_variables_required when all variables are present."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}

        # Should not raise
        check_variables_required(dep_map, {"task1"}, variables)

    def test_check_variables_required_failure(self):
        """Test check_variables_required when variables are missing."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], requires_vars=["var1", "var2"]
        )
        dep_map = DependencyMap(tasks=[task1])
        variables = {"var1": "value1"}  # Missing var2

        with pytest.raises(MissingVariableError):
            check_variables_required(dep_map, {"task1"}, variables)
