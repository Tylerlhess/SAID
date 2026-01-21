"""SAID - Smart Ansible Incremental Deployer.

An automation wrapper for Ansible that eliminates redundant tasks by analyzing
Git diffs and executing only the minimum required operations.
"""

__version__ = "0.1.0"

from said.dag_builder import CycleDetectedError, DAGError, DependencyGraph
from said.git_detector import GitDetector, GitDetectorError
from said.matcher import (
    get_tasks_for_changed_files,
    match_file_to_tasks,
    match_files_to_tasks,
)
from said.parser import (
    ParserError,
    clear_dependency_map_cache,
    discover_dependency_map,
    parse_dependency_map,
    parse_inline_metadata,
    parse_playbook_directory,
    parse_yaml_file,
)
from said.resolver import (
    DependencyResolver,
    ResolverError,
    resolve_dependencies,
)
from said.schema import (
    DependencyMap,
    SchemaError,
    TaskMetadata,
    validate_dependency_map,
    validate_task_metadata,
)
from said.state_store import FileStateStore, StateStore, StateStoreError
from said.validator import (
    MissingVariableError,
    ValidationError,
    VariableValidator,
    check_variables_required,
    validate_variables,
)
from said.orchestrator import AnsibleOrchestrator, OrchestratorError
from said.coordinator import CoordinatorError, WorkflowCoordinator
from said.builder import (
    BuilderError,
    analyze_ansible_playbook,
    analyze_ansible_task,
    build_dependency_map_from_directory,
    build_dependency_map_from_playbooks,
    find_role_path,
    resolve_playbook_path,
)
from said.inventory_loader import (
    InventoryLoaderError,
    discover_group_vars,
    discover_host_vars,
    load_all_variables,
    load_group_vars,
    load_host_vars,
    load_inventory_variables,
)

__all__ = [
    "__version__",
    # Git detector
    "GitDetector",
    "GitDetectorError",
    # State store
    "StateStore",
    "FileStateStore",
    "StateStoreError",
    # Schema
    "TaskMetadata",
    "DependencyMap",
    "SchemaError",
    "validate_task_metadata",
    "validate_dependency_map",
    # Parser
    "ParserError",
    "parse_yaml_file",
    "parse_dependency_map",
    "parse_inline_metadata",
    "parse_playbook_directory",
    "discover_dependency_map",
    "clear_dependency_map_cache",
    # DAG builder
    "DependencyGraph",
    "DAGError",
    "CycleDetectedError",
    # Matcher
    "match_file_to_tasks",
    "match_files_to_tasks",
    "get_tasks_for_changed_files",
    # Resolver
    "DependencyResolver",
    "ResolverError",
    "resolve_dependencies",
    # Validator
    "VariableValidator",
    "ValidationError",
    "MissingVariableError",
    "validate_variables",
    "check_variables_required",
    # Orchestrator
    "AnsibleOrchestrator",
    "OrchestratorError",
    # Coordinator
    "WorkflowCoordinator",
    "CoordinatorError",
    # Builder
    "BuilderError",
    "analyze_ansible_playbook",
    "analyze_ansible_task",
    "build_dependency_map_from_directory",
    "build_dependency_map_from_playbooks",
    "find_role_path",
    "resolve_playbook_path",
    # Inventory Loader
    "InventoryLoaderError",
    "load_inventory_variables",
    "load_group_vars",
    "load_host_vars",
    "discover_group_vars",
    "discover_host_vars",
    "load_all_variables",
]
