"""Unit tests for schema module."""

import pytest

from said.schema import (
    DependencyMap,
    SchemaError,
    TaskMetadata,
    validate_dependency_map,
    validate_task_metadata,
)


class TestTaskMetadata:
    """Test cases for TaskMetadata class."""

    def test_create_valid_task(self):
        """Test creating a valid task metadata."""
        task = TaskMetadata(
            name="test_task",
            provides=["resource1"],
            requires_vars=["var1", "var2"],
            triggers=["other_task"],
            watch_files=["file1.yml", "file2.yml"],
            depends_on=["resource0"],
        )

        assert task.name == "test_task"
        assert task.provides == ["resource1"]
        assert task.requires_vars == ["var1", "var2"]
        assert task.triggers == ["other_task"]
        assert task.watch_files == ["file1.yml", "file2.yml"]
        assert task.depends_on == ["resource0"]

    def test_create_task_with_defaults(self):
        """Test creating a task with default values."""
        task = TaskMetadata(name="test_task", provides=["resource1"])

        assert task.name == "test_task"
        assert task.provides == ["resource1"]
        assert task.requires_vars == []
        assert task.triggers == []
        assert task.watch_files == []
        assert task.depends_on == []

    def test_task_must_have_name(self):
        """Test that task must have a non-empty name."""
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(name="", provides=["resource1"])
        assert "name" in str(exc_info.value).lower()

        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(name=None, provides=["resource1"])
        assert "name" in str(exc_info.value).lower()

    def test_task_must_provide_something(self):
        """Test that task must provide at least one resource."""
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(name="test_task", provides=[])
        assert "must provide" in str(exc_info.value).lower()

    def test_task_fields_must_be_lists(self):
        """Test that all list fields must be lists."""
        task_data = {"name": "test_task", "provides": ["resource1"]}

        # Test provides
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(name=task_data["name"], provides="not_a_list")
        assert "must be a list" in str(exc_info.value).lower()

        # Test requires_vars
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(
                name=task_data["name"],
                provides=task_data["provides"],
                requires_vars="not_a_list",
            )
        assert "must be a list" in str(exc_info.value).lower()

        # Test triggers
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(
                name=task_data["name"],
                provides=task_data["provides"],
                triggers="not_a_list",
            )
        assert "must be a list" in str(exc_info.value).lower()

        # Test watch_files
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(
                name=task_data["name"],
                provides=task_data["provides"],
                watch_files="not_a_list",
            )
        assert "must be a list" in str(exc_info.value).lower()

        # Test depends_on
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(
                name=task_data["name"],
                provides=task_data["provides"],
                depends_on="not_a_list",
            )
        assert "must be a list" in str(exc_info.value).lower()

    def test_task_list_items_must_be_strings(self):
        """Test that all list items must be strings."""
        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(name="test_task", provides=["resource1", 123])
        assert "must be strings" in str(exc_info.value).lower()

        with pytest.raises(SchemaError) as exc_info:
            TaskMetadata(
                name="test_task", provides=["resource1"], requires_vars=["var1", None]
            )
        assert "must be strings" in str(exc_info.value).lower()


