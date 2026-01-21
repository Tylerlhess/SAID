"""Ansible orchestrator for SAID.

This module provides functionality to generate Ansible commands with --tags
based on resolved task dependencies.
"""

import shlex
from typing import Dict, List, Optional, Set


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""

    pass


class AnsibleOrchestrator:
    """Generates Ansible commands with appropriate tags."""

    def __init__(
        self,
        playbook_path: str = "playbook.yml",
        inventory: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ):
        """Initialize the Ansible orchestrator.

        Args:
            playbook_path: Path to the Ansible playbook file. Defaults to "playbook.yml".
            inventory: Path to the Ansible inventory file. Optional.
            extra_args: Additional arguments to pass to ansible-playbook. Optional.
        """
        self.playbook_path = playbook_path
        self.inventory = inventory
        self.extra_args = extra_args or []

    def generate_command(
        self, task_names: List[str], dry_run: bool = False
    ) -> List[str]:
        """Generate Ansible command with --tags for the specified tasks.

        Args:
            task_names: List of task names to execute (in execution order).
            dry_run: If True, add --check flag for dry-run mode.

        Returns:
            List of command arguments (suitable for subprocess.run or similar).

        Raises:
            OrchestratorError: If task_names is empty or invalid.
        """
        if not task_names:
            raise OrchestratorError("Cannot generate command: no tasks specified")

        # Start with ansible-playbook command
        cmd = ["ansible-playbook"]

        # Add inventory if specified
        if self.inventory:
            cmd.extend(["-i", self.inventory])

        # Add playbook path
        cmd.append(self.playbook_path)

        # Add tags
        # In Ansible, tags are specified as --tags "tag1,tag2,tag3"
        # We'll use the task names as tags
        tags_str = ",".join(task_names)
        cmd.extend(["--tags", tags_str])

        # Add dry-run flag if requested
        if dry_run:
            cmd.append("--check")

        # Add any extra arguments
        cmd.extend(self.extra_args)

        return cmd

    def generate_command_string(
        self, task_names: List[str], dry_run: bool = False
    ) -> str:
        """Generate Ansible command as a shell-escaped string.

        Args:
            task_names: List of task names to execute (in execution order).
            dry_run: If True, add --check flag for dry-run mode.

        Returns:
            Shell-escaped command string.

        Raises:
            OrchestratorError: If task_names is empty or invalid.
        """
        cmd = self.generate_command(task_names, dry_run=dry_run)
        return " ".join(shlex.quote(arg) for arg in cmd)

    def format_execution_plan(
        self,
        task_names: List[str],
        changed_files: Optional[List[str]] = None,
        matched_tasks: Optional[Set[str]] = None,
        command_string: Optional[str] = None,
    ) -> str:
        """Format a human-readable execution plan.

        Args:
            task_names: List of task names in execution order.
            changed_files: Optional list of changed files that triggered these tasks.
            matched_tasks: Optional set of initially matched task names.
            command_string: Optional Ansible command string to display.

        Returns:
            Formatted string describing the execution plan.
        """
        lines = []
        lines.append("=" * 70)
        lines.append("SAID Execution Plan")
        lines.append("=" * 70)

        if changed_files:
            lines.append("\n📝 Changed Files:")
            for file_path in sorted(changed_files):
                lines.append(f"   • {file_path}")

        if matched_tasks and matched_tasks != set(task_names):
            lines.append(f"\n🎯 Initially Matched Tasks ({len(matched_tasks)}):")
            for task_name in sorted(matched_tasks):
                lines.append(f"   • {task_name}")

        if task_names:
            lines.append(f"\n⚙️  Tasks to Execute ({len(task_names)}):")
            for i, task_name in enumerate(task_names, start=1):
                marker = "→" if task_name in (matched_tasks or set()) else " "
                lines.append(f"   {i:2d}. {marker} {task_name}")

        if command_string:
            lines.append("\n📋 Generated Ansible Command:")
            lines.append(f"   {command_string}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def format_json_output(
        self,
        task_names: List[str],
        changed_files: Optional[List[str]] = None,
        matched_tasks: Optional[Set[str]] = None,
        command: Optional[List[str]] = None,
        command_string: Optional[str] = None,
    ) -> Dict:
        """Format execution plan as a JSON-serializable dictionary.

        Args:
            task_names: List of task names in execution order.
            changed_files: Optional list of changed files.
            matched_tasks: Optional set of initially matched task names.
            command: Optional command as list of arguments.
            command_string: Optional command as shell string.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        output = {
            "execution_plan": {
                "total_tasks": len(task_names),
                "tasks": task_names,
            }
        }

        if changed_files:
            output["changed_files"] = sorted(changed_files)

        if matched_tasks:
            output["matched_tasks"] = sorted(matched_tasks)
            output["execution_plan"]["initially_matched"] = len(matched_tasks)

        if command:
            output["command"] = {
                "args": command,
                "string": command_string or " ".join(command),
            }

        return output
