"""DAG (Directed Acyclic Graph) builder for dependency resolution.

This module uses NetworkX to build a directed graph from the dependency map,
enabling efficient dependency traversal and cycle detection.
"""

from typing import Dict, List, Set

import networkx as nx

from said.schema import DependencyMap, SchemaError, TaskMetadata


class DAGError(Exception):
    """Base exception for DAG-related errors."""

    pass


class CycleDetectedError(DAGError):
    """Raised when a cycle is detected in the dependency graph."""

    pass


class DependencyGraph:
    """A directed graph representing task dependencies.

    This class wraps a NetworkX DiGraph and provides methods for
    dependency resolution and traversal.
    """

    def __init__(self, dependency_map: DependencyMap):
        """Build a dependency graph from a DependencyMap.

        Args:
            dependency_map: The dependency map to build the graph from.

        Raises:
            CycleDetectedError: If a cycle is detected in the dependency graph.
            DAGError: If the graph cannot be constructed.
        """
        self.dependency_map = dependency_map
        self.graph = nx.DiGraph()
        self._build_graph()
        self._detect_cycles()

    def _build_graph(self):
        """Build the NetworkX graph from the dependency map."""
        # Add all tasks as nodes
        for task in self.dependency_map.tasks:
            self.graph.add_node(task.name, task=task)

        # Build edges based on dependencies
        # Map: resource -> list of tasks that provide it
        resource_to_tasks: Dict[str, List[str]] = {}
        for task in self.dependency_map.tasks:
            for resource in task.provides:
                if resource not in resource_to_tasks:
                    resource_to_tasks[resource] = []
                resource_to_tasks[resource].append(task.name)

        # Add edges for depends_on relationships
        for task in self.dependency_map.tasks:
            for required_resource in task.depends_on:
                if required_resource not in resource_to_tasks:
                    raise DAGError(
                        f"Task '{task.name}' depends on resource '{required_resource}' "
                        f"but no task provides it. Available resources: "
                        f"{', '.join(sorted(resource_to_tasks.keys()))}"
                    )

                # Task depends on all tasks that provide the required resource
                for provider_task_name in resource_to_tasks[required_resource]:
                    if provider_task_name != task.name:  # Avoid self-loops
                        self.graph.add_edge(provider_task_name, task.name)

        # Add edges for triggers relationships
        for task in self.dependency_map.tasks:
            for triggered_task_name in task.triggers:
                if triggered_task_name not in self.graph:
                    raise DAGError(
                        f"Task '{task.name}' triggers '{triggered_task_name}' "
                        "but that task does not exist in the dependency map."
                    )
                # Triggered task depends on the triggering task
                self.graph.add_edge(task.name, triggered_task_name)

    def _detect_cycles(self):
        """Detect cycles in the dependency graph.

        Raises:
            CycleDetectedError: If a cycle is detected.
        """
        try:
            cycles = list(nx.simple_cycles(self.graph))
            if cycles:
                cycle_strs = [" -> ".join(cycle) + f" -> {cycle[0]}" for cycle in cycles]
                raise CycleDetectedError(
                    f"Circular dependency detected in dependency graph:\n"
                    + "\n".join(f"  - {cycle_str}" for cycle_str in cycle_strs)
                )
        except nx.NetworkXError as e:
            raise DAGError(f"Error detecting cycles: {e}")

    def get_task(self, task_name: str) -> TaskMetadata:
        """Get a task by name from the graph.

        Args:
            task_name: Name of the task to retrieve.

        Returns:
            TaskMetadata instance.

        Raises:
            DAGError: If the task is not found.
        """
        if task_name not in self.graph:
            raise DAGError(f"Task '{task_name}' not found in dependency graph")

        return self.graph.nodes[task_name]["task"]

    def get_dependencies(self, task_name: str) -> Set[str]:
        """Get all direct dependencies of a task.

        Args:
            task_name: Name of the task.

        Returns:
            Set of task names that this task directly depends on.

        Raises:
            DAGError: If the task is not found.
        """
        if task_name not in self.graph:
            raise DAGError(f"Task '{task_name}' not found in dependency graph")

        # Get all predecessors (tasks that this task depends on)
        return set(self.graph.predecessors(task_name))

    def get_dependents(self, task_name: str) -> Set[str]:
        """Get all tasks that directly depend on this task.

        Args:
            task_name: Name of the task.

        Returns:
            Set of task names that depend on this task.

        Raises:
            DAGError: If the task is not found.
        """
        if task_name not in self.graph:
            raise DAGError(f"Task '{task_name}' not found in dependency graph")

        # Get all successors (tasks that depend on this task)
        return set(self.graph.successors(task_name))

    def get_all_dependencies(self, task_name: str) -> Set[str]:
        """Get all transitive dependencies of a task (recursive).

        Args:
            task_name: Name of the task.

        Returns:
            Set of all task names that this task depends on (directly or indirectly).

        Raises:
            DAGError: If the task is not found.
        """
        if task_name not in self.graph:
            raise DAGError(f"Task '{task_name}' not found in dependency graph")

        # Use NetworkX to get all ancestors (transitive predecessors)
        return set(nx.ancestors(self.graph, task_name))

    def get_all_dependents(self, task_name: str) -> Set[str]:
        """Get all tasks that depend on this task (transitive).

        Args:
            task_name: Name of the task.

        Returns:
            Set of all task names that depend on this task (directly or indirectly).

        Raises:
            DAGError: If the task is not found.
        """
        if task_name not in self.graph:
            raise DAGError(f"Task '{task_name}' not found in dependency graph")

        # Use NetworkX to get all descendants (transitive successors)
        return set(nx.descendants(self.graph, task_name))

    def topological_sort(self) -> List[str]:
        """Get a topological sort of all tasks.

        This returns tasks in an order where dependencies come before dependents.

        Returns:
            List of task names in topological order.

        Raises:
            DAGError: If the graph cannot be topologically sorted (should not happen
                     if cycle detection passed).
        """
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError as e:
            raise DAGError(f"Failed to perform topological sort: {e}")

    def get_execution_order(self, task_names: Set[str]) -> List[str]:
        """Get execution order for a set of tasks and their dependencies.

        This method takes a set of task names and returns them (plus all their
        dependencies) in topological order.

        Args:
            task_names: Set of task names to get execution order for.

        Returns:
            List of task names in execution order (dependencies first).

        Raises:
            DAGError: If any task is not found or sorting fails.
        """
        # Collect all tasks that need to be executed
        all_tasks = set(task_names)

        # Add all dependencies
        for task_name in task_names:
            if task_name not in self.graph:
                raise DAGError(f"Task '{task_name}' not found in dependency graph")
            all_tasks.update(self.get_all_dependencies(task_name))

        # Get topological sort of entire graph
        full_order = self.topological_sort()

        # Filter to only include tasks we need, preserving order
        execution_order = [task for task in full_order if task in all_tasks]

        return execution_order

    def get_all_tasks(self) -> Set[str]:
        """Get all task names in the graph.

        Returns:
            Set of all task names.
        """
        return set(self.graph.nodes())
