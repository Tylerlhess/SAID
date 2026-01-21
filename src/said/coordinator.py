"""Main workflow coordinator for SAID.

This module orchestrates the complete workflow:
1. Get changed files from git
2. Load dependency map
3. Match files to tasks
4. Resolve dependencies
5. Validate variables
6. Generate Ansible command
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from said.git_detector import GitDetector, GitDetectorError
from said.matcher import get_tasks_for_changed_files
from said.orchestrator import AnsibleOrchestrator, OrchestratorError
from said.parser import ParserError, discover_dependency_map, parse_dependency_map
from said.resolver import DependencyResolver, ResolverError
from said.schema import DependencyMap
from said.state_store import FileStateStore, StateStore, StateStoreError
from said.validator import (
    MissingVariableError,
    VariableValidator,
    ValidationError,
    check_variables_required,
)


class CoordinatorError(Exception):
    """Base exception for coordinator errors."""

    pass


class WorkflowCoordinator:
    """Coordinates the complete SAID workflow."""

    def __init__(
        self,
        repo_path: Optional[str] = None,
        dependency_map_path: Optional[str] = None,
        state_store: Optional[StateStore] = None,
        playbook_path: str = "playbook.yml",
        inventory: Optional[str] = None,
        variables: Optional[Dict[str, any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the workflow coordinator.

        Args:
            repo_path: Path to the git repository. If None, uses current working directory.
            dependency_map_path: Path to dependency_map.yml. If None, auto-discovers.
            state_store: State store instance. If None, creates a FileStateStore.
            playbook_path: Path to the Ansible playbook. Defaults to "playbook.yml".
            inventory: Path to Ansible inventory file. Optional.
            variables: Dictionary of available variables for validation. Optional.
            logger: Logger instance. If None, creates a basic logger.
        """
        self.repo_path = repo_path
        self.dependency_map_path = dependency_map_path
        self.playbook_path = playbook_path
        self.inventory = inventory
        self.variables = variables or {}

        # Initialize logger
        if logger is None:
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        else:
            self.logger = logger

        # Initialize git detector
        try:
            self.git_detector = GitDetector(repo_path)
        except GitDetectorError as e:
            raise CoordinatorError(f"Failed to initialize git detector: {e}")

        # Initialize state store
        if state_store is None:
            self.state_store = FileStateStore()
        else:
            self.state_store = state_store

        # Will be initialized when dependency map is loaded
        self.dependency_map: Optional[DependencyMap] = None
        self.resolver: Optional[DependencyResolver] = None
        self.orchestrator: Optional[AnsibleOrchestrator] = None

    def load_dependency_map(self) -> DependencyMap:
        """Load the dependency map from file or auto-discover it.

        Returns:
            Loaded DependencyMap instance.

        Raises:
            CoordinatorError: If the dependency map cannot be loaded.
        """
        try:
            if self.dependency_map_path:
                self.dependency_map = parse_dependency_map(self.dependency_map_path)
                self.logger.info(
                    f"Loaded dependency map from {self.dependency_map_path}"
                )
            else:
                self.dependency_map = discover_dependency_map()
                if self.dependency_map is None:
                    raise CoordinatorError(
                        "Could not find dependency_map.yml. "
                        "Please specify --dependency-map or ensure it exists in a standard location."
                    )
                self.logger.info("Auto-discovered dependency map")

            # Initialize resolver and orchestrator
            self.resolver = DependencyResolver(self.dependency_map)
            self.orchestrator = AnsibleOrchestrator(
                playbook_path=self.playbook_path,
                inventory=self.inventory,
            )

            return self.dependency_map

        except ParserError as e:
            raise CoordinatorError(f"Failed to parse dependency map: {e}")
        except Exception as e:
            raise CoordinatorError(f"Unexpected error loading dependency map: {e}")

    def check_safety_conditions(
        self, changed_files: List[str], force_full_deploy: bool = False
    ) -> bool:
        """Check safety conditions that require full deploy.

        Safety checks:
        - If SAID code itself changed, force full deploy
        - If dependency_map.yml changed, force full deploy
        - If git repository is dirty, warn

        Args:
            changed_files: List of changed file paths.
            force_full_deploy: If True, skip checks and return True.

        Returns:
            True if full deploy should be forced, False otherwise.
        """
        if force_full_deploy:
            return True

        # Check if SAID code changed
        said_paths = [
            "src/said/",
            "said/",
            ".said/",
        ]
        for file_path in changed_files:
            for said_path in said_paths:
                if file_path.startswith(said_path):
                    self.logger.warning(
                        f"SAID code changed ({file_path}) - forcing full deploy for safety"
                    )
                    return True

        # Check if dependency_map.yml changed
        dependency_map_files = [
            "dependency_map.yml",
            "dependency_map.yaml",
            "ansible/dependency_map.yml",
            "playbooks/dependency_map.yml",
        ]
        for file_path in changed_files:
            if any(
                file_path.endswith(dep_file) or dep_file in file_path
                for dep_file in dependency_map_files
            ):
                self.logger.warning(
                    f"Dependency map changed ({file_path}) - forcing full deploy for safety"
                )
                return True

        # Check if git repository is dirty
        try:
            if self.git_detector.is_dirty():
                self.logger.warning(
                    "Git repository has uncommitted changes. "
                    "Consider committing changes before deployment."
                )
        except GitDetectorError:
            # If we can't check, continue anyway
            pass

        return False

    def get_changed_files(
        self,
        from_commit: Optional[str] = None,
        to_commit: str = "HEAD",
        use_state_store: bool = True,
    ) -> List[str]:
        """Get changed files between commits.

        Args:
            from_commit: Starting commit. If None and use_state_store is True,
                        uses last successful commit from state store.
            to_commit: Ending commit. Defaults to "HEAD".
            use_state_store: If True, use last successful commit if from_commit is None.

        Returns:
            List of changed file paths.

        Raises:
            CoordinatorError: If git operation fails.
        """
        try:
            # Determine from_commit
            if from_commit is None and use_state_store:
                from_commit = self.state_store.get_last_successful_commit()
                if from_commit:
                    self.logger.info(
                        f"Using last successful commit: {from_commit[:8]}..."
                    )
                else:
                    self.logger.info("No previous successful commit found, using all files")
                    # If no previous commit, we'll need to handle this differently
                    # For now, we'll compare against an empty tree
                    from_commit = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # Empty tree

            if from_commit is None:
                raise CoordinatorError(
                    "Cannot determine from_commit. "
                    "Please specify --from-commit or ensure state store has a previous commit."
                )

            changed_files = self.git_detector.get_changed_files(
                from_commit, to_commit
            )
            self.logger.info(f"Found {len(changed_files)} changed files")
            return changed_files

        except GitDetectorError as e:
            raise CoordinatorError(f"Failed to get changed files: {e}")

    def match_files_to_tasks(self, changed_files: List[str]) -> Set[str]:
        """Match changed files to tasks.

        Args:
            changed_files: List of changed file paths.

        Returns:
            Set of matched task names.

        Raises:
            CoordinatorError: If dependency map is not loaded or matching fails.
        """
        if self.dependency_map is None:
            raise CoordinatorError(
                "Dependency map not loaded. Call load_dependency_map() first."
            )

        try:
            matched_tasks = get_tasks_for_changed_files(
                changed_files, self.dependency_map
            )
            self.logger.info(
                f"Matched {len(matched_tasks)} tasks: {', '.join(sorted(matched_tasks))}"
            )
            return matched_tasks

        except Exception as e:
            raise CoordinatorError(f"Failed to match files to tasks: {e}")

    def resolve_dependencies(
        self, matched_tasks: Set[str], include_triggers: bool = True
    ) -> List[str]:
        """Resolve all dependencies for matched tasks.

        Args:
            matched_tasks: Set of initially matched task names.
            include_triggers: If True, also include triggered tasks.

        Returns:
            List of task names in execution order.

        Raises:
            CoordinatorError: If resolution fails.
        """
        if self.resolver is None:
            raise CoordinatorError(
                "Resolver not initialized. Call load_dependency_map() first."
            )

        try:
            execution_order = self.resolver.resolve(
                matched_tasks, include_triggers=include_triggers
            )
            self.logger.info(
                f"Resolved {len(execution_order)} tasks in execution order"
            )
            return execution_order

        except ResolverError as e:
            raise CoordinatorError(f"Failed to resolve dependencies: {e}")

    def validate_variables(
        self, task_names: Set[str], collect_all_errors: bool = False
    ) -> Optional[Dict]:
        """Validate that all required variables are present.

        Args:
            task_names: Set of task names to validate.
            collect_all_errors: If True, collect all errors and return error report instead of raising.

        Returns:
            If collect_all_errors is True, returns error report dict. Otherwise None.

        Raises:
            CoordinatorError: If validation fails and collect_all_errors is False.
        """
        if self.dependency_map is None:
            raise CoordinatorError(
                "Dependency map not loaded. Call load_dependency_map() first."
            )

        if collect_all_errors:
            from said.error_collector import validate_dependency_map_comprehensive
            from pathlib import Path

            # Use playbook directory as search base if available
            search_base = None
            if hasattr(self, "playbook_path") and self.playbook_path:
                search_base = Path(self.playbook_path).parent

            error_report = validate_dependency_map_comprehensive(
                self.dependency_map,
                task_names=task_names,
                variables=self.variables,
                search_base=search_base,
                search_for_suggestions=True,
            )
            if error_report.has_errors():
                return error_report.to_dict()
            return None

        try:
            check_variables_required(
                self.dependency_map, task_names, self.variables
            )
            self.logger.info("Variable validation passed")
            return None

        except MissingVariableError as e:
            raise CoordinatorError(
                f"Variable validation failed: {e}. "
                "Please ensure all required variables are defined."
            )
        except ValidationError as e:
            raise CoordinatorError(f"Variable validation error: {e}")

    def generate_ansible_command(
        self, task_names: List[str], dry_run: bool = False
    ) -> List[str]:
        """Generate Ansible command for the specified tasks.

        Args:
            task_names: List of task names in execution order.
            dry_run: If True, generate command with --check flag.

        Returns:
            List of command arguments.

        Raises:
            CoordinatorError: If command generation fails.
        """
        if self.orchestrator is None:
            raise CoordinatorError(
                "Orchestrator not initialized. Call load_dependency_map() first."
            )

        try:
            return self.orchestrator.generate_command(task_names, dry_run=dry_run)
        except OrchestratorError as e:
            raise CoordinatorError(f"Failed to generate Ansible command: {e}")

    def run_full_workflow(
        self,
        from_commit: Optional[str] = None,
        to_commit: str = "HEAD",
        include_triggers: bool = True,
        validate_vars: bool = True,
        dry_run: bool = False,
        full_deploy: bool = False,
        collect_all_errors: bool = False,
    ) -> Dict:
        """Run the complete SAID workflow.

        Args:
            from_commit: Starting commit. If None, uses last successful commit.
            to_commit: Ending commit. Defaults to "HEAD".
            include_triggers: If True, include triggered tasks.
            validate_vars: If True, validate required variables.
            dry_run: If True, generate command with --check flag.
            full_deploy: If True, execute all tasks regardless of changes.

        Returns:
            Dictionary containing:
            - changed_files: List of changed files
            - matched_tasks: Set of initially matched tasks
            - execution_order: List of tasks in execution order
            - command: List of command arguments
            - command_string: Shell-escaped command string
        """
        # Load dependency map
        self.load_dependency_map()

        # Get changed files
        if full_deploy:
            self.logger.info("Full deploy requested - executing all tasks")
            changed_files = []
            # Get all tasks
            matched_tasks = set(task.name for task in self.dependency_map.tasks)
        else:
            changed_files = self.get_changed_files(
                from_commit=from_commit, to_commit=to_commit
            )
            
            # Check safety conditions (may force full deploy)
            if self.check_safety_conditions(changed_files):
                self.logger.info("Safety check triggered - forcing full deploy")
                changed_files = []
                matched_tasks = set(task.name for task in self.dependency_map.tasks)
            elif not changed_files:
                self.logger.info("No changed files found")
                return {
                    "changed_files": [],
                    "matched_tasks": set(),
                    "execution_order": [],
                    "command": [],
                    "command_string": "",
                }
            else:
                # Match files to tasks
                matched_tasks = self.match_files_to_tasks(changed_files)

                if not matched_tasks:
                    self.logger.info("No tasks matched to changed files")
                    return {
                        "changed_files": changed_files,
                        "matched_tasks": set(),
                        "execution_order": [],
                        "command": [],
                        "command_string": "",
                    }

        # Resolve dependencies
        execution_order = self.resolve_dependencies(
            matched_tasks, include_triggers=include_triggers
        )

        if not execution_order:
            self.logger.info("No tasks to execute after dependency resolution")
            return {
                "changed_files": changed_files,
                "matched_tasks": matched_tasks,
                "execution_order": [],
                "command": [],
                "command_string": "",
            }

        # Validate variables
        validation_errors = None
        if validate_vars:
            validation_errors = self.validate_variables(
                set(execution_order), collect_all_errors=collect_all_errors
            )
            if validation_errors and not collect_all_errors:
                # If collect_all_errors is False, validate_variables will raise
                pass

        # Generate Ansible command
        command = self.generate_ansible_command(execution_order, dry_run=dry_run)
        command_string = self.orchestrator.generate_command_string(
            execution_order, dry_run=dry_run
        )

        result = {
            "changed_files": changed_files,
            "matched_tasks": matched_tasks,
            "execution_order": execution_order,
            "command": command,
            "command_string": command_string,
        }

        # Include validation errors if collected
        if validation_errors:
            result["validation_errors"] = validation_errors

        return result

    def update_successful_commit(self, commit_sha: str, environment: str = "default") -> None:
        """Update the last successful commit in the state store.

        Args:
            commit_sha: The commit SHA to store.
            environment: Environment name. Defaults to "default".

        Raises:
            CoordinatorError: If the update fails.
        """
        try:
            self.state_store.set_last_successful_commit(commit_sha, environment)
            self.logger.info(
                f"Updated last successful commit for {environment}: {commit_sha[:8]}..."
            )
        except StateStoreError as e:
            raise CoordinatorError(f"Failed to update successful commit: {e}")
