"""Command-line interface for SAID."""

import sys
from pathlib import Path
from typing import Optional

import click

from said.coordinator import CoordinatorError, WorkflowCoordinator
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
):
    """Analyze changes and generate execution plan without executing.

    This command shows what would be executed based on the current git state
    and dependency map, but does not run Ansible.
    """
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
        )

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
            # Human-readable output
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
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
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
):
    """Execute Ansible tasks based on git changes.

    This command analyzes changes, resolves dependencies, and executes
    the generated Ansible command. After successful execution, updates the
    state store with the current commit.
    """
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
        )

        if not result["execution_order"]:
            click.echo("No tasks to execute.")
            return

        # Display execution plan using orchestrator's formatter
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
            click.echo("\n[DRY RUN MODE - Command will not be executed]")
            return

        # Confirm execution
        if not click.confirm("\nExecute this command?"):
            click.echo("Execution cancelled.")
            return

        # Execute command
        import subprocess

        click.echo("\nExecuting Ansible command...")
        try:
            exit_code = subprocess.run(
                result["command"],
                check=False,
            ).returncode

            if exit_code == 0:
                click.echo("\n✓ Execution successful!")

                # Update state store
                if not no_state_update:
                    current_commit = coordinator.git_detector.get_current_commit_sha()
                    coordinator.update_successful_commit(current_commit, environment)
                    click.echo(f"✓ State updated for environment '{environment}'")
            else:
                click.echo(f"\n✗ Execution failed with exit code {exit_code}", err=True)
                sys.exit(exit_code)

        except KeyboardInterrupt:
            click.echo("\n\nExecution interrupted by user.", err=True)
            sys.exit(130)
        except Exception as e:
            click.echo(f"\n✗ Error executing command: {e}", err=True)
            sys.exit(1)

    except CoordinatorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
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
def validate(
    dependency_map: Optional[Path],
    inventory: Optional[Path],
    variables: Optional[str],
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
                click.echo("Error: Could not find dependency_map.yml", err=True)
                sys.exit(1)

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
                click.echo(f"Warning: Could not load variables from inventory: {e}", err=True)

        if variables:
            try:
                with open(variables, "r", encoding="utf-8") as f:
                    vars_dict.update(yaml.safe_load(f) or {})
            except Exception as e:
                click.echo(f"Error loading variables file: {e}", err=True)
                sys.exit(1)

        # Validate variables for all tasks
        validator = VariableValidator(vars_dict)
        validation_results = validator.validate_dependency_map(
            dep_map, set(task.name for task in dep_map.tasks)
        )

        # Report results
        errors = []
        for task_name, missing_vars in validation_results.items():
            if missing_vars:
                errors.append((task_name, missing_vars))

        if errors:
            click.echo("\n✗ Variable validation failed:")
            for task_name, missing_vars in errors:
                click.echo(
                    f"  Task '{task_name}' missing variables: {', '.join(sorted(missing_vars))}"
                )
            sys.exit(1)
        else:
            click.echo("✓ All required variables are defined")

    except Exception as e:
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
    "--hosts",
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
def build(
    playbook: tuple,
    directory: Optional[Path],
    output: Path,
    overwrite: bool,
    verbose: bool,
    hosts: Optional[Path],
    groupvars: tuple,
    hostvars: tuple,
    no_auto_discover_vars: bool,
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
        said build -p roles/consul_keepalived/tasks/main.yml --hosts inventories/dev/hosts.ini --groupvars inventories/dev/group_vars/dev2.yml
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
        if hosts or group_vars_paths or host_vars_paths or not no_auto_discover_vars:
            if verbose:
                click.echo("Loading variables from inventory and vars files...")
            
            # Determine inventory directory for auto-discovery
            inventory_dir = None
            if hosts:
                inventory_dir = Path(hosts).parent
                if verbose:
                    click.echo(f"  Inventory: {hosts}")

            # Load from explicit paths
            for gv_path in group_vars_paths:
                if verbose:
                    click.echo(f"  Group vars: {gv_path}")
            for hv_path in host_vars_paths:
                if verbose:
                    click.echo(f"  Host vars: {hv_path}")

            try:
                known_variables = load_all_variables(
                    inventory_path=hosts,
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
                
                if verbose:
                    click.echo(f"  Loaded {len(known_variables)} known variables")
            except Exception as e:
                if verbose:
                    click.echo(f"  Warning: Could not load some variables: {e}", err=True)

        # Check if output file exists
        if output.exists() and not overwrite:
            if not click.confirm(
                f"File {output} already exists. Overwrite?",
                default=False,
            ):
                click.echo("Cancelled.")
                return

        # Build from directory or playbooks
        if directory:
            if playbook_paths:
                click.echo(
                    "Warning: Both --directory and --playbook specified. Using directory.",
                    err=True,
                )
            click.echo(f"Analyzing playbooks in {directory}...")
            dep_map = build_dependency_map_from_directory(
                directory, output, verbose=verbose, known_variables=known_variables
            )
        elif playbook_paths:
            click.echo(f"Analyzing {len(playbook_paths)} playbook(s)...")
            for i, pb in enumerate(playbook_paths, 1):
                click.echo(f"  {i}. {pb}")
            dep_map = build_dependency_map_from_playbooks(
                playbook_paths, output, verbose=verbose, known_variables=known_variables
            )
        else:
            click.echo(
                "Error: Must specify either --directory or --playbook",
                err=True,
            )
            sys.exit(1)

        click.echo(f"\n✓ Generated dependency map with {len(dep_map.tasks)} tasks")
        click.echo(f"✓ Written to {output}")

        click.echo("\n📝 Next steps:")
        click.echo("  1. Review the generated dependency_map.yml")
        click.echo("  2. Add/edit watch_files, depends_on, triggers as needed")
        click.echo("  3. Verify required variables are correct")
        click.echo("  4. Run 'said validate' to check the dependency map")

    except BuilderError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point for SAID CLI."""
    cli()


if __name__ == "__main__":
    main()
