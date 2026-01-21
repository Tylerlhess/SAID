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
]
