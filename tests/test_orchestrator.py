"""Unit tests for orchestrator module."""

import pytest

from said.orchestrator import AnsibleOrchestrator, OrchestratorError


class TestAnsibleOrchestrator:
    """Test cases for AnsibleOrchestrator."""

    def test_init_default(self):
        """Test default initialization."""
        orchestrator = AnsibleOrchestrator()
        assert orchestrator.playbook_path == "playbook.yml"
        assert orchestrator.inventory is None
        assert orchestrator.extra_args == []

    def test_init_custom(self):
        """Test initialization with custom parameters."""
        orchestrator = AnsibleOrchestrator(
            playbook_path="custom.yml",
            inventory="inventory.ini",
            extra_args=["--extra-arg"],
        )
        assert orchestrator.playbook_path == "custom.yml"
        assert orchestrator.inventory == "inventory.ini"
        assert orchestrator.extra_args == ["--extra-arg"]

    def test_generate_command_basic(self):
        """Test basic command generation."""
        orchestrator = AnsibleOrchestrator()
        cmd = orchestrator.generate_command(["task1", "task2"])
        assert cmd[0] == "ansible-playbook"
        assert "playbook.yml" in cmd
        assert "--tags" in cmd
        assert "task1,task2" in cmd

    def test_generate_command_with_inventory(self):
        """Test command generation with inventory."""
        orchestrator = AnsibleOrchestrator(inventory="inventory.ini")
        cmd = orchestrator.generate_command(["task1"])
        assert "-i" in cmd
        assert "inventory.ini" in cmd

    def test_generate_command_dry_run(self):
        """Test command generation with dry-run flag."""
        orchestrator = AnsibleOrchestrator()
        cmd = orchestrator.generate_command(["task1"], dry_run=True)
        assert "--check" in cmd

    def test_generate_command_extra_args(self):
        """Test command generation with extra arguments."""
        orchestrator = AnsibleOrchestrator(extra_args=["--verbose", "--limit", "host1"])
        cmd = orchestrator.generate_command(["task1"])
        assert "--verbose" in cmd
        assert "--limit" in cmd
        assert "host1" in cmd

    def test_generate_command_empty_tasks(self):
        """Test that empty task list raises error."""
        orchestrator = AnsibleOrchestrator()
        with pytest.raises(OrchestratorError, match="no tasks specified"):
            orchestrator.generate_command([])

    def test_generate_command_string(self):
        """Test command string generation."""
        orchestrator = AnsibleOrchestrator()
        cmd_str = orchestrator.generate_command_string(["task1", "task2"])
        assert "ansible-playbook" in cmd_str
        assert "playbook.yml" in cmd_str
        assert "--tags" in cmd_str
        assert "task1,task2" in cmd_str

    def test_format_execution_plan(self):
        """Test execution plan formatting."""
        orchestrator = AnsibleOrchestrator()
        plan = orchestrator.format_execution_plan(
            ["task1", "task2"], changed_files=["file1.yml", "file2.yml"]
        )
        assert "SAID Execution Plan" in plan
        assert "task1" in plan
        assert "task2" in plan
        assert "file1.yml" in plan
        assert "file2.yml" in plan

    def test_format_execution_plan_no_files(self):
        """Test execution plan formatting without changed files."""
        orchestrator = AnsibleOrchestrator()
        plan = orchestrator.format_execution_plan(["task1"])
        assert "SAID Execution Plan" in plan
        assert "task1" in plan
        assert "Changed Files" not in plan or "Changed Files:" in plan

    def test_format_execution_plan_with_matched_tasks(self):
        """Test execution plan formatting with matched tasks."""
        orchestrator = AnsibleOrchestrator()
        plan = orchestrator.format_execution_plan(
            ["task1", "task2"],
            changed_files=["file1.yml"],
            matched_tasks={"task1"},
            command_string="ansible-playbook playbook.yml --tags task1,task2",
        )
        assert "SAID Execution Plan" in plan
        assert "task1" in plan
        assert "task2" in plan
        assert "file1.yml" in plan
        assert "ansible-playbook" in plan

    def test_format_json_output(self):
        """Test JSON output formatting."""
        orchestrator = AnsibleOrchestrator()
        output = orchestrator.format_json_output(
            task_names=["task1", "task2"],
            changed_files=["file1.yml"],
            matched_tasks={"task1"},
            command=["ansible-playbook", "playbook.yml", "--tags", "task1,task2"],
            command_string="ansible-playbook playbook.yml --tags task1,task2",
        )
        assert "execution_plan" in output
        assert output["execution_plan"]["total_tasks"] == 2
        assert output["execution_plan"]["tasks"] == ["task1", "task2"]
        assert output["changed_files"] == ["file1.yml"]
        assert output["matched_tasks"] == ["task1"]
        assert "command" in output
        assert output["command"]["string"] == "ansible-playbook playbook.yml --tags task1,task2"

    def test_format_json_output_minimal(self):
        """Test JSON output formatting with minimal data."""
        orchestrator = AnsibleOrchestrator()
        output = orchestrator.format_json_output(task_names=["task1"])
        assert "execution_plan" in output
        assert output["execution_plan"]["total_tasks"] == 1
        assert output["execution_plan"]["tasks"] == ["task1"]
