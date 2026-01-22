"""Command-line interface for SAID."""

import sys
from pathlib import Path
from typing import Optional

import click

from said.coordinator import CoordinatorError, WorkflowCoordinator


def echo_if_not_json(message: str, json_mode: bool = False, **kwargs):
    """Echo a message only if JSON mode is not enabled.
    
    Args:
        message: Message to output.
        json_mode: If True, suppress output (JSON mode is active).
        **kwargs: Additional arguments to pass to click.echo.
    """
    if not json_mode:
        click.echo(message, **kwargs)
from said.inventory_loader import (
    load_all_variables,
    load_group_vars,
    load_host_vars,
)


@click.group()
@click.version_option(version="0.1.0", prog_name="said")
def cli():
    """SAID - Smart Ansible Incremental Deployer.

    An automation wrapper for Ansible that eliminates redundant tasks by analyzing
    Git diffs and executing only the minimum required operations.
    """
    pass


def _find_roles_directory(playbook_path: Path, inventory_path: Optional[Path] = None) -> Optional[Path]:
    """Find the roles directory relative to playbook or inventory.
    
    Searches in common locations:
    - {playbook_dir}/../roles/
    - {playbook_dir}/roles/
    - {inventory_dir}/../roles/
    - {inventory_dir}/roles/
    - ./roles/
    
    Args:
        playbook_path: Path to the playbook file.
        inventory_path: Optional path to inventory file.
        
    Returns:
        Path to roles directory if found, None otherwise.
    """
    playbook_dir = Path(playbook_path).parent.resolve()
    
    search_paths = [
        playbook_dir.parent / "roles",  # ../roles from playbook
        playbook_dir / "roles",  # roles/ in playbook directory
        Path("roles"),  # ./roles from current directory
        Path(".") / "roles",  # ./roles
    ]
    
    # Add inventory-based paths if inventory is provided
    if inventory_path:
        inventory_dir = Path(inventory_path).parent.resolve()
        search_paths.extend([
            inventory_dir.parent / "roles",  # ../roles from inventory
            inventory_dir / "roles",  # roles/ in inventory directory
        ])
    
    for search_path in search_paths:
        if search_path.exists() and search_path.is_dir():
            return search_path.resolve()
    
    return None


