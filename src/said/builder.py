"""Automated dependency map builder from Ansible playbooks.

This module provides functionality to automatically analyze Ansible playbooks
and generate dependency maps by inferring relationships from task structures,
file paths, tags, handlers, and dependencies.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import yaml

from said.schema import DependencyMap, SchemaError, TaskMetadata, validate_dependency_map


class BuilderError(Exception):
    """Base exception for builder errors."""

    pass


def analyze_ansible_task(task: Dict, playbook_path: Path) -> Optional[Dict]:
    """Analyze a single Ansible task and extract metadata.

    Args:
        task: Ansible task dictionary.
        playbook_path: Path to the playbook file (for relative path resolution).

    Returns:
        Dictionary with inferred task metadata, or None if task cannot be analyzed.
    """
    metadata = {}

    # Extract task name
    if "name" in task:
        metadata["name"] = task["name"]
    elif "include_tasks" in task:
        metadata["name"] = task["include_tasks"]
    elif "import_tasks" in task:
        metadata["name"] = task["import_tasks"]
    elif "include_role" in task:
        metadata["name"] = task["include_role"].get("name", "unknown_role")
    elif "import_role" in task:
        metadata["name"] = task["import_role"].get("name", "unknown_role")
    else:
        # Try to infer from action/module
        for key in ["action", "module"]:
            if key in task:
                metadata["name"] = f"{task[key]}_{hash(str(task)) % 10000}"
                break
        if "name" not in metadata:
            return None  # Cannot infer task name

    # Extract tags (used as task identifiers)
    if "tags" in task:
        if isinstance(task["tags"], list):
            metadata["tags"] = task["tags"]
        else:
            metadata["tags"] = [task["tags"]]

    # Infer watch_files from task actions
    watch_files = set()

    # Template tasks
    if "template" in task:
        src = task["template"].get("src") if isinstance(task["template"], dict) else task["template"]
        if src:
            watch_files.add(str(playbook_path.parent / src))
            watch_files.add(f"templates/{Path(src).name}")

    # Copy tasks
    if "copy" in task:
        src = task["copy"].get("src") if isinstance(task["copy"], dict) else task["copy"]
        if src:
            watch_files.add(str(playbook_path.parent / src))

    # File tasks
    if "file" in task:
        path = task["file"].get("path") if isinstance(task["file"], dict) else task["file"]
        if path:
            watch_files.add(path)

    # Include/import tasks
    if "include_tasks" in task:
        include_path = task["include_tasks"]
        watch_files.add(str(playbook_path.parent / include_path))
    if "import_tasks" in task:
        import_path = task["import_tasks"]
        watch_files.add(str(playbook_path.parent / import_path))

    # Role tasks
    if "include_role" in task or "import_role" in task:
        role_name = None
        if "include_role" in task:
            role_name = task["include_role"].get("name") if isinstance(task["include_role"], dict) else task["include_role"]
        elif "import_role" in task:
            role_name = task["import_role"].get("name") if isinstance(task["import_role"], dict) else task["import_role"]
        
        if role_name:
            watch_files.add(f"roles/{role_name}/**/*")
            watch_files.add(f"roles/{role_name}/tasks/**/*")

    # Extract variables used in task
    requires_vars = set()
    task_str = yaml.dump(task, default_flow_style=False)
    
    # Look for variable references {{ var_name }} or {{ var_name | filter }}
    var_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[|}]'
    for match in re.finditer(var_pattern, task_str):
        var_name = match.group(1)
        # Skip common Ansible variables
        if var_name not in ["item", "ansible", "hostvars", "group_names", "groups"]:
            requires_vars.add(var_name)

    # Extract when conditions (may reference variables)
    if "when" in task:
        when_str = str(task["when"])
        for match in re.finditer(var_pattern, when_str):
            var_name = match.group(1)
            if var_name not in ["item", "ansible", "hostvars", "group_names", "groups"]:
                requires_vars.add(var_name)

    # Build metadata
    result = {
        "name": metadata["name"],
        "provides": [metadata["name"]],  # Default: task provides itself as resource
        "depends_on": [],
        "triggers": [],
        "watch_files": sorted(list(watch_files)) if watch_files else [],
        "requires_vars": sorted(list(requires_vars)) if requires_vars else [],
    }

    # Extract dependencies from when conditions or explicit dependencies
    if "when" in task:
        when_str = str(task["when"])
        # Look for references to other tasks/resources
        # This is a simple heuristic - could be enhanced
        deps = re.findall(r'(\w+)\s+is\s+defined', when_str)
        result["depends_on"].extend(deps)

    return result


def analyze_ansible_playbook(playbook_path: Union[str, Path]) -> List[Dict]:
    """Analyze an Ansible playbook and extract task metadata.

    Args:
        playbook_path: Path to the Ansible playbook file.

    Returns:
        List of task metadata dictionaries.

    Raises:
        BuilderError: If the playbook cannot be parsed or analyzed.
    """
    playbook_path = Path(playbook_path)

    if not playbook_path.exists():
        raise BuilderError(f"Playbook not found: {playbook_path}")

    try:
        with open(playbook_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BuilderError(f"Failed to parse playbook {playbook_path}: {e}")
    except IOError as e:
        raise BuilderError(f"Failed to read playbook {playbook_path}: {e}")

    if content is None:
        return []

    # Handle both single playbook and list of playbooks
    if isinstance(content, list):
        plays = content
    else:
        plays = [content]

    all_tasks = []

    for play in plays:
        if not isinstance(play, dict):
            continue

        # Extract tasks from play
        tasks = play.get("tasks", [])
        handlers = play.get("handlers", [])

        # Analyze handlers
        for handler in handlers:
            if isinstance(handler, dict):
                task_meta = analyze_ansible_task(handler, playbook_path)
                if task_meta:
                    # Mark as handler-triggered
                    task_meta["triggers"] = [f"notify_{task_meta['name']}"]
                    all_tasks.append(task_meta)

        # Check for pre_tasks and post_tasks
        pre_tasks = play.get("pre_tasks", [])
        post_tasks = play.get("post_tasks", [])

        # Analyze regular tasks
        for task in tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    all_tasks.append(task_meta)

        # Analyze pre_tasks
        for task in pre_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    all_tasks.append(task_meta)

        # Analyze post_tasks
        for task in post_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    all_tasks.append(task_meta)

    return all_tasks


def build_dependency_map_from_playbooks(
    playbook_paths: List[Union[str, Path]],
    output_path: Optional[Union[str, Path]] = None,
) -> DependencyMap:
    """Build a dependency map by analyzing multiple Ansible playbooks.

    Args:
        playbook_paths: List of paths to Ansible playbook files.
        output_path: Optional path to write the generated dependency map YAML file.

    Returns:
        Validated DependencyMap instance.

    Raises:
        BuilderError: If analysis fails or dependency map is invalid.
    """
    all_tasks = []

    for playbook_path in playbook_paths:
        try:
            tasks = analyze_ansible_playbook(playbook_path)
            all_tasks.extend(tasks)
        except BuilderError as e:
            raise BuilderError(f"Failed to analyze {playbook_path}: {e}")

    if not all_tasks:
        raise BuilderError("No tasks found in playbooks")

    # Deduplicate tasks by name (keep first occurrence)
    seen_names = set()
    unique_tasks = []
    for task in all_tasks:
        if task["name"] not in seen_names:
            unique_tasks.append(task)
            seen_names.add(task["name"])

    # Build dependency map
    try:
        dependency_map = validate_dependency_map({"tasks": unique_tasks})
    except SchemaError as e:
        raise BuilderError(f"Invalid dependency map structure: {e}")

    # Write to file if requested
    if output_path:
        output_path = Path(output_path)
        output_data = {
            "tasks": [
                {
                    "name": task.name,
                    "provides": task.provides,
                    "depends_on": task.depends_on,
                    "triggers": task.triggers,
                    "watch_files": task.watch_files,
                    "requires_vars": task.requires_vars,
                }
                for task in dependency_map.tasks
            ]
        }
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)
        except IOError as e:
            raise BuilderError(f"Failed to write dependency map to {output_path}: {e}")

    return dependency_map


def build_dependency_map_from_directory(
    directory: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    pattern: str = "*.yml",
) -> DependencyMap:
    """Build a dependency map by analyzing all playbooks in a directory.

    Args:
        directory: Path to directory containing Ansible playbooks.
        output_path: Optional path to write the generated dependency map YAML file.
        pattern: Glob pattern to match playbook files. Defaults to "*.yml".

    Returns:
        Validated DependencyMap instance.

    Raises:
        BuilderError: If analysis fails or dependency map is invalid.
    """
    directory = Path(directory)

    if not directory.exists():
        raise BuilderError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise BuilderError(f"Path is not a directory: {directory}")

    # Find all playbook files
    playbook_paths = []
    for pattern_variant in [pattern, "*.yaml"]:
        playbook_paths.extend(directory.rglob(pattern_variant))

    if not playbook_paths:
        raise BuilderError(f"No playbook files found in {directory}")

    return build_dependency_map_from_playbooks(playbook_paths, output_path)
