"""Dynamic search for variable definitions in Ansible files.

This module searches for where variables might be defined in various Ansible
file types including group_vars, host_vars, inventory files, playbooks, and roles.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml


def search_variable_in_yaml_file(
    file_path: Path, variable_name: str
) -> Optional[Dict]:
    """Search for a variable definition in a YAML file.

    Args:
        file_path: Path to the YAML file to search.
        variable_name: Name of the variable to search for.

    Returns:
        Dictionary with file path and context if found, None otherwise.
    """
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)

        if isinstance(content, dict):
            # Check if variable exists in the dict
            if variable_name in content:
                return {
                    "file": str(file_path),
                    "found": True,
                    "value_preview": str(content[variable_name])[:100] if content[variable_name] else None,
                }

            # Also check nested structures (for inventory files)
            if "vars" in content and isinstance(content["vars"], dict):
                if variable_name in content["vars"]:
                    return {
                        "file": str(file_path),
                        "found": True,
                        "value_preview": str(content["vars"][variable_name])[:100] if content["vars"][variable_name] else None,
                    }

            # Check in "all" group vars
            if "all" in content and isinstance(content["all"], dict):
                if "vars" in content["all"] and isinstance(content["all"]["vars"], dict):
                    if variable_name in content["all"]["vars"]:
                        return {
                            "file": str(file_path),
                            "found": True,
                            "value_preview": str(content["all"]["vars"][variable_name])[:100] if content["all"]["vars"][variable_name] else None,
                        }

    except (yaml.YAMLError, IOError):
        pass

    return None


def search_variable_in_text_file(
    file_path: Path, variable_name: str
) -> Optional[Dict]:
    """Search for a variable definition in a text file (INI format or playbook).

    Args:
        file_path: Path to the file to search.
        variable_name: Name of the variable to search for.

    Returns:
        Dictionary with file path and context if found, None otherwise.
    """
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Search for variable patterns
        for i, line in enumerate(lines):
            # Look for variable assignments: var_name = value or var_name: value
            pattern = rf"^\s*{re.escape(variable_name)}\s*[=:]\s*(.+)$"
            match = re.match(pattern, line.strip())
            if match:
                return {
                    "file": str(file_path),
                    "found": True,
                    "line_number": i + 1,
                    "line_preview": line.strip()[:100],
                }

            # Also check for YAML-style in playbooks
            if ":" in line and variable_name in line:
                # Simple heuristic - check if it looks like a variable definition
                if re.match(rf"^\s*{re.escape(variable_name)}\s*:", line):
                    return {
                        "file": str(file_path),
                        "found": True,
                        "line_number": i + 1,
                        "line_preview": line.strip()[:100],
                    }

    except IOError:
        pass

    return None


def find_variable_suggestions(
    variable_name: str, search_base: Optional[Path] = None
) -> Dict[str, List[Dict]]:
    """Find suggestions for where a variable might be defined.

    Searches in:
    - group_vars/ directories
    - host_vars/ directories
    - Inventory files (hosts.ini, hosts.yml)
    - Playbook files (*.yml, *.yaml)
    - Role defaults (roles/*/defaults/main.yml)
    - Role vars (roles/*/vars/main.yml)

    Args:
        variable_name: Name of the variable to search for.
        search_base: Base directory to search from. Defaults to current directory.

    Returns:
        Dictionary mapping file type categories to lists of found locations.
    """
    if search_base is None:
        search_base = Path.cwd()
    else:
        search_base = Path(search_base)

    suggestions = {
        "group_vars": [],
        "host_vars": [],
        "inventory": [],
        "playbooks": [],
        "role_defaults": [],
        "role_vars": [],
    }

    # Search group_vars
    group_vars_paths = [
        search_base / "group_vars",
        search_base / "inventories" / "group_vars",
    ]
    # Also search in inventory subdirectories
    inventories_dir = search_base / "inventories"
    if inventories_dir.exists():
        for inv_dir in inventories_dir.iterdir():
            if inv_dir.is_dir():
                group_vars_paths.append(inv_dir / "group_vars")

    for group_vars_path in group_vars_paths:
        if group_vars_path.exists() and group_vars_path.is_dir():
            for var_file in group_vars_path.glob("*.yml"):
                result = search_variable_in_yaml_file(var_file, variable_name)
                if result:
                    suggestions["group_vars"].append(result)
            for var_file in group_vars_path.glob("*.yaml"):
                result = search_variable_in_yaml_file(var_file, variable_name)
                if result:
                    suggestions["group_vars"].append(result)

    # Search host_vars
    host_vars_paths = [
        search_base / "host_vars",
        search_base / "inventories" / "host_vars",
    ]
    # Also search in inventory subdirectories
    if inventories_dir.exists():
        for inv_dir in inventories_dir.iterdir():
            if inv_dir.is_dir():
                host_vars_paths.append(inv_dir / "host_vars")

    for host_vars_path in host_vars_paths:
        if host_vars_path.exists() and host_vars_path.is_dir():
            for var_file in host_vars_path.glob("*.yml"):
                result = search_variable_in_yaml_file(var_file, variable_name)
                if result:
                    suggestions["host_vars"].append(result)
            for var_file in host_vars_path.glob("*.yaml"):
                result = search_variable_in_yaml_file(var_file, variable_name)
                if result:
                    suggestions["host_vars"].append(result)

    # Search inventory files
    inventory_patterns = [
        search_base / "hosts.ini",
        search_base / "hosts.yml",
        search_base / "hosts.yaml",
        search_base / "inventory.ini",
        search_base / "inventory.yml",
        search_base / "inventory.yaml",
    ]
    # Also search in inventories subdirectories
    if inventories_dir.exists():
        for inv_dir in inventories_dir.iterdir():
            if inv_dir.is_dir():
                inventory_patterns.extend([
                    inv_dir / "hosts.ini",
                    inv_dir / "hosts.yml",
                    inv_dir / "hosts.yaml",
                ])

    for inv_file in inventory_patterns:
        if inv_file.exists():
            result = search_variable_in_yaml_file(inv_file, variable_name)
            if result:
                suggestions["inventory"].append(result)
            else:
                # Try text search for INI files
                if inv_file.suffix == ".ini":
                    result = search_variable_in_text_file(inv_file, variable_name)
                    if result:
                        suggestions["inventory"].append(result)

    # Search playbook files (limited search to avoid too many results)
    playbook_patterns = [
        search_base / "*.yml",
        search_base / "*.yaml",
        search_base / "playbooks" / "*.yml",
        search_base / "playbooks" / "*.yaml",
    ]

    for pattern in playbook_patterns:
        for playbook_file in search_base.glob(pattern.name if "*" in str(pattern) else pattern):
            if playbook_file.is_file() and playbook_file.name not in ["dependency_map.yml"]:
                # Only search in vars sections of playbooks
                try:
                    with open(playbook_file, "r", encoding="utf-8") as f:
                        content = yaml.safe_load(f)
                    if isinstance(content, list):
                        for play in content:
                            if isinstance(play, dict) and "vars" in play:
                                if isinstance(play["vars"], dict) and variable_name in play["vars"]:
                                    suggestions["playbooks"].append({
                                        "file": str(playbook_file),
                                        "found": True,
                                        "value_preview": str(play["vars"][variable_name])[:100] if play["vars"][variable_name] else None,
                                    })
                except (yaml.YAMLError, IOError):
                    pass

    # Search role defaults
    roles_dir = search_base / "roles"
    if roles_dir.exists():
        for role_dir in roles_dir.iterdir():
            if role_dir.is_dir():
                defaults_file = role_dir / "defaults" / "main.yml"
                if defaults_file.exists():
                    result = search_variable_in_yaml_file(defaults_file, variable_name)
                    if result:
                        suggestions["role_defaults"].append(result)
                # Also check .yaml extension
                defaults_file = role_dir / "defaults" / "main.yaml"
                if defaults_file.exists():
                    result = search_variable_in_yaml_file(defaults_file, variable_name)
                    if result:
                        suggestions["role_defaults"].append(result)

    # Search role vars
    if roles_dir.exists():
        for role_dir in roles_dir.iterdir():
            if role_dir.is_dir():
                vars_file = role_dir / "vars" / "main.yml"
                if vars_file.exists():
                    result = search_variable_in_yaml_file(vars_file, variable_name)
                    if result:
                        suggestions["role_vars"].append(result)
                # Also check .yaml extension
                vars_file = role_dir / "vars" / "main.yaml"
                if vars_file.exists():
                    result = search_variable_in_yaml_file(vars_file, variable_name)
                    if result:
                        suggestions["role_vars"].append(result)

    # Remove empty categories
    return {k: v for k, v in suggestions.items() if v}


def find_all_variable_suggestions(
    variable_names: Set[str], search_base: Optional[Path] = None
) -> Dict[str, Dict[str, List[Dict]]]:
    """Find suggestions for multiple variables.

    Args:
        variable_names: Set of variable names to search for.
        search_base: Base directory to search from.

    Returns:
        Dictionary mapping variable names to their suggestion dictionaries.
    """
    results = {}
    for var_name in variable_names:
        suggestions = find_variable_suggestions(var_name, search_base)
        if suggestions:
            results[var_name] = suggestions
    return results