class TestDependencyMap:
    """Test cases for DependencyMap class."""

    def test_create_valid_dependency_map(self):
        """Test creating a valid dependency map."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["file1.yml"]
        )
        task2 = TaskMetadata(
            name="task2",
            provides=["resource2"],
            depends_on=["resource1"],
            triggers=["task1"],
        )

        dep_map = DependencyMap(tasks=[task1, task2])

        assert len(dep_map.tasks) == 2
        assert dep_map.get_task_by_name("task1") == task1
        assert dep_map.get_task_by_name("task2") == task2

    def test_dependency_map_must_have_tasks(self):
        """Test that dependency map must have at least one task."""
        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[])
        assert "at least one task" in str(exc_info.value).lower()

    def test_dependency_map_tasks_must_be_list(self):
        """Test that tasks must be a list."""
        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks="not_a_list")
        assert "must be a list" in str(exc_info.value).lower()

    def test_dependency_map_tasks_must_be_task_metadata(self):
        """Test that all tasks must be TaskMetadata instances."""
        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[{"name": "task1", "provides": ["r1"]}])
        assert "TaskMetadata instances" in str(exc_info.value)

    def test_no_duplicate_task_names(self):
        """Test that task names must be unique."""
        task1 = TaskMetadata(name="duplicate", provides=["resource1"])
        task2 = TaskMetadata(name="duplicate", provides=["resource2"])

        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[task1, task2])
        assert "Duplicate task names" in str(exc_info.value)

    def test_triggers_must_reference_existing_tasks(self):
        """Test that triggers must reference existing task names."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["nonexistent_task"]
        )

        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[task1])
        assert "triggers non-existent tasks" in str(exc_info.value).lower()

    def test_depends_on_must_reference_existing_provides(self):
        """Test that depends_on must reference existing provides."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], depends_on=["nonexistent_resource"]
        )

        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[task1])
        assert "depends on non-existent resources" in str(exc_info.value).lower()

    def test_valid_triggers_and_depends_on(self):
        """Test valid triggers and depends_on references."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2",
            provides=["resource2"],
            depends_on=["resource1"],
            triggers=["task1"],
        )

        # Should not raise an error
        dep_map = DependencyMap(tasks=[task1, task2])
        assert len(dep_map.tasks) == 2

    def test_get_task_by_name(self):
        """Test getting a task by name."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])

        assert dep_map.get_task_by_name("task1") == task1
        assert dep_map.get_task_by_name("task2") == task2
        assert dep_map.get_task_by_name("nonexistent") is None

    def test_get_all_provides(self):
        """Test getting all provided resources."""
        task1 = TaskMetadata(name="task1", provides=["resource1", "resource2"])
        task2 = TaskMetadata(name="task2", provides=["resource3"])

        dep_map = DependencyMap(tasks=[task1, task2])

        all_provides = dep_map.get_all_provides()
        assert all_provides == {"resource1", "resource2", "resource3"}

    def test_get_all_task_names(self):
        """Test getting all task names."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])

        all_names = dep_map.get_all_task_names()
        assert all_names == {"task1", "task2"}

    def test_complex_valid_dependency_map(self):
        """Test a complex but valid dependency map."""
        task1 = TaskMetadata(
            name="generate_config",
            provides=["config_file"],
            watch_files=["templates/config.j2"],
            requires_vars=["app_name", "app_port"],
        )
        task2 = TaskMetadata(
            name="restart_service",
            provides=["service_state"],
            depends_on=["config_file"],
            triggers=["generate_config"],
        )
        task3 = TaskMetadata(
            name="verify_service",
            provides=["verification"],
            depends_on=["service_state"],
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])

        assert len(dep_map.tasks) == 3
        assert dep_map.get_all_provides() == {
            "config_file",
            "service_state",
            "verification",
        }


class TestValidateTaskMetadata:
    """Test cases for validate_task_metadata function."""

    def test_validate_valid_task(self):
        """Test validating a valid task dictionary."""
        data = {
            "name": "test_task",
            "provides": ["resource1"],
            "requires_vars": ["var1"],
            "triggers": ["other_task"],
            "watch_files": ["file1.yml"],
            "depends_on": ["resource0"],
        }

        task = validate_task_metadata(data)
        assert isinstance(task, TaskMetadata)
        assert task.name == "test_task"
        assert task.provides == ["resource1"]

    def test_validate_task_with_missing_fields(self):
        """Test validating a task with missing optional fields."""
        data = {"name": "test_task", "provides": ["resource1"]}

        task = validate_task_metadata(data)
        assert isinstance(task, TaskMetadata)
        assert task.requires_vars == []
        assert task.triggers == []

    def test_validate_task_invalid_data(self):
        """Test validating invalid task data."""
        # Missing name
        with pytest.raises(SchemaError):
            validate_task_metadata({"provides": ["resource1"]})

        # Empty provides
        with pytest.raises(SchemaError):
            validate_task_metadata({"name": "test", "provides": []})


class TestValidateDependencyMap:
    """Test cases for validate_dependency_map function."""

    def test_validate_valid_dependency_map(self):
        """Test validating a valid dependency map dictionary."""
        data = {
            "tasks": [
                {
                    "name": "task1",
                    "provides": ["resource1"],
                    "watch_files": ["file1.yml"],
                },
                {
                    "name": "task2",
                    "provides": ["resource2"],
                    "depends_on": ["resource1"],
                },
            ]
        }

        dep_map = validate_dependency_map(data)
        assert isinstance(dep_map, DependencyMap)
        assert len(dep_map.tasks) == 2

    def test_validate_dependency_map_empty_tasks(self):
        """Test validating dependency map with empty tasks."""
        with pytest.raises(SchemaError) as exc_info:
            validate_dependency_map({"tasks": []})
        assert "at least one task" in str(exc_info.value).lower()

    def test_validate_dependency_map_missing_tasks(self):
        """Test validating dependency map with missing tasks key."""
        with pytest.raises(SchemaError):
            validate_dependency_map({})

    def test_validate_dependency_map_invalid_task(self):
        """Test validating dependency map with invalid task."""
        data = {
            "tasks": [
                {"name": "task1", "provides": []},  # Invalid: empty provides
            ]
        }

        with pytest.raises(SchemaError) as exc_info:
            validate_dependency_map(data)
        assert "index 0" in str(exc_info.value).lower()

    def test_validate_dependency_map_invalid_triggers(self):
        """Test validating dependency map with invalid triggers."""
        data = {
            "tasks": [
                {
                    "name": "task1",
                    "provides": ["resource1"],
                    "triggers": ["nonexistent"],
                }
            ]
        }

        with pytest.raises(SchemaError) as exc_info:
            validate_dependency_map(data)
        assert "triggers non-existent tasks" in str(exc_info.value).lower()
