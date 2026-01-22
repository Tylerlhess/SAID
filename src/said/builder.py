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

    def __init__(self, message: str, error_context: Optional[Dict] = None):
        """Initialize builder error with optional context.

        Args:
            message: Error message.
            error_context: Optional dictionary with context for error enhancement
                         (e.g., tasks, dependency_map, known_variables).
        """
        super().__init__(message)
        self.error_context = error_context or {}


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
    # Also handle "variable is defined" patterns - these are variables, not task dependencies
    if "when" in task:
        when_str = str(task["when"])
        # Extract variables from {{ var }} patterns
        for match in re.finditer(var_pattern, when_str):
            var_name = match.group(1)
            if var_name not in ["item", "ansible", "hostvars", "group_names", "groups"]:
                requires_vars.add(var_name)
        
        # Extract variables from "variable is defined" or "variable is not defined" patterns
        # These are variable checks, not task dependencies
        defined_pattern = r'(\w+(?:\.\w+)*)\s+is\s+(?:not\s+)?defined'
        for match in re.finditer(defined_pattern, when_str):
            var_name = match.group(1)
            # Handle nested variables like "server_map.service"
            if '.' in var_name:
                # Add both the base variable and the full path
                base_var = var_name.split('.')[0]
                requires_vars.add(base_var)
                requires_vars.add(var_name)
            else:
                if var_name not in ["item", "ansible", "hostvars", "group_names", "groups", "inventory_hostname"]:
                    requires_vars.add(var_name)

        # Build metadata
    result = {
        "name": metadata["name"],
        "provides": [metadata["name"]],  # Default: task provides itself as resource
        "depends_on": [],
        "triggers": [],
        "watch_files": sorted(list(watch_files)) if watch_files else [],
        "requires_vars": sorted(list(requires_vars)) if requires_vars else [],
        "required_tasks": [],  # Will be populated during variable dependency analysis
    }
    
    # Track register and set_fact information for variable production analysis
    # Store this in a way that can be used later (we'll add it to provides if it's a variable)
    if "register" in task:
        reg_var = task["register"]
        # Add registered variable to provides so it can be tracked
        result["provides"].append(reg_var)
    
    # Track set_fact variables
    for set_fact_key in ["set_fact", "ansible.builtin.set_fact", "ansible.legacy.set_fact"]:
        if set_fact_key in task:
            set_fact_dict = task[set_fact_key]
            if isinstance(set_fact_dict, dict):
                # set_fact can set multiple variables - add them to provides
                for var_name in set_fact_dict.keys():
                    result["provides"].append(var_name)
            break

    # Extract dependencies from when conditions
    # NOTE: Variables used in "is defined" checks are VARIABLES, not task dependencies
    # They should go in requires_vars, not depends_on
    # Only actual task resources (from task.provides) should be in depends_on
    # We've already extracted variables from when conditions above, so we don't need to do it again here

    return result


