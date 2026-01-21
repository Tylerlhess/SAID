"""Unit tests for matcher module."""

import pytest

from said.matcher import (
    get_tasks_for_changed_files,
    match_file_to_tasks,
    match_files_to_tasks,
    validate_watch_files,
)
from said.schema import DependencyMap, TaskMetadata


class TestMatchFileToTasks:
    """Test cases for match_file_to_tasks function."""

    def test_exact_match(self):
        """Test matching a file with exact path."""
        task1 = TaskMetadata(
            name="task1",
            provides=["resource1"],
            watch_files=["templates/nginx.conf.j2"],
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_file_to_tasks("templates/nginx.conf.j2", dep_map)
        assert "task1" in matched

    def test_glob_pattern_match(self):
        """Test matching a file with glob pattern."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_file_to_tasks("config.yml", dep_map)
        assert "task1" in matched

    def test_path_pattern_match(self):
        """Test matching a file with path pattern."""
        task1 = TaskMetadata(
            name="task1",
            provides=["resource1"],
            watch_files=["templates/*.j2"],
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_file_to_tasks("templates/nginx.conf.j2", dep_map)
        assert "task1" in matched

    def test_no_match(self):
        """Test when no tasks match a file."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_file_to_tasks("config.txt", dep_map)
        assert len(matched) == 0

    def test_multiple_tasks_match(self):
        """Test when multiple tasks match a file."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], watch_files=["config.yml"]
        )
        dep_map = DependencyMap(tasks=[task1, task2])

        matched = match_file_to_tasks("config.yml", dep_map)
        assert "task1" in matched
        assert "task2" in matched

    def test_relative_path_matching(self):
        """Test matching with relative paths."""
        task1 = TaskMetadata(
            name="task1",
            provides=["resource1"],
            watch_files=["nginx.conf.j2"],
        )
        dep_map = DependencyMap(tasks=[task1])

        # Should match even if path has directory prefix
        matched = match_file_to_tasks("some/deep/path/nginx.conf.j2", dep_map)
        assert "task1" in matched


class TestMatchFilesToTasks:
    """Test cases for match_files_to_tasks function."""

    def test_match_multiple_files(self):
        """Test matching multiple files."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], watch_files=["*.txt"]
        )
        dep_map = DependencyMap(tasks=[task1, task2])

        matched = match_files_to_tasks(["file1.yml", "file2.txt"], dep_map)
        assert "task1" in matched
        assert "task2" in matched

    def test_match_empty_list(self):
        """Test matching an empty file list."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_files_to_tasks([], dep_map)
        assert len(matched) == 0

    def test_match_overlapping_tasks(self):
        """Test when multiple files match the same task."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = match_files_to_tasks(["file1.yml", "file2.yml"], dep_map)
        assert "task1" in matched
        assert len(matched) == 1  # Task should only appear once


class TestGetTasksForChangedFiles:
    """Test cases for get_tasks_for_changed_files function."""

    def test_get_tasks_for_changed_files(self):
        """Test getting tasks for changed files."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        task2 = TaskMetadata(
            name="task2", provides=["resource2"], watch_files=["*.txt"]
        )
        dep_map = DependencyMap(tasks=[task1, task2])

        changed_files = ["config.yml", "readme.txt"]
        matched = get_tasks_for_changed_files(changed_files, dep_map)
        assert "task1" in matched
        assert "task2" in matched

    def test_get_tasks_empty_changes(self):
        """Test with empty changed files list."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["*.yml"]
        )
        dep_map = DependencyMap(tasks=[task1])

        matched = get_tasks_for_changed_files([], dep_map)
        assert len(matched) == 0


class TestValidateWatchFiles:
    """Test cases for validate_watch_files function."""

    def test_validate_valid_watch_files(self):
        """Test validation with valid watch files."""
        task1 = TaskMetadata(
            name="task1",
            provides=["resource1"],
            watch_files=["file1.yml", "file2.yml"],
        )
        dep_map = DependencyMap(tasks=[task1])

        warnings = validate_watch_files(dep_map)
        assert len(warnings) == 0

    def test_validate_empty_pattern(self):
        """Test validation with empty pattern."""
        task1 = TaskMetadata(
            name="task1", provides=["resource1"], watch_files=["file1.yml", ""]
        )
        dep_map = DependencyMap(tasks=[task1])

        warnings = validate_watch_files(dep_map)
        assert len(warnings) > 0
        assert "empty" in warnings[0].lower()

    def test_validate_whitespace_pattern(self):
        """Test validation with whitespace-only pattern."""
        task1 = TaskMetadata(
            name="task1",
            provides=["resource1"],
            watch_files=["file1.yml", "   "],
        )
        dep_map = DependencyMap(tasks=[task1])

        warnings = validate_watch_files(dep_map)
        assert len(warnings) > 0
