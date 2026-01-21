"""Unit tests for parser module."""

import tempfile
from pathlib import Path

import pytest

from said.parser import (
    ParserError,
    discover_dependency_map,
    parse_dependency_map,
    parse_inline_metadata,
    parse_playbook_directory,
    parse_yaml_file,
)
from said.schema import DependencyMap, TaskMetadata


class TestParseYamlFile:
    """Test cases for parse_yaml_file function."""

    def test_parse_valid_yaml(self, tmp_path):
        """Test parsing a valid YAML file."""
        yaml_file = tmp_path / "test.yml"
        yaml_file.write_text("key: value\nnumber: 42\n")

        result = parse_yaml_file(yaml_file)
        assert result == {"key": "value", "number": 42}

    def test_parse_nonexistent_file(self, tmp_path):
        """Test parsing a non-existent file."""
        with pytest.raises(ParserError) as exc_info:
            parse_yaml_file(tmp_path / "nonexistent.yml")
        assert "not found" in str(exc_info.value).lower()

    def test_parse_invalid_yaml(self, tmp_path):
        """Test parsing invalid YAML."""
        yaml_file = tmp_path / "invalid.yml"
        yaml_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(ParserError) as exc_info:
            parse_yaml_file(yaml_file)
        assert "failed to parse" in str(exc_info.value).lower()

    def test_parse_empty_yaml(self, tmp_path):
        """Test parsing an empty YAML file."""
        yaml_file = tmp_path / "empty.yml"
        yaml_file.write_text("")

        with pytest.raises(ParserError) as exc_info:
            parse_yaml_file(yaml_file)
        assert "empty" in str(exc_info.value).lower()

    def test_parse_non_dict_yaml(self, tmp_path):
        """Test parsing YAML that is not a dictionary."""
        yaml_file = tmp_path / "list.yml"
        yaml_file.write_text("- item1\n- item2\n")

        with pytest.raises(ParserError) as exc_info:
            parse_yaml_file(yaml_file)
        assert "dictionary" in str(exc_info.value).lower()


class TestParseDependencyMap:
    """Test cases for parse_dependency_map function."""

    def test_parse_valid_dependency_map(self, tmp_path):
        """Test parsing a valid dependency map."""
        yaml_content = """
tasks:
  - name: task1
    provides: [resource1]
    watch_files: [file1.yml]
  - name: task2
    provides: [resource2]
    depends_on: [resource1]
"""
        yaml_file = tmp_path / "dependency_map.yml"
        yaml_file.write_text(yaml_content)

        result = parse_dependency_map(yaml_file)
        assert isinstance(result, DependencyMap)
        assert len(result.tasks) == 2
        assert result.get_task_by_name("task1") is not None
        assert result.get_task_by_name("task2") is not None

    def test_parse_missing_tasks_key(self, tmp_path):
        """Test parsing a file without 'tasks' key."""
        yaml_file = tmp_path / "invalid.yml"
        yaml_file.write_text("other_key: value\n")

        with pytest.raises(ParserError) as exc_info:
            parse_dependency_map(yaml_file)
        assert "tasks" in str(exc_info.value).lower()

    def test_parse_invalid_dependency_map(self, tmp_path):
        """Test parsing an invalid dependency map."""
        yaml_content = """
tasks:
  - name: task1
    provides: []  # Invalid: empty provides
"""
        yaml_file = tmp_path / "invalid.yml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ParserError):
            parse_dependency_map(yaml_file)


class TestParseInlineMetadata:
    """Test cases for parse_inline_metadata function."""

    def test_parse_single_inline_metadata(self):
        """Test parsing a single inline metadata comment."""
        content = """
# Some regular comment
# SAID: {"name": "task1", "provides": ["resource1"]}
- name: Some task
  action: do_something
"""
        result = parse_inline_metadata(content)
        assert len(result) == 1
        assert result[0]["name"] == "task1"
        assert result[0]["provides"] == ["resource1"]

    def test_parse_multiple_inline_metadata(self):
        """Test parsing multiple inline metadata comments."""
        content = """
# SAID: {"name": "task1", "provides": ["resource1"]}
- name: Task 1
  action: do_something

# SAID: {"name": "task2", "provides": ["resource2"], "depends_on": ["resource1"]}
- name: Task 2
  action: do_something_else
"""
        result = parse_inline_metadata(content)
        assert len(result) == 2
        assert result[0]["name"] == "task1"
        assert result[1]["name"] == "task2"

    def test_parse_no_metadata(self):
        """Test parsing content with no metadata."""
        content = """
- name: Some task
  action: do_something
"""
        result = parse_inline_metadata(content)
        assert len(result) == 0

    def test_parse_invalid_metadata(self):
        """Test parsing invalid inline metadata."""
        # Test with empty content (this should fail)
        content = "# SAID:\n"
        with pytest.raises(ParserError) as exc_info:
            parse_inline_metadata(content)
        assert "invalid" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()
        
        # Test with unclosed bracket (this should fail YAML parsing)
        content2 = "# SAID: {unclosed\n"
        with pytest.raises(ParserError) as exc_info:
            parse_inline_metadata(content2)
        assert "failed to parse" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    def test_parse_yaml_metadata(self):
        """Test parsing YAML format inline metadata.
        
        Note: Current implementation only supports single-line metadata.
        Multi-line YAML format is not yet supported.
        """
        # Test with single-line YAML format (which works)
        content = "# SAID: {name: task1, provides: [resource1]}\n"
        result = parse_inline_metadata(content)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "task1"
        
        # Test that multi-line format currently fails (empty content after "# SAID:")
        content2 = """
# SAID:
#   name: task1
#   provides: [resource1]
- name: Some task
"""
        # This will fail because "# SAID:" with nothing after it is empty
        with pytest.raises(ParserError):
            parse_inline_metadata(content2)