def build_task_prefix(playbook_path: Path, base_path: Optional[Path] = None) -> str:
    """Build a path-based prefix for task names.
    
    For playbooks: playbook/{playbook_name}
    For roles: role/{role_name}/tasks/{task_file}
    
    Args:
        playbook_path: Path to the playbook/task file.
        base_path: Optional base path for relative path calculation.
    
    Returns:
        String prefix like "playbook/main" or "role/consul_keepalived/tasks/main"
    """
    playbook_path = Path(playbook_path).resolve()
    
    # Check if this is a role task file
    parts = playbook_path.parts
    if "roles" in parts:
        # Find the role name (directory after "roles")
        roles_idx = parts.index("roles")
        if roles_idx + 1 < len(parts):
            role_name = parts[roles_idx + 1]
            # Get the task file name (main.yml, handlers/main.yml, etc.)
            if "tasks" in parts:
                task_file = playbook_path.stem  # e.g., "main" from "main.yml"
                return f"role/{role_name}/tasks/{task_file}"
            elif "handlers" in parts:
                task_file = playbook_path.stem
                return f"role/{role_name}/handlers/{task_file}"
            else:
                # Fallback
                return f"role/{role_name}/{playbook_path.stem}"
    
    # It's a playbook
    playbook_name = playbook_path.stem
    return f"playbook/{playbook_name}"


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
            # Build path-based prefix for role tasks
            role_prefix = build_task_prefix(main_tasks_path)
            tasks = analyze_ansible_playbook(main_tasks_path, visited, source_prefix=role_prefix)
            all_tasks.extend(tasks)
        except BuilderError:
            pass  # Skip if role tasks can't be parsed

    # Analyze handlers
    handlers_path = role_path / "handlers" / "main.yml"
    if not handlers_path.exists():
        handlers_path = role_path / "handlers" / "main.yaml"

    if handlers_path.exists():
        try:
            # Build path-based prefix for role handlers
            handler_prefix = build_task_prefix(handlers_path)
            tasks = analyze_ansible_playbook(handlers_path, visited, source_prefix=handler_prefix)
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
        # Build path-based prefix (playbook/{name} or role/{name}/tasks/{file})
        source_prefix = build_task_prefix(playbook_path)

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
                                        include_prefix = build_task_prefix(included_path)
                                        included_tasks = analyze_ansible_playbook(included_path, visited, source_prefix=include_prefix)
                                        all_tasks.extend(included_tasks)
                                    except BuilderError:
                                        # If include fails, analyze task as-is
                                        task_meta = analyze_ansible_task(task, playbook_path)
                                        if task_meta:
                                            if source_prefix and not task_meta["name"].startswith(f"{source_prefix}:"):
                                                task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
                                            all_tasks.append(task_meta)
                                else:
                                    # Include path not found, analyze task as-is
                                    task_meta = analyze_ansible_task(task, playbook_path)
                                    if task_meta:
                                        if source_prefix and not task_meta["name"].startswith(f"{source_prefix}:"):
                                            task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
                                        all_tasks.append(task_meta)
                            else:
                                task_meta = analyze_ansible_task(task, playbook_path)
                                if task_meta:
                                    if source_prefix and not task_meta["name"].startswith(f"{source_prefix}:"):
                                        task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Regular task
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if source_prefix and not task_meta["name"].startswith(f"{source_prefix}:"):
                                    task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
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
        
        # Extract roles from play (roles: key at play level)
        play_roles = play.get("roles", [])
        
        # Process play-level roles
        for role_item in play_roles:
            role_name = None
            if isinstance(role_item, str):
                # Simple role name: roles: [role1, role2]
                role_name = role_item
            elif isinstance(role_item, dict):
                # Role with parameters: roles: [{ role: role1, vars: {...} }]
                # Can be: { role: "name" } or { name: "name" } or just the role name as key
                role_name = role_item.get("role") or role_item.get("name")
                # If still None, check if it's a dict with a single key (role name)
                if not role_name and len(role_item) == 1:
                    role_name = list(role_item.keys())[0]
            
            if role_name:
                role_path = find_role_path(role_name, playbook_path)
                if role_path:
                    try:
                        role_tasks = analyze_role(role_path, playbook_path, visited)
                        all_tasks.extend(role_tasks)
                    except BuilderError:
                        # If role expansion fails, skip it (role might not exist)
                        pass

        # Analyze handlers
        for handler in handlers:
            if isinstance(handler, dict):
                task_meta = analyze_ansible_task(handler, playbook_path)
                if task_meta:
                    # Prefix with source and mark as handler-triggered
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}:"):
                        task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
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
                                include_prefix = build_task_prefix(included_path)
                                included_tasks = analyze_ansible_playbook(included_path, visited, source_prefix=include_prefix)
                                all_tasks.extend(included_tasks)
                            except BuilderError as e:
                                # If include fails, still analyze the include task itself
                                task_meta = analyze_ansible_task(task, playbook_path)
                                if task_meta:
                                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                        task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Include path not found, analyze task as-is
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                    task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                                all_tasks.append(task_meta)
                    else:
                        # No include path string, analyze task as-is
                        task_meta = analyze_ansible_task(task, playbook_path)
                        if task_meta:
                            if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
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
                                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                        task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                                    all_tasks.append(task_meta)
                        else:
                            # Role not found, analyze task as-is
                            task_meta = analyze_ansible_task(task, playbook_path)
                            if task_meta:
                                if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                    task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                                all_tasks.append(task_meta)
                    else:
                        task_meta = analyze_ansible_task(task, playbook_path)
                        if task_meta:
                            if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                                task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                            all_tasks.append(task_meta)
                else:
                    # Regular task
                    task_meta = analyze_ansible_task(task, playbook_path)
                    if task_meta:
                        if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}/"):
                            task_meta["name"] = f"{source_prefix}/{task_meta['name']}"
                        all_tasks.append(task_meta)

        # Analyze pre_tasks
        for task in pre_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}:"):
                        task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
                    all_tasks.append(task_meta)

        # Analyze post_tasks
        for task in post_tasks:
            if isinstance(task, dict):
                task_meta = analyze_ansible_task(task, playbook_path)
                if task_meta:
                    if task_meta["name"] and not task_meta["name"].startswith(f"{source_prefix}:"):
                        task_meta["name"] = f"{source_prefix}:{task_meta['name']}"
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

    This function:
    1. Analyzes playbooks to extract task metadata
    2. Creates a dependency map
    3. Applies variable-based dependencies (maps requires_vars to producing tasks)
    4. Validates and returns the complete dependency map

    Args:
        playbook_paths: List of paths to Ansible playbook files.
        output_path: Optional path to write the generated dependency map YAML file.
        verbose: If True, print debug information about discovered tasks.
        known_variables: Optional dictionary of known variables to filter from requires_vars.

    Returns:
        Validated DependencyMap instance with variable-based dependencies applied.

    Raises:
        BuilderError: If analysis fails or dependency map is invalid.
    """
    all_tasks = []

    for playbook_path in playbook_paths:
        try:
            # Build path-based prefix for playbook tasks
            playbook_prefix = build_task_prefix(Path(playbook_path))
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
    # Create a temporary dependency map from tasks for error analysis (even if validation fails)
    temp_dependency_map = None
    try:
        # Try to create dependency map from tasks (may fail validation)
        dependency_map = validate_dependency_map({"tasks": unique_tasks})
        
        # Apply variable-based dependencies using two-pass analysis
        # This maps requires_vars to the tasks that produce those variables
        from said.variable_dependency_analyzer import map_variable_dependencies_to_tasks, build_producers_dictionary
        
        # Determine search base for variable file discovery
        search_base = None
        if playbook_paths:
            search_base = Path(playbook_paths[0]).parent
        elif directory:
            search_base = Path(directory)
        
        # Build producers dictionary (first pass)
        producers = build_producers_dictionary(
            dependency_map, search_base=search_base, known_variables=known_variables
        )
        
        # Map variable dependencies to task dependencies (second pass)
        variable_task_deps = map_variable_dependencies_to_tasks(dependency_map, producers)
        
        # Update each task's depends_on with variable-based dependencies
        # Also populate required_tasks: tasks that produce the required variables
        # Note: variable_task_deps contains resource names (variables), not task names
        task_map = {task.name: task for task in dependency_map.tasks}
        
        # Build a reverse map: for each variable, which tasks produce it?
        variable_to_producing_tasks: Dict[str, Set[str]] = {}
        for var_name, var_producers in producers.items():
            for producer in var_producers:
                if producer.source_type == "task" and producer.source_name in task_map:
                    producing_task = task_map[producer.source_name]
                    # Only include if the variable is actually in the task's provides
                    if var_name in producing_task.provides:
                        if var_name not in variable_to_producing_tasks:
                            variable_to_producing_tasks[var_name] = set()
                        variable_to_producing_tasks[var_name].add(producer.source_name)
        
        for task_name, resource_deps in variable_task_deps.items():
            if task_name in task_map:
                task = task_map[task_name]
                # Add variable-based dependencies (avoid duplicates)
                # These are resource names (variables) that should be in depends_on
                existing_deps = set(task.depends_on)
                new_deps = resource_deps - existing_deps
                if new_deps:
                    task.depends_on.extend(new_deps)
                
                # Populate required_tasks: tasks that produce variables this task requires
                # Exclude the current task from required_tasks (tasks shouldn't require themselves)
                required_task_set = set()
                for required_var in task.requires_vars:
                    if required_var in variable_to_producing_tasks:
                        # Filter out the current task - tasks shouldn't require themselves
                        producing_tasks = variable_to_producing_tasks[required_var] - {task_name}
                        required_task_set.update(producing_tasks)
                
                # Update required_tasks (avoid duplicates, maintain order)
                existing_required = set(task.required_tasks)
                new_required = required_task_set - existing_required
                if new_required:
                    task.required_tasks.extend(sorted(new_required))
        
        # Re-validate the dependency map after adding variable-based dependencies
        # This ensures all depends_on references are valid
        try:
            # Re-validate by checking that all depends_on items exist in provides
            all_provides = set()
            for task in dependency_map.tasks:
                all_provides.update(task.provides)
            
            for task in dependency_map.tasks:
                invalid_deps = set(task.depends_on) - all_provides
                if invalid_deps:
                    # This shouldn't happen if our logic is correct, but check anyway
                    if verbose:
                        print(f"Warning: Task '{task.name}' has invalid dependencies after variable mapping: {invalid_deps}")
        except Exception as e:
            if verbose:
                print(f"Warning: Error during dependency validation: {e}")
        
    except SchemaError as e:
        # If validation fails, create a partial dependency map for error analysis
        # This allows us to analyze variables even when validation fails
        from said.schema import TaskMetadata
        try:
            # Create TaskMetadata objects without validation
            temp_tasks = []
            for task_dict in unique_tasks:
                try:
                    temp_tasks.append(TaskMetadata(**task_dict))
                except Exception:
                    # Skip tasks that can't be created
                    pass
            
            # Create DependencyMap without calling __post_init__ (which does validation)
            from said.schema import DependencyMap
            temp_dependency_map = object.__new__(DependencyMap)
            temp_dependency_map.tasks = temp_tasks
        except Exception:
            # If we can't even create the temp map, just raise the original error
            temp_dependency_map = None
        
        # Extract register information from original task analysis
        # This helps identify which tasks produce which variables
        registered_vars_map = {}  # var_name -> task_name
        if temp_dependency_map:
            # Re-analyze to find register statements (we need the original playbook tasks)
            # For now, we'll rely on the variable dependency analyzer to find variables
            # But we can enhance this later if needed
            pass
        
        # Store context for error enhancement
        error_context = {
            "tasks": unique_tasks,
            "temp_dependency_map": temp_dependency_map,
            "known_variables": known_variables,
            "registered_vars": registered_vars_map,
        }
        raise BuilderError(f"Invalid dependency map structure: {e}", error_context=error_context)

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
                    "required_tasks": task.required_tasks,
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
