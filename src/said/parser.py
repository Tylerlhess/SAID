"""Dependency map parser for YAML configuration files.

This module provides functionality to parse dependency_map.yml files and
extract task metadata, supporting both standalone manifest files and
inline metadata within Ansible playbooks.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml

from said.schema import DependencyMap, SchemaError, TaskMetadata, validate_dependency_map


class ParserError(Exception):
    """Base exception for parser errors."""

    pass


def parse_yaml_file(file_path: Union[str, Path]) -> Dict:
    """Parse a YAML file and return its contents as a dictionary.

    Args:
        file_path: Path to the YAML file to parse.

    Returns:
        Dictionary containing the parsed YAML content.

    Raises:
        ParserError: If the file cannot be read or parsed.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise ParserError(f"Dependency map file not found: {file_path}")

    if not file_path.is_file():
        raise ParserError(f"Path is not a file: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ParserError(f"Failed to parse YAML file {file_path}: {e}")
    except IOError as e:
        raise ParserError(f"Failed to read file {file_path}: {e}")

    if content is None:
        raise ParserError(f"YAML file is empty: {file_path}")

    if not isinstance(content, dict):
        raise ParserError(
            f"YAML file must contain a dictionary at root level, got {type(content).__name__}"
        )

    return content


def parse_dependency_map(file_path: Union[str, Path]) -> DependencyMap:
    """Parse a dependency_map.yml file and return a validated DependencyMap.

    This function handles standalone manifest files that contain a 'tasks' key
    with a list of task metadata definitions.

    Args:
        file_path: Path to the dependency_map.yml file.

    Returns:
        Validated DependencyMap instance.

    Raises:
        ParserError: If the file cannot be parsed or is invalid.
        SchemaError: If the dependency map structure is invalid.
    """
    try:
        data = parse_yaml_file(file_path)

        # Check if 'tasks' key exists
        if "tasks" not in data:
            raise ParserError(
                f"Dependency map file must contain a 'tasks' key: {file_path}"
            )

        # Validate and create DependencyMap
        try:
            return validate_dependency_map(data)
        except SchemaError as e:
            # Wrap SchemaError in ParserError for consistency
            raise ParserError(f"Invalid dependency map structure: {e}")

    except ParserError:
        raise
    except Exception as e:
        raise ParserError(f"Unexpected error parsing dependency map: {e}")


def parse_inline_metadata(playbook_content: str) -> List[Dict]:
    """Extract inline task metadata from Ansible playbook content.

    This function looks for YAML comments or special metadata blocks within
    Ansible playbooks. The format expected is:
    # SAID: {"name": "task_name", "provides": ["resource"], ...}

    Args:
        playbook_content: String content of an Ansible playbook file.

    Returns:
        List of task metadata dictionaries found in the playbook.

    Raises:
        ParserError: If metadata cannot be parsed.
    """
    tasks = []
    lines = playbook_content.split("\n")

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()

        # Look for SAID metadata comments
        if line.startswith("# SAID:"):
            metadata_str = line[7:].strip()  # Remove "# SAID:" prefix

            try:
                # Try to parse as YAML (which is a superset of JSON)
                metadata = yaml.safe_load(metadata_str)
                if metadata is None:
                    # Empty or invalid content
                    raise ParserError(
                        f"Invalid inline metadata at line {line_num}: empty or invalid content"
                    )
                if not isinstance(metadata, dict):
                    raise ParserError(
                        f"Invalid inline metadata at line {line_num}: expected dictionary, got {type(metadata).__name__}"
                    )
                tasks.append(metadata)
            except yaml.YAMLError as e:
                raise ParserError(
                    f"Failed to parse inline metadata at line {line_num}: {e}"
                )

    return tasks


def parse_playbook_directory(directory: Union[str, Path]) -> DependencyMap:
    """Parse all playbooks in a directory and extract inline metadata.

    This function scans a directory for Ansible playbook files (typically .yml or .yaml)
    and extracts inline metadata from each file, then combines them into a single
    DependencyMap.

    Args:
        directory: Path to the directory containing Ansible playbooks.

    Returns:
        Validated DependencyMap instance containing all tasks from playbooks.

    Raises:
        ParserError: If the directory cannot be read or metadata is invalid.
        SchemaError: If the combined dependency map structure is invalid.
    """
    directory = Path(directory)

    if not directory.exists():
        raise ParserError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise ParserError(f"Path is not a directory: {directory}")

    all_tasks = []

    # Common Ansible playbook file extensions
    playbook_extensions = {".yml", ".yaml"}

    for file_path in directory.rglob("*"):
        if file_path.is_file() and file_path.suffix in playbook_extensions:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    inline_tasks = parse_inline_metadata(content)
                    all_tasks.extend(inline_tasks)
            except IOError as e:
                raise ParserError(f"Failed to read playbook file {file_path}: {e}")
            except ParserError as e:
                # Re-raise with file context
                raise ParserError(f"Error in {file_path}: {e}")

    if not all_tasks:
        raise ParserError(
            f"No task metadata found in playbook directory: {directory}"
        )

    # Combine all tasks into a dependency map
    try:
        return validate_dependency_map({"tasks": all_tasks})
    except SchemaError as e:
        raise ParserError(f"Invalid combined dependency map: {e}")


def discover_dependency_map(
    start_path: Optional[Union[str, Path]] = None,
) -> Optional[DependencyMap]:
    """Auto-discover dependency_map.yml in common locations.

    Searches for dependency_map.yml in:
    1. Current working directory
    2. Parent directories (up to 3 levels)
    3. Common locations: ./ansible/, ./playbooks/, ./

    Args:
        start_path: Starting path for discovery. Defaults to current working directory.

    Returns:
        DependencyMap if found, None otherwise.

    Raises:
        ParserError: If a file is found but cannot be parsed.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    # Common filenames
    filenames = ["dependency_map.yml", "dependency_map.yaml"]

    # Search locations
    search_paths = [
        start_path,
        start_path / "ansible",
        start_path / "playbooks",
        start_path.parent,
        start_path.parent.parent,
        start_path.parent.parent.parent,
    ]

    for search_path in search_paths:
        if not search_path.exists():
            continue

        for filename in filenames:
            candidate = search_path / filename
            if candidate.exists() and candidate.is_file():
                try:
                    return parse_dependency_map(candidate)
                except (ParserError, SchemaError) as e:
                    # If file exists but is invalid, raise error
                    raise ParserError(
                        f"Found dependency map at {candidate} but it is invalid: {e}"
                    )

    return None
