"""Ansible orchestrator for SAID.

This module provides functionality to generate Ansible commands with --tags
based on resolved task dependencies.
"""

import shlex
from typing import List, Optional


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
        self, task_names: List[str], changed_files: Optional[List[str]] = None
    ) -> str:
        """Format a human-readable execution plan.

        Args:
            task_names: List of task names in execution order.
            changed_files: Optional list of changed files that triggered these tasks.

        Returns:
            Formatted string describing the execution plan.
        """
        lines = []
        lines.append("=" * 60)
        lines.append("SAID Execution Plan")
        lines.append("=" * 60)

        if changed_files:
            lines.append("\nChanged Files:")
            for file_path in changed_files:
                lines.append(f"  - {file_path}")

        lines.append(f"\nTasks to Execute ({len(task_names)}):")
        for i, task_name in enumerate(task_names, start=1):
            lines.append(f"  {i}. {task_name}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
