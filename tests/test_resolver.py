"""Unit tests for resolver module."""

import pytest

from said.resolver import (
    DependencyResolver,
    ResolverError,
    resolve_dependencies,
)
from said.schema import DependencyMap, TaskMetadata


class TestDependencyResolver:
    """Test cases for DependencyResolver class."""

    def test_resolve_simple_dependencies(self):
        """Test resolving simple dependencies."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        # If task2 is matched, task1 should be included
        result = resolver.resolve({"task2"})
        assert "task1" in result
        assert "task2" in result
        assert result.index("task1") < result.index("task2")

    def test_resolve_transitive_dependencies(self):
        """Test resolving transitive dependencies."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource2"]
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        resolver = DependencyResolver(dep_map)

        # If task3 is matched, task1 and task2 should be included
        result = resolver.resolve({"task3"})
        assert "task1" in result
        assert "task2" in result
        assert "task3" in result
        assert result.index("task1") < result.index("task2")
        assert result.index("task2") < result.index("task3")

    def test_resolve_with_triggers(self):
        """Test resolving with triggers included."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        # If task1 is matched, task2 should be included (triggered)
        result = resolver.resolve({"task1"}, include_triggers=True)
        assert "task1" in result
        assert "task2" in result

    def test_resolve_without_triggers(self):
        """Test resolving without triggers."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        # If task1 is matched, task2 should NOT be included (triggers disabled)
        result = resolver.resolve({"task1"}, include_triggers=False)
        assert "task1" in result
        assert "task2" not in result

    def test_resolve_multiple_matched_tasks(self):
        """Test resolving when multiple tasks are matched."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(name="task3", provides=["resource3"])

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        resolver = DependencyResolver(dep_map)

        # If both task2 and task3 are matched
        result = resolver.resolve({"task2", "task3"})
        assert "task1" in result  # Dependency of task2
        assert "task2" in result
        assert "task3" in result

    def test_resolve_empty_set(self):
        """Test resolving with empty matched tasks."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        dep_map = DependencyMap(tasks=[task1])
        resolver = DependencyResolver(dep_map)

        result = resolver.resolve(set())
        assert len(result) == 0

    def test_resolve_invalid_task(self):
        """Test resolving with invalid task name."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        dep_map = DependencyMap(tasks=[task1])
        resolver = DependencyResolver(dep_map)

        with pytest.raises(ResolverError) as exc_info:
            resolver.resolve({"nonexistent"})
        assert "not found" in str(exc_info.value).lower()

    def test_resolve_cycle_detection(self):
        """Test that cycles are detected during resolution."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], depends_on=["resource2"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])

        with pytest.raises(ResolverError) as exc_info:
            DependencyResolver(dep_map)
        assert "circular dependency" in str(exc_info.value).lower()

    def test_get_task_dependencies(self):
        """Test getting dependencies for a single task."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        deps = resolver.get_task_dependencies("task2")
        assert "task1" in deps

    def test_get_task_triggers(self):
        """Test getting triggers for a single task."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        triggers = resolver.get_task_triggers("task1")
        assert "task2" in triggers

    def test_resolve_dependencies_only(self):
        """Test resolve_dependencies_only convenience method."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        result = resolver.resolve_dependencies_only({"task1"})
        assert "task1" in result
        assert "task2" not in result  # Triggers not included

    def test_resolve_with_triggers_method(self):
        """Test resolve_with_triggers convenience method."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        resolver = DependencyResolver(dep_map)

        result = resolver.resolve_with_triggers({"task1"})
        assert "task1" in result
        assert "task2" in result  # Triggers included


class TestResolveDependenciesFunction:
    """Test cases for resolve_dependencies convenience function."""

    def test_resolve_dependencies_function(self):
        """Test the resolve_dependencies convenience function."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])

        result = resolve_dependencies({"task2"}, dep_map)
        assert "task1" in result
        assert "task2" in result

    def test_resolve_dependencies_with_triggers(self):
        """Test resolve_dependencies with triggers."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])

        result = resolve_dependencies({"task1"}, dep_map, include_triggers=True)
        assert "task1" in result
        assert "task2" in result
