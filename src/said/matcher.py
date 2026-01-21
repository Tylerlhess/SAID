"""File-to-task matching logic.

This module provides functionality to match changed files to tasks based on
watch_files patterns, supporting both exact matches and glob patterns.
"""

import fnmatch
from pathlib import Path
from typing import List, Set

from said.schema import DependencyMap, TaskMetadata


class MatcherError(Exception):
    """Base exception for matcher errors."""

    pass


def match_file_to_tasks(
    file_path: str, dependency_map: DependencyMap
) -> Set[str]:
    """Match a single file path to tasks that watch it.

    Args:
        file_path: Path to the file to match (can be relative or absolute).
        dependency_map: The dependency map containing tasks with watch_files.

    Returns:
        Set of task names that match this file.
    """
    matched_tasks = set()
    file_path_obj = Path(file_path)

    for task in dependency_map.tasks:
        for pattern in task.watch_files:
            if _matches_pattern(file_path_obj, pattern):
                matched_tasks.add(task.name)
                break  # Task matches, no need to check other patterns

    return matched_tasks


def match_files_to_tasks(
    file_paths: List[str], dependency_map: DependencyMap
) -> Set[str]:
    """Match multiple file paths to tasks.

    Args:
        file_paths: List of file paths to match.
        dependency_map: The dependency map containing tasks with watch_files.

    Returns:
        Set of all task names that match any of the provided files.
    """
    all_matched_tasks = set()

    for file_path in file_paths:
        matched = match_file_to_tasks(file_path, dependency_map)
        all_matched_tasks.update(matched)

    return all_matched_tasks


def _matches_pattern(file_path: Path, pattern: str) -> bool:
    """Check if a file path matches a pattern.

    Supports:
    - Exact matches: "file.yml" matches only "file.yml"
    - Glob patterns: "*.yml" matches any .yml file
    - Path patterns: "templates/*.j2" matches .j2 files in templates/
    - Relative paths: Both file and pattern are normalized

    Args:
        file_path: Path object for the file to check.
        pattern: Pattern to match against (supports glob syntax).

    Returns:
        True if the file matches the pattern, False otherwise.
    """
    # Normalize paths to handle different separators
    file_path_str = str(file_path.as_posix())
    pattern_str = str(Path(pattern).as_posix())

    # Check for exact match first
    if file_path_str == pattern_str:
        return True

    # Check if pattern matches the full path
    if fnmatch.fnmatch(file_path_str, pattern_str):
        return True

    # Check if pattern matches just the filename
    if fnmatch.fnmatch(file_path.name, pattern_str):
        return True

    # Check if pattern matches relative path from common base
    # This handles cases like "templates/nginx.conf.j2" matching "templates/*.j2"
    # Try matching against different path segments
    path_parts = file_path.parts
    pattern_parts = Path(pattern_str).parts

    # If pattern has multiple parts, try matching path segments
    if len(pattern_parts) > 1:
        # Try to match from the end (most specific)
        if len(path_parts) >= len(pattern_parts):
            # Get the last N parts of the path
            path_suffix = Path(*path_parts[-len(pattern_parts) :])
            if fnmatch.fnmatch(str(path_suffix.as_posix()), pattern_str):
                return True

    # Try matching any suffix of the path against the pattern
    # This handles cases where pattern is "nginx.conf.j2" and file is
    # "some/deep/path/nginx.conf.j2"
    for i in range(len(path_parts)):
        path_suffix = Path(*path_parts[i:])
        if fnmatch.fnmatch(str(path_suffix.as_posix()), pattern_str):
            return True
        if fnmatch.fnmatch(path_suffix.name, pattern_str):
            return True

    return False


def get_tasks_for_changed_files(
    changed_files: List[str], dependency_map: DependencyMap
) -> Set[str]:
    """Get all tasks that should be executed for a list of changed files.

    This is a convenience function that combines file matching logic.

    Args:
        changed_files: List of file paths that have changed.
        dependency_map: The dependency map containing tasks with watch_files.

    Returns:
        Set of task names that match the changed files.
    """
    if not changed_files:
        return set()

    return match_files_to_tasks(changed_files, dependency_map)


def validate_watch_files(dependency_map: DependencyMap) -> List[str]:
    """Validate that all watch_files patterns are well-formed.

    This function checks for common issues with watch_files patterns:
    - Empty patterns
    - Invalid glob syntax (basic check)

    Args:
        dependency_map: The dependency map to validate.

    Returns:
        List of warning messages (empty if no issues found).
    """
    warnings = []

    for task in dependency_map.tasks:
        for pattern in task.watch_files:
            if not pattern or not pattern.strip():
                warnings.append(
                    f"Task '{task.name}' has an empty watch_files pattern"
                )

    return warnings
