"""Unit tests for dag_builder module."""

import pytest

from said.dag_builder import CycleDetectedError, DAGError, DependencyGraph
from said.schema import DependencyMap, TaskMetadata


class TestDependencyGraph:
    """Test cases for DependencyGraph class."""

    def test_build_simple_graph(self):
        """Test building a simple dependency graph."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["file1.yml"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])
        graph = DependencyGraph(dep_map)

        assert "task1" in graph.get_all_tasks()
        assert "task2" in graph.get_all_tasks()

    def test_get_dependencies(self):
        """Test getting direct dependencies."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])
        graph = DependencyGraph(dep_map)

        deps = graph.get_dependencies("task2")
        assert "task1" in deps
        assert "task2" not in deps

    def test_get_all_dependencies(self):
        """Test getting transitive dependencies."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource2"]
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        graph = DependencyGraph(dep_map)

        all_deps = graph.get_all_dependencies("task3")
        assert "task1" in all_deps
        assert "task2" in all_deps
        assert "task3" not in all_deps

    def test_get_dependents(self):
        """Test getting direct dependents."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])
        graph = DependencyGraph(dep_map)

        dependents = graph.get_dependents("task1")
        assert "task2" in dependents

    def test_get_all_dependents(self):
        """Test getting transitive dependents."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource2"]
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        graph = DependencyGraph(dep_map)

        all_dependents = graph.get_all_dependents("task1")
        assert "task2" in all_dependents
        assert "task3" in all_dependents

    def test_triggers_create_edges(self):
        """Test that triggers create dependency edges."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], triggers=["task2"]
        )
        task2 = TaskMetadata(name="task2", provides=["resource2"])

        dep_map = DependencyMap(tasks=[task1, task2])
        graph = DependencyGraph(dep_map)

        # task2 should depend on task1 (because task1 triggers task2)
        deps = graph.get_dependencies("task2")
        assert "task1" in deps

    def test_topological_sort(self):
        """Test topological sorting."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource2"]
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        graph = DependencyGraph(dep_map)

        order = graph.topological_sort()
        assert order.index("task1") < order.index("task2")
        assert order.index("task2") < order.index("task3")

    def test_get_execution_order(self):
        """Test getting execution order for specific tasks."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource2"]
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3])
        graph = DependencyGraph(dep_map)

        # If we want to execute task3, we need task1 and task2 first
        order = graph.get_execution_order({"task3"})
        assert "task1" in order
        assert "task2" in order
        assert "task3" in order
        assert order.index("task1") < order.index("task2")
        assert order.index("task2") < order.index("task3")

    def test_cycle_detection(self):
        """Test that cycles are detected."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], depends_on=["resource2"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1, task2])

        with pytest.raises(CycleDetectedError) as exc_info:
            DependencyGraph(dep_map)
        assert "circular dependency" in str(exc_info.value).lower()

    def test_self_loop_prevention(self):
        """Test that self-loops are prevented."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], depends_on=["resource1"]
        )

        dep_map = DependencyMap(tasks=[task1])
        graph = DependencyGraph(dep_map)

        # Should not have self as dependency
        deps = graph.get_dependencies("task1")
        assert "task1" not in deps

    def test_missing_resource_error(self):
        """Test error when task depends on non-existent resource.
        
        Note: This error is actually caught by schema validation before
        the DAG builder, so we test it at the schema level instead.
        """
        # The schema validation should catch this
        from said.schema import SchemaError
        
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], depends_on=["nonexistent"]
        )

        with pytest.raises(SchemaError) as exc_info:
            DependencyMap(tasks=[task1])
        assert "depends on non-existent resources" in str(exc_info.value).lower()

    def test_get_task(self):
        """Test getting a task from the graph."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        dep_map = DependencyMap(tasks=[task1])
        graph = DependencyGraph(dep_map)

        retrieved = graph.get_task("task1")
        assert retrieved == task1

    def test_get_task_not_found(self):
        """Test getting a non-existent task."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        dep_map = DependencyMap(tasks=[task1])
        graph = DependencyGraph(dep_map)

        with pytest.raises(DAGError) as exc_info:
            graph.get_task("nonexistent")
        assert "not found" in str(exc_info.value).lower()

    def test_complex_dependency_graph(self):
        """Test a complex dependency graph."""
        task1 = TaskMetadata(name="task1", provides=["resource1"])
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], depends_on=["resource1"]
        )
        task3 = TaskMetadata(
            name="task3", provides=["resource3"], depends_on=["resource1"]
        )
        task4 = TaskMetadata(
            name="task4",
            provides=["resource4"],
            depends_on=["resource2", "resource3"],
        )

        dep_map = DependencyMap(tasks=[task1, task2, task3, task4])
        graph = DependencyGraph(dep_map)

        # task4 depends on both task2 and task3
        deps = graph.get_dependencies("task4")
        assert "task2" in deps
        assert "task3" in deps

        # Both task2 and task3 depend on task1
        assert "task1" in graph.get_dependencies("task2")
        assert "task1" in graph.get_dependencies("task3")

        # task4 transitively depends on task1
        all_deps = graph.get_all_dependencies("task4")
        assert "task1" in all_deps
