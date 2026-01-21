"""Recursive dependency resolver.

This module provides functionality to resolve all dependencies and triggers
for a set of matched tasks, using topological sort to determine execution order.
"""

from typing import List, Set

from said.dag_builder import CycleDetectedError, DAGError, DependencyGraph
from said.schema import DependencyMap


class ResolverError(Exception):
    """Base exception for resolver errors."""

    pass


class DependencyResolver:
    """Resolves dependencies and determines execution order for tasks."""

    def __init__(self, dependency_map: DependencyMap):
        """Initialize the dependency resolver.

        Args:
            dependency_map: The dependency map to resolve dependencies from.

        Raises:
            ResolverError: If the dependency graph cannot be built.
        """
        try:
            self.dependency_map = dependency_map
            self.graph = DependencyGraph(dependency_map)
        except CycleDetectedError as e:
            raise ResolverError(f"Invalid dependency map: {e}")
        except DAGError as e:
            raise ResolverError(f"Failed to build dependency graph: {e}")

    def resolve(
        self, matched_tasks: Set[str], include_triggers: bool = True
    ) -> List[str]:
        """Resolve all dependencies and triggers for matched tasks.

        This method:
        1. Takes a set of initially matched tasks (from file changes)
        2. Recursively collects all dependencies (via depends_on)
        3. Optionally collects all triggered tasks (via triggers)
        4. Returns them in topological order for execution

        Args:
            matched_tasks: Set of task names that were matched by file changes.
            include_triggers: If True, also include tasks triggered by matched tasks.

        Returns:
            List of task names in execution order (dependencies first).

        Raises:
            ResolverError: If any task is not found or resolution fails.
        """
        if not matched_tasks:
            return []

        # Validate that all matched tasks exist
        all_task_names = self.graph.get_all_tasks()
        invalid_tasks = matched_tasks - all_task_names
        if invalid_tasks:
            raise ResolverError(
                f"Matched tasks not found in dependency map: {invalid_tasks}"
            )

        # Start with the matched tasks
        tasks_to_execute = set(matched_tasks)

        # Add all dependencies (transitive)
        for task_name in matched_tasks:
            try:
                dependencies = self.graph.get_all_dependencies(task_name)
                tasks_to_execute.update(dependencies)
            except DAGError as e:
                raise ResolverError(f"Failed to get dependencies for {task_name}: {e}")

        # Optionally add all triggered tasks (transitive)
        if include_triggers:
            for task_name in matched_tasks:
                try:
                    # Get all tasks that are triggered by this task
                    # (these are the successors in the graph for trigger edges)
                    triggered = self.graph.get_all_dependents(task_name)
                    tasks_to_execute.update(triggered)
                except DAGError as e:
                    raise ResolverError(
                        f"Failed to get triggered tasks for {task_name}: {e}"
                    )

        # Get execution order using topological sort
        try:
            execution_order = self.graph.get_execution_order(tasks_to_execute)
        except DAGError as e:
            raise ResolverError(f"Failed to determine execution order: {e}")

        return execution_order

    def resolve_dependencies_only(self, matched_tasks: Set[str]) -> List[str]:
        """Resolve only dependencies (not triggers) for matched tasks.

        This is a convenience method that calls resolve with include_triggers=False.

        Args:
            matched_tasks: Set of task names that were matched by file changes.

        Returns:
            List of task names in execution order (dependencies first).
        """
        return self.resolve(matched_tasks, include_triggers=False)

    def resolve_with_triggers(self, matched_tasks: Set[str]) -> List[str]:
        """Resolve dependencies and triggers for matched tasks.

        This is a convenience method that calls resolve with include_triggers=True.

        Args:
            matched_tasks: Set of task names that were matched by file changes.

        Returns:
            List of task names in execution order (dependencies first).
        """
        return self.resolve(matched_tasks, include_triggers=True)

    def get_task_dependencies(self, task_name: str) -> Set[str]:
        """Get all dependencies for a single task.

        Args:
            task_name: Name of the task.

        Returns:
            Set of all task names that this task depends on (transitive).

        Raises:
            ResolverError: If the task is not found.
        """
        try:
            return self.graph.get_all_dependencies(task_name)
        except DAGError as e:
            raise ResolverError(f"Failed to get dependencies: {e}")

    def get_task_triggers(self, task_name: str) -> Set[str]:
        """Get all tasks triggered by a single task.

        Args:
            task_name: Name of the task.

        Returns:
            Set of all task names triggered by this task (transitive).

        Raises:
            ResolverError: If the task is not found.
        """
        try:
            return self.graph.get_all_dependents(task_name)
        except DAGError as e:
            raise ResolverError(f"Failed to get triggered tasks: {e}")


def resolve_dependencies(
    matched_tasks: Set[str],
    dependency_map: DependencyMap,
    include_triggers: bool = True,
) -> List[str]:
    """Convenience function to resolve dependencies for matched tasks.

    This function creates a DependencyResolver and calls resolve().

    Args:
        matched_tasks: Set of task names that were matched by file changes.
        dependency_map: The dependency map to resolve dependencies from.
        include_triggers: If True, also include tasks triggered by matched tasks.

    Returns:
        List of task names in execution order (dependencies first).

    Raises:
        ResolverError: If resolution fails.
    """
    resolver = DependencyResolver(dependency_map)
    return resolver.resolve(matched_tasks, include_triggers=include_triggers)
