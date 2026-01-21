"""Ansible inventory and variable file loader.

This module provides functionality to load variables from Ansible inventory files,
group_vars, and host_vars directories.
"""

import configparser
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml


class InventoryLoaderError(Exception):
    """Base exception for inventory loader errors."""

    pass


def load_yaml_file(file_path: Path) -> Dict:
    """Load a YAML file and return its contents.

    Args:
        file_path: Path to the YAML file.

    Returns:
        Dictionary containing the parsed YAML content.

    Raises:
        InventoryLoaderError: If the file cannot be read or parsed.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
            return content if isinstance(content, dict) else {}
    except yaml.YAMLError as e:
        raise InventoryLoaderError(f"Failed to parse YAML file {file_path}: {e}")
    except IOError as e:
        raise InventoryLoaderError(f"Failed to read file {file_path}: {e}")


def load_group_vars(group_vars_path: Union[str, Path]) -> Dict:
    """Load variables from a group_vars file or directory.

    Args:
        group_vars_path: Path to a group_vars file or directory.

    Returns:
        Dictionary of variables loaded from group_vars.

    Raises:
        InventoryLoaderError: If the path cannot be read.
    """
    group_vars_path = Path(group_vars_path)

    if not group_vars_path.exists():
        raise InventoryLoaderError(f"Group vars path not found: {group_vars_path}")

    variables = {}

    if group_vars_path.is_file():
        # Single file
        if group_vars_path.suffix in [".yml", ".yaml"]:
            variables.update(load_yaml_file(group_vars_path))
    elif group_vars_path.is_dir():
        # Directory - load all YAML files
        for var_file in group_vars_path.glob("*.yml"):
            try:
                variables.update(load_yaml_file(var_file))
            except InventoryLoaderError:
                pass  # Skip files that can't be parsed
        for var_file in group_vars_path.glob("*.yaml"):
            try:
                variables.update(load_yaml_file(var_file))
            except InventoryLoaderError:
                pass

    return variables


def load_host_vars(host_vars_path: Union[str, Path]) -> Dict:
    """Load variables from a host_vars file or directory.

    Args:
        host_vars_path: Path to a host_vars file or directory.

    Returns:
        Dictionary of variables loaded from host_vars.

    Raises:
        InventoryLoaderError: If the path cannot be read.
    """
    host_vars_path = Path(host_vars_path)

    if not host_vars_path.exists():
        raise InventoryLoaderError(f"Host vars path not found: {host_vars_path}")

    variables = {}

    if host_vars_path.is_file():
        # Single file
        if host_vars_path.suffix in [".yml", ".yaml"]:
            variables.update(load_yaml_file(host_vars_path))
    elif host_vars_path.is_dir():
        # Directory - load all YAML files
        for var_file in host_vars_path.glob("*.yml"):
            try:
                variables.update(load_yaml_file(var_file))
            except InventoryLoaderError:
                pass
        for var_file in host_vars_path.glob("*.yaml"):
            try:
                variables.update(load_yaml_file(var_file))
            except InventoryLoaderError:
                pass

    return variables


def load_inventory_variables(inventory_path: Union[str, Path]) -> Dict:
    """Load variables from an Ansible inventory file.

    Supports both YAML and INI format inventory files.

    Args:
        inventory_path: Path to the inventory file.

    Returns:
        Dictionary of variables from the inventory.

    Raises:
        InventoryLoaderError: If the inventory cannot be read.
    """
    inventory_path = Path(inventory_path)

    if not inventory_path.exists():
        raise InventoryLoaderError(f"Inventory file not found: {inventory_path}")

    variables = {}

    # Try YAML format first
    if inventory_path.suffix in [".yml", ".yaml"]:
        try:
            content = load_yaml_file(inventory_path)
            if isinstance(content, dict):
                # Extract variables from inventory structure
                if "all" in content and "vars" in content["all"]:
                    variables.update(content["all"]["vars"])
                # Also check for group vars in inventory
                for group_name, group_data in content.items():
                    if isinstance(group_data, dict) and "vars" in group_data:
                        variables.update(group_data["vars"])
        except InventoryLoaderError:
            pass
    else:
        # Try INI format
        try:
            config = configparser.ConfigParser(allow_no_value=True)
            config.read(inventory_path)
            # INI format doesn't typically have vars, but we can extract host/group info
            # Variables are usually in group_vars/host_vars
            pass
        except Exception:
            pass

    return variables


def discover_group_vars(inventory_dir: Optional[Path] = None) -> Dict:
    """Auto-discover and load group_vars from common locations.

    Searches for group_vars in:
    - inventory_dir/group_vars/
    - inventory_dir/../group_vars/
    - ./group_vars/
    - ./inventories/*/group_vars/

    Args:
        inventory_dir: Optional inventory directory to search from.

    Returns:
        Dictionary of all discovered group variables.
    """
    variables = {}
    search_paths = []

    if inventory_dir:
        inventory_dir = Path(inventory_dir)
        search_paths.extend([
            inventory_dir / "group_vars",
            inventory_dir.parent / "group_vars",
        ])

    # Add common locations
    search_paths.extend([
        Path("group_vars"),
        Path("inventories") / "group_vars",
    ])

    # Search in inventory subdirectories
    inventories_dir = Path("inventories")
    if inventories_dir.exists():
        for inv_dir in inventories_dir.iterdir():
            if inv_dir.is_dir():
                group_vars_dir = inv_dir / "group_vars"
                if group_vars_dir.exists():
                    search_paths.append(group_vars_dir)

    # Load from all found locations
    for search_path in search_paths:
        if search_path.exists() and search_path.is_dir():
            for var_file in search_path.glob("*.yml"):
                try:
                    variables.update(load_yaml_file(var_file))
                except InventoryLoaderError:
                    pass
            for var_file in search_path.glob("*.yaml"):
                try:
                    variables.update(load_yaml_file(var_file))
                except InventoryLoaderError:
                    pass

    return variables


def discover_host_vars(inventory_dir: Optional[Path] = None) -> Dict:
    """Auto-discover and load host_vars from common locations.

    Similar to discover_group_vars but for host_vars.

    Args:
        inventory_dir: Optional inventory directory to search from.

    Returns:
        Dictionary of all discovered host variables.
    """
    variables = {}
    search_paths = []

    if inventory_dir:
        inventory_dir = Path(inventory_dir)
        search_paths.extend([
            inventory_dir / "host_vars",
            inventory_dir.parent / "host_vars",
        ])

    # Add common locations
    search_paths.extend([
        Path("host_vars"),
        Path("inventories") / "host_vars",
    ])

    # Search in inventory subdirectories
    inventories_dir = Path("inventories")
    if inventories_dir.exists():
        for inv_dir in inventories_dir.iterdir():
            if inv_dir.is_dir():
                host_vars_dir = inv_dir / "host_vars"
                if host_vars_dir.exists():
                    search_paths.append(host_vars_dir)

    # Load from all found locations
    for search_path in search_paths:
        if search_path.exists() and search_path.is_dir():
            for host_dir in search_path.iterdir():
                if host_dir.is_dir():
                    # Each host has its own directory
                    for var_file in host_dir.glob("*.yml"):
                        try:
                            variables.update(load_yaml_file(var_file))
                        except InventoryLoaderError:
                            pass
                    for var_file in host_dir.glob("*.yaml"):
                        try:
                            variables.update(load_yaml_file(var_file))
                        except InventoryLoaderError:
                            pass
                elif host_dir.is_file() and host_dir.suffix in [".yml", ".yaml"]:
                    # Single host var file
                    try:
                        variables.update(load_yaml_file(host_dir))
                    except InventoryLoaderError:
                        pass

    return variables


def load_all_variables(
    inventory_path: Optional[Union[str, Path]] = None,
    group_vars_path: Optional[Union[str, Path]] = None,
    host_vars_path: Optional[Union[str, Path]] = None,
    auto_discover: bool = True,
) -> Dict:
    """Load all variables from inventory, group_vars, and host_vars.

    Args:
        inventory_path: Path to inventory file.
        group_vars_path: Path to group_vars file or directory.
        host_vars_path: Path to host_vars file or directory.
        auto_discover: If True, auto-discover group_vars and host_vars.

    Returns:
        Combined dictionary of all variables.
    """
    all_variables = {}

    # Load from inventory
    if inventory_path:
        try:
            inventory_vars = load_inventory_variables(inventory_path)
            all_variables.update(inventory_vars)
        except InventoryLoaderError:
            pass

    # Load from explicit group_vars path
    if group_vars_path:
        try:
            group_vars = load_group_vars(group_vars_path)
            all_variables.update(group_vars)
        except InventoryLoaderError:
            pass

    # Load from explicit host_vars path
    if host_vars_path:
        try:
            host_vars = load_host_vars(host_vars_path)
            all_variables.update(host_vars)
        except InventoryLoaderError:
            pass

    # Auto-discover if requested
    if auto_discover:
        inventory_dir = None
        if inventory_path:
            inventory_dir = Path(inventory_path).parent

        try:
            discovered_group_vars = discover_group_vars(inventory_dir)
            all_variables.update(discovered_group_vars)
        except Exception:
            pass

        try:
            discovered_host_vars = discover_host_vars(inventory_dir)
            all_variables.update(discovered_host_vars)
        except Exception:
            pass

    return all_variables
