"""Dependency map parser for YAML configuration files.

This module provides functionality to parse dependency_map.yml files and
extract task metadata, supporting both standalone manifest files and
inline metadata within Ansible playbooks.
"""

import os
from functools import lru_cache
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


# Cache for parsed dependency maps (keyed by file path and mtime)
_dependency_map_cache: Dict[tuple, DependencyMap] = {}


def _get_cache_key(file_path: Path) -> tuple:
    """Generate cache key from file path and modification time.

    Args:
        file_path: Path to the file.

    Returns:
        Tuple of (absolute_path, mtime) for use as cache key.
    """
    try:
        stat = file_path.stat()
        return (str(file_path.resolve()), stat.st_mtime)
    except OSError:
        # If we can't stat the file, use path only (no caching)
        return (str(file_path.resolve()), None)


def parse_dependency_map(file_path: Union[str, Path], use_cache: bool = True) -> DependencyMap:
    """Parse a dependency_map.yml file and return a validated DependencyMap.

    This function handles standalone manifest files that contain a 'tasks' key
    with a list of task metadata definitions. Results are cached based on file
    path and modification time for performance.

    Args:
        file_path: Path to the dependency_map.yml file.
        use_cache: If True, use caching for parsed maps. Defaults to True.

    Returns:
        Validated DependencyMap instance.

    Raises:
        ParserError: If the file cannot be parsed or is invalid.
        SchemaError: If the dependency map structure is invalid.
    """
    file_path = Path(file_path)
    
    # Check cache if enabled
    if use_cache:
        cache_key = _get_cache_key(file_path)
        if cache_key[1] is not None and cache_key in _dependency_map_cache:
            return _dependency_map_cache[cache_key]
    
    try:
        data = parse_yaml_file(file_path)

        # Check if 'tasks' key exists
        if "tasks" not in data:
            raise ParserError(
                f"Dependency map file must contain a 'tasks' key: {file_path}"
            )

        # Validate and create DependencyMap
        try:
            dependency_map = validate_dependency_map(data)
            
            # Cache the result if enabled
            if use_cache and cache_key[1] is not None:
                _dependency_map_cache[cache_key] = dependency_map
                # Limit cache size to prevent memory issues
                if len(_dependency_map_cache) > 100:
                    # Remove oldest entries (simple FIFO)
                    oldest_key = next(iter(_dependency_map_cache))
                    del _dependency_map_cache[oldest_key]
            
            return dependency_map
        except SchemaError as e:
            # Wrap SchemaError in ParserError for consistency
            raise ParserError(f"Invalid dependency map structure: {e}")

    except ParserError:
        raise
    except Exception as e:
        raise ParserError(f"Unexpected error parsing dependency map: {e}")


def clear_dependency_map_cache():
    """Clear the dependency map cache.

    Useful for testing or when you want to force re-parsing of files.
    """
    _dependency_map_cache.clear()


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
    search_multiple: bool = False,
) -> Optional[DependencyMap]:
    """Auto-discover dependency_map.yml in common locations.

    Searches for dependency_map.yml in:
    1. Current working directory
    2. Parent directories (up to 3 levels)
    3. Common locations: ./ansible/, ./playbooks/, ./

    Args:
        start_path: Starting path for discovery. Defaults to current working directory.
        search_multiple: If True, search for multiple dependency map files and merge them.
                        Defaults to False (returns first found).

    Returns:
        DependencyMap if found, None otherwise. If search_multiple is True and multiple
        files are found, returns a merged DependencyMap.

    Raises:
        ParserError: If a file is found but cannot be parsed.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    # Common filenames
    filenames = ["dependency_map.yml", "dependency_map.yaml"]

    # Search locations (ordered by priority)
    search_paths = [
        start_path,
        start_path / "ansible",
        start_path / "playbooks",
        start_path.parent,
        start_path.parent.parent,
        start_path.parent.parent.parent,
    ]

    found_maps = []
    
    for search_path in search_paths:
        if not search_path.exists():
            continue

        for filename in filenames:
            candidate = search_path / filename
            if candidate.exists() and candidate.is_file():
                try:
                    dep_map = parse_dependency_map(candidate)
                    found_maps.append((candidate, dep_map))
                    
                    # If not searching for multiple, return first found
                    if not search_multiple:
                        return dep_map
                except (ParserError, SchemaError) as e:
                    # If file exists but is invalid, raise error
                    raise ParserError(
                        f"Found dependency map at {candidate} but it is invalid: {e}"
                    )

    # If searching for multiple, merge all found maps
    if search_multiple and found_maps:
        return _merge_dependency_maps([dep_map for _, dep_map in found_maps])
    
    return None


def _merge_dependency_maps(maps: List[DependencyMap]) -> DependencyMap:
    """Merge multiple dependency maps into one.

    Tasks with the same name will be deduplicated (first occurrence wins).
    All tasks from all maps are combined.

    Args:
        maps: List of DependencyMap instances to merge.

    Returns:
        Merged DependencyMap instance.

    Raises:
        ParserError: If merging fails or creates invalid structure.
    """
    if not maps:
        raise ParserError("Cannot merge empty list of dependency maps")
    
    if len(maps) == 1:
        return maps[0]
    
    # Collect all tasks, deduplicating by name
    seen_names = set()
    merged_tasks = []
    
    for dep_map in maps:
        for task in dep_map.tasks:
            if task.name not in seen_names:
                merged_tasks.append(task)
                seen_names.add(task.name)
    
    # Create merged map
    try:
        return validate_dependency_map({"tasks": [task.__dict__ for task in merged_tasks]})
    except SchemaError as e:
        raise ParserError(f"Failed to merge dependency maps: {e}")