class TestParsePlaybookDirectory:
    """Test cases for parse_playbook_directory function."""

    def test_parse_directory_with_playbooks(self, tmp_path):
        """Test parsing a directory with playbook files."""
        playbook1 = tmp_path / "playbook1.yml"
        playbook1.write_text(
            """
# SAID: {"name": "task1", "provides": ["resource1"]}
- name: Task 1
  action: do_something
"""
        )

        playbook2 = tmp_path / "playbook2.yml"
        playbook2.write_text(
            """
# SAID: {"name": "task2", "provides": ["resource2"], "depends_on": ["resource1"]}
- name: Task 2
  action: do_something_else
"""
        )

        result = parse_playbook_directory(tmp_path)
        assert isinstance(result, DependencyMap)
        assert len(result.tasks) == 2

    def test_parse_nonexistent_directory(self, tmp_path):
        """Test parsing a non-existent directory."""
        with pytest.raises(ParserError) as exc_info:
            parse_playbook_directory(tmp_path / "nonexistent")
        assert "not found" in str(exc_info.value).lower()

    def test_parse_directory_no_metadata(self, tmp_path):
        """Test parsing a directory with no metadata."""
        playbook = tmp_path / "playbook.yml"
        playbook.write_text("- name: Some task\n  action: do_something\n")

        with pytest.raises(ParserError) as exc_info:
            parse_playbook_directory(tmp_path)
        assert "no task metadata" in str(exc_info.value).lower()

    def test_parse_subdirectories(self, tmp_path):
        """Test parsing playbooks in subdirectories."""
        subdir = tmp_path / "roles" / "web"
        subdir.mkdir(parents=True)
        playbook = subdir / "tasks.yml"
        playbook.write_text(
            """
# SAID: {"name": "web_task", "provides": ["web_config"]}
- name: Web task
  action: configure_web
"""
        )

        result = parse_playbook_directory(tmp_path)
        assert isinstance(result, DependencyMap)
        assert len(result.tasks) == 1
        assert result.get_task_by_name("web_task") is not None


class TestDiscoverDependencyMap:
    """Test cases for discover_dependency_map function."""

    def test_discover_in_current_directory(self, tmp_path, monkeypatch):
        """Test discovering dependency map in current directory."""
        monkeypatch.chdir(tmp_path)
        dep_map_file = tmp_path / "dependency_map.yml"
        dep_map_file.write_text(
            """
tasks:
  - name: task1
    provides: [resource1]
"""
        )

        result = discover_dependency_map()
        assert isinstance(result, DependencyMap)
        assert len(result.tasks) == 1

    def test_discover_in_subdirectory(self, tmp_path, monkeypatch):
        """Test discovering dependency map in subdirectory."""
        monkeypatch.chdir(tmp_path)
        ansible_dir = tmp_path / "ansible"
        ansible_dir.mkdir()
        dep_map_file = ansible_dir / "dependency_map.yml"
        dep_map_file.write_text(
            """
tasks:
  - name: task1
    provides: [resource1]
"""
        )

        result = discover_dependency_map()
        assert isinstance(result, DependencyMap)

    def test_discover_not_found(self, tmp_path, monkeypatch):
        """Test when dependency map is not found."""
        monkeypatch.chdir(tmp_path)
        result = discover_dependency_map()
        assert result is None

    def test_discover_invalid_file(self, tmp_path, monkeypatch):
        """Test discovering an invalid dependency map file."""
        monkeypatch.chdir(tmp_path)
        dep_map_file = tmp_path / "dependency_map.yml"
        dep_map_file.write_text("invalid: content\n")

        with pytest.raises(ParserError):
            discover_dependency_map()