def _is_task_file(file_path: Path) -> bool:
    """Check if a file path is a role task file (not a playbook).
    
    Args:
        file_path: Path to check.
        
    Returns:
        True if the file appears to be a role task file, False otherwise.
    """
    file_path = Path(file_path).resolve()
    parts = file_path.parts
    
    # Check if path contains roles/*/tasks/ or roles/*/handlers/
    if "roles" in parts:
        roles_idx = parts.index("roles")
        if roles_idx + 1 < len(parts):
            # Check if it's in tasks/ or handlers/ subdirectory
            if "tasks" in parts or "handlers" in parts:
                return True
    
    # Also check if the file content is a list of tasks (not a playbook)
    # This is a heuristic - playbooks typically have "hosts" or are dicts with "tasks"
    try:
        import yaml
        with open(file_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
        
        # If it's a list and first item doesn't have "hosts" or "tasks" key, it's likely a task file
        if isinstance(content, list) and content:
            first_item = content[0]
            if isinstance(first_item, dict):
                if "hosts" not in first_item and "tasks" not in first_item and "roles" not in first_item:
                    # Likely a task file (list of tasks)
                    return True
    except Exception:
        # If we can't read/parse, assume it's not a task file
        pass
    
    return False


@cli.command()
@click.option(
    "--dependency-map",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Path to dependency_map.yml file. Auto-discovered if not specified.",
)
@click.option(
    "--from-commit",
    "-f",
    type=str,
    help="Starting commit SHA, branch, or tag. Uses last successful commit if not specified.",
)
@click.option(
    "--to-commit",
    "-t",
    type=str,
    default="HEAD",
    help="Ending commit SHA, branch, or tag. Defaults to HEAD.",
)
@click.option(
    "--repo-path",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    help="Path to git repository. Uses current directory if not specified.",
)
@click.option(
    "--playbook",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    default="playbook.yml",
    help="Path to Ansible playbook. Defaults to playbook.yml.",
)
@click.option(
    "--inventory",
    "-i",
    type=click.Path(exists=True, path_type=Path),
    help="Path to Ansible inventory file.",
)
@click.option(
    "--no-triggers",
    is_flag=True,
    help="Do not include triggered tasks (only dependencies).",
)
@click.option(
    "--no-validate",
    is_flag=True,
    help="Skip variable validation.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results in JSON format.",
)
@click.option(
    "--json-errors",
    is_flag=True,
    help="Output validation errors in JSON format (only if validation fails).",
)
def analyze(
    dependency_map: Optional[Path],
    from_commit: Optional[str],
    to_commit: str,
    repo_path: Optional[Path],
    playbook: Path,
    inventory: Optional[Path],
    no_triggers: bool,
    no_validate: bool,
    output_json: bool,
    json_errors: bool,
):
    """Analyze changes and generate execution plan without executing.

    This command shows what would be executed based on the current git state
    and dependency map, but does not run Ansible.
    """
    # Validate that playbook is not a task file
    if _is_task_file(playbook):
        # Try to extract role name for better error message
        role_name = None
        playbook_path = Path(playbook).resolve()
        parts = playbook_path.parts
        if "roles" in parts:
            roles_idx = parts.index("roles")
            if roles_idx + 1 < len(parts):
                role_name = parts[roles_idx + 1]
        
        error_msg = (
            f"Error: '{playbook}' is a role task file, not a playbook.\n"
            "Task files cannot be executed directly with ansible-playbook.\n\n"
            "To analyze/execute tasks from this role:\n"
            "  1. Use a playbook that includes this role, e.g.:\n"
            f"     said analyze -p playbook.yml" + (f" --inventory {inventory}" if inventory else "") + "\n"
            "  2. Ensure your playbook includes the role, e.g.:\n"
            f"     - hosts: all\n"
            f"       roles:\n"
            f"         - {role_name if role_name else 'your_role_name'}\n"
        )
        if json_errors or output_json:
            from said.error_collector import DependencyError, DependencyErrorReport
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="invalid_playbook",
                        task_name="analyze",
                        message=error_msg,
                        details={
                            "file_path": str(playbook),
                            "role_name": role_name,
                            "suggestion": "Use a playbook file that includes this role instead of the task file directly.",
                        },
                    )
                ],
                total_errors=1,
                error_summary={"invalid_playbook": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(error_msg, err=True)
        sys.exit(1)
    
    try:
        coordinator = WorkflowCoordinator(
            repo_path=str(repo_path) if repo_path else None,
            dependency_map_path=str(dependency_map) if dependency_map else None,
            playbook_path=str(playbook),
            inventory=str(inventory) if inventory else None,
        )

        result = coordinator.run_full_workflow(
            from_commit=from_commit,
            to_commit=to_commit,
            include_triggers=not no_triggers,
            validate_vars=not no_validate,
            dry_run=True,
            collect_all_errors=json_errors,
        )

        # Check for validation errors
        if "validation_errors" in result and result["validation_errors"]:
            if json_errors or output_json:
                import json

                error_output = {
                    "validation_errors": result["validation_errors"],
                    "workflow_result": {
                        "changed_files": result["changed_files"],
                        "matched_tasks": list(result["matched_tasks"]),
                        "execution_order": result["execution_order"],
                    },
                }
                click.echo(json.dumps(error_output, indent=2))
                sys.exit(1)
            else:
                from said.error_collector import DependencyErrorReport

                # Reconstruct error report for display
                error_report = DependencyErrorReport(
                    errors=[
                        type("obj", (object,), {
                            "error_type": err["error_type"],
                            "task_name": err["task_name"],
                            "message": err["message"],
                            "details": err["details"],
                        })()
                        for err in result["validation_errors"]["errors"]
                    ],
                    total_errors=result["validation_errors"]["total_errors"],
                    error_summary=result["validation_errors"]["error_summary"],
                )

                click.echo("\n✗ Validation errors detected:")
                click.echo(f"Total errors: {error_report.total_errors}")
                for error in error_report.errors:
                    click.echo(f"  - {error.message}")
                sys.exit(1)

        if output_json:
            import json

            # Use orchestrator's JSON formatter for consistent output
            orchestrator = coordinator.orchestrator
            if orchestrator:
                output = orchestrator.format_json_output(
                    task_names=result["execution_order"],
                    changed_files=result["changed_files"],
                    matched_tasks=result["matched_tasks"],
                    command=result["command"],
                    command_string=result["command_string"],
                )
            else:
                # Fallback to basic format
                output = {
                    "changed_files": result["changed_files"],
                    "matched_tasks": list(result["matched_tasks"]),
                    "execution_order": result["execution_order"],
                    "command": result["command"],
                    "command_string": result["command_string"],
                }
            click.echo(json.dumps(output, indent=2))
        else:
            # Human-readable output (suppressed if json_errors is enabled)
            if not json_errors:
                if result["changed_files"]:
                    click.echo("\nChanged Files:")
                    for file_path in result["changed_files"]:
                        click.echo(f"  - {file_path}")

                if result["matched_tasks"]:
                    click.echo(f"\nMatched Tasks ({len(result['matched_tasks'])}):")
                    for task_name in sorted(result["matched_tasks"]):
                        click.echo(f"  - {task_name}")

                if result["execution_order"]:
                    click.echo(f"\nExecution Order ({len(result['execution_order'])}):")
                    for i, task_name in enumerate(result["execution_order"], start=1):
                        click.echo(f"  {i}. {task_name}")

                    click.echo("\nGenerated Ansible Command:")
                    click.echo(f"  {result['command_string']}")
                else:
                    click.echo("\nNo tasks to execute.")

    except CoordinatorError as e:
        if json_errors or output_json:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="coordinator_error",
                        task_name="workflow",
                        message=str(e),
                        details={"error_class": type(e).__name__},
                    )
                ],
                total_errors=1,
                error_summary={"coordinator_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        if json_errors or output_json:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            import traceback
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="unexpected_error",
                        task_name="workflow",
                        message=str(e),
                        details={
                            "error_class": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                    )
                ],
                total_errors=1,
                error_summary={"unexpected_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--dependency-map",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Path to dependency_map.yml file. Auto-discovered if not specified.",
)
@click.option(
    "--from-commit",
    "-f",
    type=str,
    help="Starting commit SHA, branch, or tag. Uses last successful commit if not specified.",
)
@click.option(
    "--to-commit",
    "-t",
    type=str,
    default="HEAD",
    help="Ending commit SHA, branch, or tag. Defaults to HEAD.",
)
@click.option(
    "--repo-path",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    help="Path to git repository. Uses current directory if not specified.",
)
@click.option(
    "--playbook",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    default="playbook.yml",
    help="Path to Ansible playbook. Defaults to playbook.yml.",
)
@click.option(
    "--inventory",
    "-i",
    type=click.Path(exists=True, path_type=Path),
    help="Path to Ansible inventory file.",
)
@click.option(
    "--no-triggers",
    is_flag=True,
    help="Do not include triggered tasks (only dependencies).",
)
@click.option(
    "--no-validate",
    is_flag=True,
    help="Skip variable validation.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Generate command with --check flag (dry-run mode).",
)
@click.option(
    "--full-deploy",
    is_flag=True,
    help="Execute all tasks regardless of changes (full deployment).",
)
@click.option(
    "--environment",
    "-e",
    type=str,
    default="default",
    help="Environment name for state tracking. Defaults to 'default'.",
)
@click.option(
    "--no-state-update",
    is_flag=True,
    help="Do not update state store after successful execution.",
)
@click.option(
    "--json-errors",
    is_flag=True,
    help="Output validation errors in JSON format (only if validation fails).",
)
def execute(
    dependency_map: Optional[Path],
    from_commit: Optional[str],
    to_commit: str,
    repo_path: Optional[Path],
    playbook: Path,
    inventory: Optional[Path],
    no_triggers: bool,
    no_validate: bool,
    dry_run: bool,
    full_deploy: bool,
    environment: str,
    no_state_update: bool,
    json_errors: bool,
):
    """Execute Ansible tasks based on git changes.

    This command analyzes changes, resolves dependencies, and executes
    the generated Ansible command. After successful execution, updates the
    state store with the current commit.
    """
    # Validate that playbook is not a task file
    if _is_task_file(playbook):
        # Try to extract role name for better error message
        role_name = None
        playbook_path = Path(playbook).resolve()
        parts = playbook_path.parts
        if "roles" in parts:
            roles_idx = parts.index("roles")
            if roles_idx + 1 < len(parts):
                role_name = parts[roles_idx + 1]
        
        error_msg = (
            f"Error: '{playbook}' is a role task file, not a playbook.\n"
            "Task files cannot be executed directly with ansible-playbook.\n\n"
            "To analyze/execute tasks from this role:\n"
            "  1. Use a playbook that includes this role, e.g.:\n"
            f"     said execute -p playbook.yml" + (f" --inventory {inventory}" if inventory else "") + "\n"
            "  2. Ensure your playbook includes the role, e.g.:\n"
            f"     - hosts: all\n"
            f"       roles:\n"
            f"         - {role_name if role_name else 'your_role_name'}\n"
        )
        if json_errors:
            from said.error_collector import DependencyError, DependencyErrorReport
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="invalid_playbook",
                        task_name="execute",
                        message=error_msg,
                        details={
                            "file_path": str(playbook),
                            "role_name": role_name,
                            "suggestion": "Use a playbook file that includes this role instead of the task file directly.",
                        },
                    )
                ],
                total_errors=1,
                error_summary={"invalid_playbook": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(error_msg, err=True)
        sys.exit(1)
    
    try:
        coordinator = WorkflowCoordinator(
            repo_path=str(repo_path) if repo_path else None,
            dependency_map_path=str(dependency_map) if dependency_map else None,
            playbook_path=str(playbook),
            inventory=str(inventory) if inventory else None,
        )

        # Run workflow
        result = coordinator.run_full_workflow(
            from_commit=from_commit,
            to_commit=to_commit,
            include_triggers=not no_triggers,
            validate_vars=not no_validate,
            dry_run=dry_run,
            full_deploy=full_deploy,
            collect_all_errors=json_errors,
        )

        # Check for validation errors
        if "validation_errors" in result and result["validation_errors"]:
            if json_errors:
                import json

                error_output = {
                    "validation_errors": result["validation_errors"],
                    "workflow_result": {
                        "changed_files": result["changed_files"],
                        "matched_tasks": list(result["matched_tasks"]),
                        "execution_order": result["execution_order"],
                    },
                }
                click.echo(json.dumps(error_output, indent=2))
            else:
                from said.error_collector import DependencyErrorReport

                # Reconstruct error report for display
                error_report = DependencyErrorReport(
                    errors=[
                        type("obj", (object,), {
                            "error_type": err["error_type"],
                            "task_name": err["task_name"],
                            "message": err["message"],
                            "details": err["details"],
                        })()
                        for err in result["validation_errors"]["errors"]
                    ],
                    total_errors=result["validation_errors"]["total_errors"],
                    error_summary=result["validation_errors"]["error_summary"],
                )

                if not json_errors:
                    click.echo("\n✗ Validation errors detected:")
                    click.echo(f"Total errors: {error_report.total_errors}")
                    for error in error_report.errors:
                        click.echo(f"  - {error.message}")
            sys.exit(1)

        if not result["execution_order"]:
            if not json_errors:
                click.echo("No tasks to execute.")
            return

        # Display execution plan using orchestrator's formatter (suppressed if json_errors)
        if not json_errors:
            orchestrator = coordinator.orchestrator
            if orchestrator:
                plan = orchestrator.format_execution_plan(
                    task_names=result["execution_order"],
                    changed_files=result["changed_files"],
                    matched_tasks=result["matched_tasks"],
                    command_string=result["command_string"],
                )
                click.echo("\n" + plan)
            else:
                # Fallback to basic format
                click.echo("\n" + "=" * 60)
                click.echo("SAID Execution Plan")
                click.echo("=" * 60)

                if result["changed_files"]:
                    click.echo("\nChanged Files:")
                    for file_path in result["changed_files"]:
                        click.echo(f"  - {file_path}")

                click.echo(f"\nTasks to Execute ({len(result['execution_order'])}):")
                for i, task_name in enumerate(result["execution_order"], start=1):
                    click.echo(f"  {i}. {task_name}")

                click.echo("\nGenerated Ansible Command:")
                click.echo(f"  {result['command_string']}")

        if dry_run:
            if not json_errors:
                click.echo("\n[DRY RUN MODE - Command will not be executed]")
            return

        # Confirm execution (skip if json_errors - assume yes for automation)
        if not json_errors:
            if not click.confirm("\nExecute this command?"):
                click.echo("Execution cancelled.")
                return

        # Execute command
        import subprocess
        import os

        if not json_errors:
            click.echo("\nExecuting Ansible command...")
        
        # Find roles directory and set ANSIBLE_ROLES_PATH if found
        env = os.environ.copy()
        roles_dir = _find_roles_directory(playbook, inventory)
        if roles_dir:
            # ANSIBLE_ROLES_PATH can contain multiple paths separated by colon (Unix) or semicolon (Windows)
            separator = ":" if os.name != "nt" else ";"
            existing_paths = env.get("ANSIBLE_ROLES_PATH", "")
            if existing_paths:
                new_paths = f"{existing_paths}{separator}{roles_dir}"
            else:
                new_paths = str(roles_dir)
            env["ANSIBLE_ROLES_PATH"] = new_paths
            if not json_errors:
                click.echo(f"Using roles directory: {roles_dir}")
        
        try:
            exit_code = subprocess.run(
                result["command"],
                check=False,
                env=env,
            ).returncode

            if exit_code == 0:
                if not json_errors:
                    click.echo("\n✓ Execution successful!")

                # Update state store
                if not no_state_update:
                    current_commit = coordinator.git_detector.get_current_commit_sha()
                    coordinator.update_successful_commit(current_commit, environment)
                    if not json_errors:
                        click.echo(f"✓ State updated for environment '{environment}'")
            else:
                if not json_errors:
                    click.echo(f"\n✗ Execution failed with exit code {exit_code}", err=True)
                sys.exit(exit_code)

        except KeyboardInterrupt:
            if json_errors:
                import json
                from said.error_collector import DependencyError, DependencyErrorReport
                
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type="execution_interrupted",
                            task_name="ansible_execution",
                            message="Execution interrupted by user",
                            details={},
                        )
                    ],
                    total_errors=1,
                    error_summary={"execution_interrupted": 1},
                )
                click.echo(error_report.to_json())
            else:
                click.echo("\n\nExecution interrupted by user.", err=True)
            sys.exit(130)
        except Exception as e:
            if json_errors:
                import json
                from said.error_collector import DependencyError, DependencyErrorReport
                import traceback
                
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type="execution_error",
                            task_name="ansible_execution",
                            message=str(e),
                            details={
                                "error_class": type(e).__name__,
                                "traceback": traceback.format_exc(),
                            },
                        )
                    ],
                    total_errors=1,
                    error_summary={"execution_error": 1},
                )
                click.echo(error_report.to_json())
            else:
                click.echo(f"\n✗ Error executing command: {e}", err=True)
            sys.exit(1)

    except CoordinatorError as e:
        if json_errors:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="coordinator_error",
                        task_name="workflow",
                        message=str(e),
                        details={"error_class": type(e).__name__},
                    )
                ],
                total_errors=1,
                error_summary={"coordinator_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        if json_errors:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            import traceback
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="unexpected_error",
                        task_name="workflow",
                        message=str(e),
                        details={
                            "error_class": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                    )
                ],
                total_errors=1,
                error_summary={"unexpected_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--dependency-map",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Path to dependency_map.yml file. Auto-discovered if not specified.",
)
@click.option(
    "--inventory",
    "-i",
    type=click.Path(exists=True, path_type=Path),
    help="Path to Ansible inventory file to load variables from.",
)
@click.option(
    "--variables",
    "-v",
    type=str,
    help="Path to YAML file containing variables.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output errors in JSON format.",
)
def validate(
    dependency_map: Optional[Path],
    inventory: Optional[Path],
    variables: Optional[str],
    output_json: bool,
):
    """Validate dependency map and required variables.

    This command validates the dependency map structure and checks that
    all required variables are defined.
    """
    try:
        from said.parser import discover_dependency_map, parse_dependency_map
        from said.schema import validate_dependency_map
        from said.validator import VariableValidator
        import yaml

        # Load dependency map
        if dependency_map:
            dep_map = parse_dependency_map(str(dependency_map))
        else:
            dep_map = discover_dependency_map()
            if dep_map is None:
                if output_json:
                    import json
                    from said.error_collector import DependencyError, DependencyErrorReport
                    
                    error_report = DependencyErrorReport(
                        errors=[
                            DependencyError(
                                error_type="file_not_found",
                                task_name="validation",
                                message="Could not find dependency_map.yml",
                                details={},
                            )
                        ],
                        total_errors=1,
                        error_summary={"file_not_found": 1},
                    )
                    click.echo(error_report.to_json())
                else:
                    click.echo("Error: Could not find dependency_map.yml", err=True)
                sys.exit(1)

        if not output_json:
            click.echo("✓ Dependency map structure is valid")

        # Load variables
        vars_dict = {}
        if inventory:
            # Try to load from inventory (basic implementation)
            try:
                with open(inventory, "r", encoding="utf-8") as f:
                    inv_content = yaml.safe_load(f)
                    if isinstance(inv_content, dict) and "all" in inv_content:
                        vars_dict.update(inv_content["all"].get("vars", {}))
            except Exception as e:
                if not output_json:
                    click.echo(f"Warning: Could not load variables from inventory: {e}", err=True)

        if variables:
            try:
                with open(variables, "r", encoding="utf-8") as f:
                    vars_dict.update(yaml.safe_load(f) or {})
            except Exception as e:
                if output_json:
                    import json
                    from said.error_collector import DependencyError, DependencyErrorReport
                    
                    error_report = DependencyErrorReport(
                        errors=[
                            DependencyError(
                                error_type="file_error",
                                task_name="validation",
                                message=f"Error loading variables file: {e}",
                                details={"error_class": type(e).__name__},
                            )
                        ],
                        total_errors=1,
                        error_summary={"file_error": 1},
                    )
                    click.echo(error_report.to_json())
                else:
                    click.echo(f"Error loading variables file: {e}", err=True)
                sys.exit(1)

        # Comprehensive validation with error collection
        from said.error_collector import validate_dependency_map_comprehensive

        # Determine search base (use dependency map location or current directory)
        search_base = None
        if dependency_map:
            search_base = dependency_map.parent
        else:
            # Try to find dependency map location
            from said.parser import discover_dependency_map
            discovered_map = discover_dependency_map()
            if discovered_map:
                # Use current directory as search base
                search_base = Path.cwd()

        error_report = validate_dependency_map_comprehensive(
            dep_map,
            task_names=set(task.name for task in dep_map.tasks),
            variables=vars_dict if vars_dict else None,
            search_base=search_base,
            search_for_suggestions=True,
        )

        if error_report.has_errors():
            if output_json:
                click.echo(error_report.to_json())
                sys.exit(1)
            else:
                click.echo("\n✗ Dependency validation failed:")
                click.echo(f"Total errors: {error_report.total_errors}")
                click.echo(f"Error summary: {error_report.error_summary}\n")

                # Group errors by type
                errors_by_type = {}
                for error in error_report.errors:
                    if error.error_type not in errors_by_type:
                        errors_by_type[error.error_type] = []
                    errors_by_type[error.error_type].append(error)

                for error_type, type_errors in errors_by_type.items():
                    click.echo(f"\n{error_type.replace('_', ' ').title()} ({len(type_errors)}):")
                    for error in type_errors:
                        click.echo(f"  - {error.message}")
                        if error.details:
                            for key, value in error.details.items():
                                if key == "suggestions":
                                    # Format suggestions nicely
                                    click.echo(f"    Suggestions for missing variables:")
                                    for var_name, var_suggestions in value.items():
                                        click.echo(f"      {var_name}:")
                                        for category, files in var_suggestions.items():
                                            if files:
                                                click.echo(f"        {category}:")
                                                for file_info in files[:3]:  # Limit to 3 per category
                                                    file_path = file_info.get("file", "unknown")
                                                    if "line_number" in file_info:
                                                        click.echo(f"          - {file_path}:{file_info['line_number']}")
                                                    else:
                                                        click.echo(f"          - {file_path}")
                                                if len(files) > 3:
                                                    click.echo(f"          ... and {len(files) - 3} more")
                                elif key == "variable_producers":
                                    # Format variable producers (two-pass analysis results)
                                    click.echo(f"    Variable producers (tasks/files that could provide these variables):")
                                    for var_name, producers in value.items():
                                        click.echo(f"      {var_name}:")
                                        if producers:
                                            for producer in producers[:5]:  # Limit to 5 producers
                                                source_type = producer.get("source_type", "unknown")
                                                source_name = producer.get("source_name", "unknown")
                                                source_path = producer.get("source_path")
                                                if source_path:
                                                    click.echo(f"        - {source_type}: {source_path}")
                                                else:
                                                    click.echo(f"        - {source_type}: {source_name}")
                                            if len(producers) > 5:
                                                click.echo(f"        ... and {len(producers) - 5} more")
                                        else:
                                            click.echo(f"        (no producers found)")
                                elif key == "suggested_task_dependencies":
                                    # Show suggested task dependencies
                                    if value:
                                        click.echo(f"    Suggested task dependencies (based on variable producers):")
                                        for dep_task in value[:5]:  # Limit to 5
                                            click.echo(f"      - {dep_task}")
                                        if len(value) > 5:
                                            click.echo(f"      ... and {len(value) - 5} more")
                                elif isinstance(value, list) and len(value) > 5:
                                    click.echo(f"    {key}: {len(value)} items")
                                elif isinstance(value, dict):
                                    # For nested dicts, show a summary
                                    click.echo(f"    {key}: {len(value)} items")
                                else:
                                    click.echo(f"    {key}: {value}")

            sys.exit(1)
        else:
            if output_json:
                click.echo('{"total_errors": 0, "errors": []}')
            else:
                click.echo("✓ All dependencies are valid")
                click.echo("✓ All required variables are defined")

    except Exception as e:
        if output_json:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            import traceback
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="validation_error",
                        task_name="validation",
                        message=str(e),
                        details={
                            "error_class": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                    )
                ],
                total_errors=1,
                error_summary={"validation_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--playbook",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Path to Ansible playbook file(s). Can be specified multiple times.",
)
@click.option(
    "--directory",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Path to directory containing Ansible playbooks. Analyzes all .yml/.yaml files.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default="dependency_map.yml",
    help="Output path for generated dependency map. Defaults to dependency_map.yml.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing dependency_map.yml if it exists.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose output about discovered tasks.",
)
@click.option(
    "--inventory",
    "-i",
    type=click.Path(exists=True, path_type=Path),
    help="Path to Ansible inventory file (hosts.ini or hosts.yml).",
)
@click.option(
    "--groupvars",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Path to group_vars file or directory. Can be specified multiple times.",
)
@click.option(
    "--hostvars",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Path to host_vars file or directory. Can be specified multiple times.",
)
@click.option(
    "--no-auto-discover-vars",
    is_flag=True,
    help="Disable auto-discovery of group_vars and host_vars.",
)
@click.option(
    "--json-errors",
    is_flag=True,
    help="Output errors in JSON format (only if errors occur).",
)
def build(
    playbook: tuple,
    directory: Optional[Path],
    output: Path,
    overwrite: bool,
    verbose: bool,
    inventory: Optional[Path],
    groupvars: tuple,
    hostvars: tuple,
    no_auto_discover_vars: bool,
    json_errors: bool,
):
    """Automatically build dependency map from Ansible playbooks.

    This command analyzes Ansible playbooks and automatically generates a
    dependency_map.yml file by inferring:
    - Task names from playbook tasks
    - Watch files from template/copy/file tasks
    - Required variables from variable references
    - Dependencies from task relationships

    Variables from inventory, group_vars, and host_vars are used to filter
    out known variables from the required_vars list.

    Example:
        said build --directory ./playbooks --output dependency_map.yml
        said build --playbook site.yml --playbook roles/web/tasks/main.yml
        said build -p roles/consul_keepalived/tasks/main.yml --inventory inventories/dev/hosts.ini --groupvars inventories/dev/group_vars/dev2.yml
    """
    try:
        from said.builder import (
            BuilderError,
            build_dependency_map_from_directory,
            build_dependency_map_from_playbooks,
        )

        # Convert tuple to list (click's multiple=True returns a tuple)
        playbook_paths = list(playbook) if playbook and len(playbook) > 0 else []
        group_vars_paths = list(groupvars) if groupvars else []
        host_vars_paths = list(hostvars) if hostvars else []

        # Load variables from inventory, group_vars, and host_vars
        known_variables = {}
        if inventory or group_vars_paths or host_vars_paths or not no_auto_discover_vars:
            if verbose and not json_errors:
                click.echo("Loading variables from inventory and vars files...")
            
            # Determine inventory directory for auto-discovery
            inventory_dir = None
            if inventory:
                inventory_dir = Path(inventory).parent
                if verbose and not json_errors:
                    click.echo(f"  Inventory: {inventory}")

            # Load from explicit paths
            for gv_path in group_vars_paths:
                if verbose and not json_errors:
                    click.echo(f"  Group vars: {gv_path}")
            for hv_path in host_vars_paths:
                if verbose and not json_errors:
                    click.echo(f"  Host vars: {hv_path}")

            try:
                known_variables = load_all_variables(
                    inventory_path=inventory,
                    group_vars_path=group_vars_paths[0] if group_vars_paths else None,
                    host_vars_path=host_vars_paths[0] if host_vars_paths else None,
                    auto_discover=not no_auto_discover_vars,
                )
                # Merge multiple group_vars/host_vars if provided
                for gv_path in group_vars_paths[1:]:
                    try:
                        known_variables.update(load_group_vars(gv_path))
                    except Exception:
                        pass
                for hv_path in host_vars_paths[1:]:
                    try:
                        known_variables.update(load_host_vars(hv_path))
                    except Exception:
                        pass
                
                if verbose and not json_errors:
                    click.echo(f"  Loaded {len(known_variables)} known variables")
            except Exception as e:
                if verbose and not json_errors:
                    click.echo(f"  Warning: Could not load some variables: {e}", err=True)

        # Check if output file exists
        if output.exists() and not overwrite:
            if json_errors:
                # In JSON mode, don't prompt - just error
                import json
                from said.error_collector import DependencyError, DependencyErrorReport
                
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type="file_exists",
                            task_name="build",
                            message=f"File {output} already exists. Use --overwrite to overwrite.",
                            details={"file": str(output)},
                        )
                    ],
                    total_errors=1,
                    error_summary={"file_exists": 1},
                )
                click.echo(error_report.to_json())
                sys.exit(1)
            else:
                if not click.confirm(
                    f"File {output} already exists. Overwrite?",
                    default=False,
                ):
                    click.echo("Cancelled.")
                    return

        # Build from directory or playbooks
        if directory:
            if playbook_paths and not json_errors:
                click.echo(
                    "Warning: Both --directory and --playbook specified. Using directory.",
                    err=True,
                )
            if not json_errors:
                click.echo(f"Analyzing playbooks in {directory}...")
            dep_map = build_dependency_map_from_directory(
                directory, output, verbose=verbose and not json_errors, known_variables=known_variables
            )
        elif playbook_paths:
            if not json_errors:
                click.echo(f"Analyzing {len(playbook_paths)} playbook(s)...")
                for i, pb in enumerate(playbook_paths, 1):
                    click.echo(f"  {i}. {pb}")
            dep_map = build_dependency_map_from_playbooks(
                playbook_paths, output, verbose=verbose and not json_errors, known_variables=known_variables
            )
        else:
            if json_errors:
                import json
                from said.error_collector import DependencyError, DependencyErrorReport
                
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type="build_error",
                            task_name="build",
                            message="Must specify either --directory or --playbook",
                            details={},
                        )
                    ],
                    total_errors=1,
                    error_summary={"build_error": 1},
                )
                click.echo(error_report.to_json())
            else:
                click.echo(
                    "Error: Must specify either --directory or --playbook",
                    err=True,
                )
            sys.exit(1)

        if not json_errors:
            click.echo(f"\n✓ Generated dependency map with {len(dep_map.tasks)} tasks")
            click.echo(f"✓ Written to {output}")

            click.echo("\n📝 Next steps:")
            click.echo("  1. Review the generated dependency_map.yml")
            click.echo("  2. Add/edit watch_files, depends_on, triggers as needed")
            click.echo("  3. Verify required variables are correct")
            click.echo("  4. Run 'said validate' to check the dependency map")

    except BuilderError as e:
        if json_errors:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            from said.error_parser import structure_dependency_error
            
            # Get error context if available
            error_context = getattr(e, "error_context", {})
            dependency_map = error_context.get("temp_dependency_map")
            known_vars = error_context.get("known_variables")
            
            # Determine search base
            search_base = None
            if playbook_paths:
                search_base = Path(playbook_paths[0]).parent
            elif directory:
                search_base = Path(directory)
            
            # Try to parse and structure the error with variable analysis
            structured = structure_dependency_error(
                str(e),
                type(e).__name__,
                dependency_map=dependency_map,
                search_base=search_base,
                known_variables=known_vars,
            )
            
            # If it's a dependency error, use the structured format
            if structured["error_type"] == "invalid_dependency":
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type=structured["error_type"],
                            task_name=structured["task_name"],
                            message=structured["message"],
                            details=structured["details"],
                        )
                    ],
                    total_errors=1,
                    error_summary={"invalid_dependency": 1},
                )
            else:
                # Fallback to basic builder error
                error_report = DependencyErrorReport(
                    errors=[
                        DependencyError(
                            error_type="builder_error",
                            task_name="build",
                            message=str(e),
                            details={"error_class": type(e).__name__},
                        )
                    ],
                    total_errors=1,
                    error_summary={"builder_error": 1},
                )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        if json_errors:
            import json
            from said.error_collector import DependencyError, DependencyErrorReport
            import traceback
            
            error_report = DependencyErrorReport(
                errors=[
                    DependencyError(
                        error_type="unexpected_error",
                        task_name="build",
                        message=str(e),
                        details={
                            "error_class": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                    )
                ],
                total_errors=1,
                error_summary={"unexpected_error": 1},
            )
            click.echo(error_report.to_json())
        else:
            click.echo(f"Unexpected error: {e}", err=True)
            import traceback
            if verbose:
                click.echo(traceback.format_exc(), err=True)
        sys.exit(1)


def main():
    """Main entry point for SAID CLI."""
    cli()


if __name__ == "__main__":
    main()
