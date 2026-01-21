"""Automated dependency map builder from Ansible playbooks.

This module provides functionality to automatically analyze Ansible playbooks
and generate dependency maps by inferring relationships from task structures,
file paths, tags, handlers, and dependencies. Recursively expands included
playbooks and roles.
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

    # Template tasks (handle both "template" and "ansible.builtin.template")
    for template_key in ["template", "ansible.builtin.template", "ansible.legacy.template"]:
        if template_key in task:
            template_dict = task[template_key]
            if isinstance(template_dict, dict):
                src = template_dict.get("src")
            else:
                src = template_dict
            if src:
                watch_files.add(str(playbook_path.parent / src))
                watch_files.add(f"templates/{Path(src).name}")
            break

    # Copy tasks (handle both "copy" and "ansible.builtin.copy")
    for copy_key in ["copy", "ansible.builtin.copy", "ansible.legacy.copy"]:
        if copy_key in task:
            copy_dict = task[copy_key]
            if isinstance(copy_dict, dict):
                src = copy_dict.get("src")
                dest = copy_dict.get("dest")
                if src:
                    watch_files.add(str(playbook_path.parent / src))
                if dest:
                    watch_files.add(dest)
            else:
                # Simple string format
                watch_files.add(str(playbook_path.parent / copy_dict))
            break

    # File tasks (handle both "file" and "ansible.builtin.file")
    for file_key in ["file", "ansible.builtin.file", "ansible.legacy.file"]:
        if file_key in task:
            file_dict = task[file_key]
            if isinstance(file_dict, dict):
                path = file_dict.get("path") or file_dict.get("dest")
            else:
                path = file_dict
            if path:
                watch_files.add(path)
            break

    # Stat tasks (check for file paths)
    for stat_key in ["stat", "ansible.builtin.stat", "ansible.legacy.stat"]:
        if stat_key in task:
            stat_dict = task[stat_key]
            if isinstance(stat_dict, dict):
                path = stat_dict.get("path")
                if path:
                    watch_files.add(path)
            break

    # Find tasks (check for search paths)
    for find_key in ["find", "ansible.builtin.find", "ansible.legacy.find"]:
        if find_key in task:
            find_dict = task[find_key]
            if isinstance(find_dict, dict):
                paths = find_dict.get("paths")
                if paths:
                    if isinstance(paths, list):
                        watch_files.update(paths)
                    else:
                        watch_files.add(paths)
            break

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

    # Extract dependencies from when conditions
    if "when" in task:
        when_str = str(task["when"])
        # Look for references to other tasks/resources
        # Pattern: "resource_name is defined" or "resource_name is not defined"
        deps = re.findall(r'(\w+)\s+is\s+(?:not\s+)?defined', when_str)
        result["depends_on"].extend(deps)

    return result


def find_role_path(role_name: str, base_path: Path) -> Optional[Path]:
    """Find the path to a role directory.

    Searches in common Ansible role locations:
    - roles/{role_name}/
    - {base_path}/roles/{role_name}/
    - {base_path}/../roles/{role_name}/

    Args:
        role_name: Name of the role to find.
        base_path: Base path to search from.

    Returns:
        Path to role directory if found, None otherwise.
    """
    search_paths = [
        base_path / "roles" / role_name,
        base_path.parent / "roles" / role_name,
        base_path.parent.parent / "roles" / role_name,
        Path("roles") / role_name,
        Path(".") / "roles" / role_name,
    ]

    for search_path in search_paths:
        if search_path.exists() and search_path.is_dir():
            return search_path

    return None


def resolve_playbook_path(include_path: str, base_path: Path) -> Optional[Path]:
    """Resolve a relative playbook include path to an absolute path.

    Args:
        include_path: Relative path from include_tasks/import_tasks.
        base_path: Base path of the current playbook.

    Returns:
        Resolved Path if found, None otherwise.
    """
    # Try relative to current playbook
    candidate = base_path.parent / include_path
    if candidate.exists():
        return candidate

    # Try relative to common playbook locations
    search_paths = [
        base_path.parent / "tasks" / include_path,
        base_path.parent / include_path,
        Path("tasks") / include_path,
        Path(".") / include_path,
    ]

    for search_path in search_paths:
        if search_path.exists():
            return search_path

    return None


def analyze_role(role_path: Path, base_path: Path, visited: Set[Path]) -> List[Dict]:
    """Recursively analyze an Ansible role and extract all tasks.

    Args:
        role_path: Path to the role directory.
        base_path: Base path for resolving relative paths.
        visited: Set of already visited paths to prevent infinite recursion.

    Returns:
        List of task metadata dictionaries from the role.
    """
    if role_path in visited:
        return []  # Prevent infinite recursion

    visited.add(role_path)
    all_tasks = []
    role_name = role_path.name

    # Analyze main tasks
    main_tasks_path = role_path / "tasks" / "main.yml"
    if not main_tasks_path.exists():
        main_tasks_path = role_path / "tasks" / "main.yaml"

    if main_tasks_path.exists():
        try:
            # Pass role name as prefix - analyze_ansible_playbook will prefix all tasks
            tasks = analyze_ansible_playbook(main_tasks_path, visited, source_prefix=role_name)
            all_tasks.extend(tasks)
        except BuilderError:
            pass  # Skip if role tasks can't be parsed

    # Analyze handlers
    handlers_path = role_path / "handlers" / "main.yml"
    if not handlers_path.exists():
        handlers_path = role_path / "handlers" / "main.yaml"

    if handlers_path.exists():
        try:
            # Pass role name as prefix for handlers too
            tasks = analyze_ansible_playbook(handlers_path, visited, source_prefix=role_name)
            # Mark handlers appropriately
            for task in tasks:
                if "triggers" not in task or not task["triggers"]:
                    task["triggers"] = [f"notify_{task['name']}"]
            all_tasks.extend(tasks)
        except BuilderError:
            pass

    return all_tasks


def infer_dependencies_from_playbook(
    all_tasks: List[Dict], play_tasks: List[Dict]
) -> None:
    """Infer dependencies between tasks based on execution order and variable usage.

    This function analyzes task order and register variables to infer dependencies.
    If task B uses a variable registered by task A, task B depends on task A.
    Also infers handler triggers from notify statements.

    Args:
        all_tasks: List of all task metadata dictionaries (will be modified in-place).
        play_tasks: List of tasks from the playbook in execution order.
    """
    if not all_tasks or not play_tasks:
        return

    # Build a map of task names to their metadata
    task_map = {task["name"]: task for task in all_tasks}

    # Track registered variables and which tasks register them
    registered_vars: Dict[str, str] = {}  # var_name -> task_name

    # Analyze tasks in order
    for task_dict in play_tasks:
        if not isinstance(task_dict, dict):
            continue

        task_name = None
        if "name" in task_dict:
            task_name = task_dict["name"]
        elif "include_tasks" in task_dict:
            task_name = task_dict["include_tasks"]
        elif "import_tasks" in task_dict:
            task_name = task_dict["import_tasks"]
        elif "include_role" in task_dict:
            role_dict = task_dict["include_role"]
            task_name = role_dict.get("name") if isinstance(role_dict, dict) else role_dict
        elif "import_role" in task_dict:
            role_dict = task_dict["import_role"]
            task_name = role_dict.get("name") if isinstance(role_dict, dict) else role_dict

        if not task_name or task_name not in task_map:
            continue

        task_meta = task_map[task_name]

        # Check for register: this task registers a variable
        if "register" in task_dict:
            reg_var = task_dict["register"]
            registered_vars[reg_var] = task_name

        # Check for variables used in this task that were registered by previous tasks
        task_str = yaml.dump(task_dict, default_flow_style=False)
        var_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[|}]'

        for match in re.finditer(var_pattern, task_str):
            var_name = match.group(1)
            # Skip common Ansible variables
            if var_name in ["item", "ansible", "hostvars", "group_names", "groups", "inventory_hostname"]:
                continue

            # If this variable was registered by another task, add dependency
            if var_name in registered_vars:
                dep_task = registered_vars[var_name]
                if dep_task != task_name:  # Don't depend on self
                    if dep_task not in task_meta["depends_on"]:
                        task_meta["depends_on"].append(dep_task)

        # Check for notify: this task triggers handlers
        if "notify" in task_dict:
            notify_targets = task_dict["notify"]
            if isinstance(notify_targets, list):
                for handler_name in notify_targets:
                    # Find handler task and add trigger relationship
                    for other_task in all_tasks:
                        if other_task["name"] == handler_name:
                            if "triggers" not in other_task:
                                other_task["triggers"] = []
                            if task_name not in other_task["triggers"]:
                                other_task["triggers"].append(task_name)
            elif isinstance(notify_targets, str):
                # Single handler
                for other_task in all_tasks:
                    if other_task["name"] == notify_targets:
                        if "triggers" not in other_task:
                            other_task["triggers"] = []
                        if task_name not in other_task["triggers"]:
                            other_task["triggers"].append(task_name)


def analyze_ansible_playbook(
    playbook_path: Union[str, Path], 
    visited: Optional[Set[Path]] = None,
    source_prefix: Optional[str] = None,
) -> List[Dict]:
    """Analyze an Ansible playbook and extract task metadata.

    Recursively expands included playbooks and roles.

    Args:
        playbook_path: Path to the Ansible playbook file.
        visited: Set of already visited paths to prevent infinite recursion.
        source_prefix: Optional prefix to add to all task names from this playbook.

    Returns:
        List of task metadata dictionaries.

    Raises:
        BuilderError: If the playbook cannot be parsed or analyzed.
    """
    if visited is None:
        visited = set()

    playbook_path = Path(playbook_path).resolve()

    if playbook_path in visited:
        return []  # Prevent infinite recursion

    if not playbook_path.exists():
        raise BuilderError(f"Playbook not found: {playbook_path}")

    visited.add(playbook_path)

    # Determine prefix for this playbook if not provided
    if source_prefix is None:
        # Use playbook filename (without extension) as prefix
        source_prefix = playbook_path.stem

    try:
        with open(playbook_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BuilderError(f"Failed to parse playbook {playbook_path}: {e}")
    except IOError as e:
        raise BuilderError(f"Failed to read playbook {playbook_path}: {e}")

    if content is None:
        return []

    all_tasks = []

    # Check if this is a role task file (list of tasks) or a playbook (dict with tasks/hosts/etc)
    if isinstance(content, list):
        # Could be a list of plays OR a list of tasks (role task file)
        # Check first item to determine
        if content and isinstance(content[0], dict):
            # Check if first item looks like a play (has hosts/tasks) or a task (has name/action/module)
            first_item = content[0]
            if "hosts" in first_item or "tasks" in first_item or "roles" in first_item:
                # It's a list of plays
                plays = content
            else:
                # It's a list of tasks (role task file)
                tasks = content
                # Process tasks directly (skip the play loop)
                for task in tasks:
                    if isinstance(task, dict):
                        # Handle include_tasks / import_tasks in role task files
                        if "include_tasks" in task or "import_tasks" in task:
                            include_path_str = task.get("include_tasks") or task.get("import_tasks")
                            if include_path_str:
                                included_path = resolve_playbook_path(include_path_str, playbook_path)
                                if included_path:
                                    try:
                                        include_prefix = included_path.stem
                                        included_tasks = analyze_ansible_playbook(included_path, visited, source_prefix=include_prefix)
                                        all_tasks.extend(included_tasks)
                                    except BuilderError:
                                        # If include fails, analyze task as-is
                                        task_meta = analyze_ansible_task(task, playbook_path)
                                        if task_meta:
                                            if source_prefix and not task_meta["name"].startswith(f"{source_prefix}_"):
                                                task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                            all_tasks.append(task_meta)
                                else:
                                    # Include path not found, analyze task as-is
                                    task_meta = analyze_ansible_task(task, playbook_path)
                                    if task_meta:
                                        if source_prefix and not task_meta["name"].startswith(f"{source_prefix}_"):
                                            task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                        all_tasks.append(task_meta)
                            else:
                                task_meta = analyze_ansible_task(task, playbook_path)
                                if task_meta:
                                    if source_prefix and not task_meta["name"].startswith(f"{source_prefix}_"):
                                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Regular task
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if source_prefix and not task_meta["name"].startswith(f"{source_prefix}_"):
                                    task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                all_tasks.append(task_meta)
                
                # Infer dependencies
                if all_tasks and tasks:
                    infer_dependencies_from_playbook(all_tasks, tasks)
                
                return all_tasks
        else:
            plays = content
    else:
        plays = [content]

    # Process playbook structure (has plays with tasks/handlers)
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
                    # Prefix with source and mark as handler-triggered
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                    task_meta["triggers"] = [f"notify_{task_meta['name']}"]
                    all_tasks.append(task_meta)

        # Check for pre_tasks and post_tasks
        pre_tasks = play.get("pre_tasks", [])
        post_tasks = play.get("post_tasks", [])

        # Analyze regular tasks (with recursive expansion)
        for task in tasks:
            if isinstance(task, dict):
                # Handle include_tasks / import_tasks - recursively expand
                if "include_tasks" in task or "import_tasks" in task:
                    include_path_str = task.get("include_tasks") or task.get("import_tasks")
                    if include_path_str:
                        included_path = resolve_playbook_path(include_path_str, playbook_path)
                        if included_path:
                            try:
                                # Use included playbook name as prefix
                                include_prefix = included_path.stem
                                included_tasks = analyze_ansible_playbook(included_path, visited, source_prefix=include_prefix)
                                all_tasks.extend(included_tasks)
                            except BuilderError as e:
                                # If include fails, still analyze the include task itself
                                task_meta = analyze_ansible_task(task, playbook_path)
                                if task_meta:
                                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Include path not found, analyze task as-is
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                    task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                all_tasks.append(task_meta)
                    else:
                        # No include path string, analyze task as-is
                        task_meta = analyze_ansible_task(task, playbook_path)
                        if task_meta:
                            if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                            all_tasks.append(task_meta)
                # Handle include_role / import_role - recursively expand
                elif "include_role" in task or "import_role" in task:
                    role_name = None
                    if "include_role" in task:
                        role_dict = task["include_role"]
                        role_name = role_dict.get("name") if isinstance(role_dict, dict) else role_dict
                    elif "import_role" in task:
                        role_dict = task["import_role"]
                        role_name = role_dict.get("name") if isinstance(role_dict, dict) else role_dict

                    if role_name:
                        role_path = find_role_path(role_name, playbook_path)
                        if role_path:
                            try:
                                role_tasks = analyze_role(role_path, playbook_path, visited)
                                all_tasks.extend(role_tasks)
                            except BuilderError:
                                # If role expansion fails, still analyze the role task itself
                                task_meta = analyze_ansible_task(task, playbook_path)
                                if task_meta:
                                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Role not found, analyze task as-is
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                    task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                                all_tasks.append(task_meta)
                    else:
                        task_meta = analyze_ansible_task(task, playbook_path)
                        if task_meta:
                            if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                                task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                            all_tasks.append(task_meta)
                else:
                    # Regular task
                    task_meta = analyze_ansible_task(task, playbook_path)
                    if task_meta:
                        if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                            task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                        all_tasks.append(task_meta)

        # Analyze pre_tasks
        for task in pre_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                    all_tasks.append(task_meta)

        # Analyze post_tasks
        for task in post_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}_"):
                        task_meta["name"] = f"{source_prefix}_{task_meta['name']}"
                    all_tasks.append(task_meta)

        # Infer dependencies from task order and variable usage
        # Combine all tasks in execution order for analysis
        all_play_tasks = pre_tasks + tasks + post_tasks
        if all_tasks and all_play_tasks:
            infer_dependencies_from_playbook(all_tasks, all_play_tasks)

    return all_tasks


def build_dependency_map_from_playbooks(
    playbook_paths: List[Union[str, Path]],
    output_path: Optional[Union[str, Path]] = None,
    verbose: bool = False,
    known_variables: Optional[Dict] = None,
) -> DependencyMap:
    """Build a dependency map by analyzing multiple Ansible playbooks.

    Args:
        playbook_paths: List of paths to Ansible playbook files.
        output_path: Optional path to write the generated dependency map YAML file.
        verbose: If True, print debug information about discovered tasks.
        known_variables: Optional dictionary of known variables to filter from requires_vars.

    Returns:
        Validated DependencyMap instance.

    Raises:
        BuilderError: If analysis fails or dependency map is invalid.
    """
    all_tasks = []

    for playbook_path in playbook_paths:
        try:
            # Use playbook filename as prefix for all tasks from this playbook
            playbook_prefix = Path(playbook_path).stem
            tasks = analyze_ansible_playbook(playbook_path, source_prefix=playbook_prefix)
            if verbose:
                print(f"Found {len(tasks)} tasks in {playbook_path} (prefix: {playbook_prefix})")
            all_tasks.extend(tasks)
        except BuilderError as e:
            raise BuilderError(f"Failed to analyze {playbook_path}: {e}")

    if not all_tasks:
        raise BuilderError("No tasks found in playbooks")

    # Filter out known variables from requires_vars
    if known_variables:
        known_var_names = set(known_variables.keys())
        # Also check nested keys (e.g., if environment_servers is a dict, its keys are known)
        for var_name, var_value in known_variables.items():
            if isinstance(var_value, dict):
                known_var_names.update(var_value.keys())
        
        for task in all_tasks:
            if "requires_vars" in task:
                # Remove variables that are known from inventory/vars
                task["requires_vars"] = [
                    var for var in task["requires_vars"]
                    if var not in known_var_names
                ]

    if verbose:
        print(f"Total tasks before deduplication: {len(all_tasks)}")
        task_names = [task["name"] for task in all_tasks]
        duplicates = [name for name in task_names if task_names.count(name) > 1]
        if duplicates:
            print(f"Duplicate task names found: {set(duplicates)}")

    # Deduplicate tasks by name (keep first occurrence)
    # Note: This might remove tasks from included playbooks/roles if they have the same name
    seen_names = set()
    unique_tasks = []
    for task in all_tasks:
        if task["name"] not in seen_names:
            unique_tasks.append(task)
            seen_names.add(task["name"])
        elif verbose:
            print(f"Skipping duplicate task: {task['name']}")

    if verbose:
        print(f"Tasks after deduplication: {len(unique_tasks)}")

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
    verbose: bool = False,
    known_variables: Optional[Dict] = None,
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

    return build_dependency_map_from_playbooks(
        playbook_paths, output_path, verbose=verbose, known_variables=known_variables
    )
