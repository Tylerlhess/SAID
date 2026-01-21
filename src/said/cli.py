"""Command-line interface for SAID."""

import sys
from pathlib import Path
from typing import Optional

import click

from said.coordinator import CoordinatorError, WorkflowCoordinator


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


def main():
    """Main entry point for SAID CLI."""
    cli()


if __name__ == "__main__":
    main()
