"""Unit tests for coordinator module."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from said.coordinator import CoordinatorError, WorkflowCoordinator
from said.git_detector import GitDetectorError
from said.parser import ParserError
from said.resolver import ResolverError
from said.schema import DependencyMap, TaskMetadata
from said.state_store import StateStoreError
from said.validator import MissingVariableError


class TestWorkflowCoordinator:
    """Test cases for WorkflowCoordinator."""

    @pytest.fixture
    def sample_dependency_map(self):
        """Create a sample dependency map for testing."""
        return DependencyMap(
            tasks=[
                TaskMetadata(
                    name="task1",
                    provides=["resource1"],
                    requires_vars=[],
                    triggers=[],
                    watch_files=["file1.yml"],
                    depends_on=[],
                ),
                TaskMetadata(
                    name="task2",
                    provides=["resource2"],
                    requires_vars=["var1"],
                    triggers=[],
                    watch_files=["file2.yml"],
                    depends_on=["resource1"],
                ),
            ]
        )

    @pytest.fixture
    def mock_git_detector(self):
        """Create a mock git detector."""
        detector = MagicMock()
        detector.get_changed_files.return_value = ["file1.yml"]
        detector.get_current_commit_sha.return_value = "abc123"
        detector.is_dirty.return_value = False
        return detector

    @pytest.fixture
    def mock_state_store(self):
        """Create a mock state store."""
        store = MagicMock()
        store.get_last_successful_commit.return_value = "prev123"
        return store

    def test_init_default(self):
        """Test default initialization."""
        with patch("said.coordinator.GitDetector") as mock_git:
            mock_git.return_value = MagicMock()
            coordinator = WorkflowCoordinator()
            assert coordinator.repo_path is None
            assert coordinator.dependency_map_path is None
            assert coordinator.playbook_path == "playbook.yml"

    def test_init_custom(self):
        """Test initialization with custom parameters."""
        with patch("said.coordinator.GitDetector") as mock_git:
            mock_git.return_value = MagicMock()
            coordinator = WorkflowCoordinator(
                repo_path="/path/to/repo",
                dependency_map_path="/path/to/map.yml",
                playbook_path="custom.yml",
                inventory="inventory.ini",
                variables={"var1": "value1"},
            )
            assert coordinator.repo_path == "/path/to/repo"
            assert coordinator.dependency_map_path == "/path/to/map.yml"
            assert coordinator.playbook_path == "custom.yml"
            assert coordinator.inventory == "inventory.ini"
            assert coordinator.variables == {"var1": "value1"}

    def test_init_git_error(self):
        """Test initialization with git error."""
        with patch("said.coordinator.GitDetector") as mock_git:
            mock_git.side_effect = GitDetectorError("Not a git repo")
            with pytest.raises(CoordinatorError, match="Failed to initialize git detector"):
                WorkflowCoordinator()

    def test_load_dependency_map_from_path(self, mock_git_detector, sample_dependency_map):
        """Test loading dependency map from specified path."""
        with patch("said.coordinator.parse_dependency_map") as mock_parse:
            mock_parse.return_value = sample_dependency_map
            coordinator = WorkflowCoordinator(
                dependency_map_path="/path/to/map.yml",
                logger=logging.getLogger("test"),
            )
            coordinator.git_detector = mock_git_detector

            result = coordinator.load_dependency_map()
            assert result == sample_dependency_map
            assert coordinator.dependency_map == sample_dependency_map
            assert coordinator.resolver is not None
            assert coordinator.orchestrator is not None

    def test_load_dependency_map_auto_discover(self, mock_git_detector, sample_dependency_map):
        """Test auto-discovering dependency map."""
        with patch("said.coordinator.discover_dependency_map") as mock_discover:
            mock_discover.return_value = sample_dependency_map
            coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
            coordinator.git_detector = mock_git_detector

            result = coordinator.load_dependency_map()
            assert result == sample_dependency_map

    def test_load_dependency_map_not_found(self, mock_git_detector):
        """Test loading dependency map when not found."""
        with patch("said.coordinator.discover_dependency_map") as mock_discover:
            mock_discover.return_value = None
            coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
            coordinator.git_detector = mock_git_detector

            with pytest.raises(CoordinatorError, match="Could not find dependency_map.yml"):
                coordinator.load_dependency_map()

    def test_get_changed_files_with_state_store(
        self, mock_git_detector, mock_state_store
    ):
        """Test getting changed files using state store."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector
        coordinator.state_store = mock_state_store

        files = coordinator.get_changed_files(use_state_store=True)
        assert files == ["file1.yml"]
        mock_state_store.get_last_successful_commit.assert_called_once()

    def test_get_changed_files_with_commit(self, mock_git_detector):
        """Test getting changed files with explicit commit."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        files = coordinator.get_changed_files(from_commit="abc123", to_commit="def456")
        assert files == ["file1.yml"]
        mock_git_detector.get_changed_files.assert_called_with("abc123", "def456")

    def test_get_changed_files_git_error(self, mock_git_detector):
        """Test getting changed files with git error."""
        mock_git_detector.get_changed_files.side_effect = GitDetectorError("Git error")
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        with pytest.raises(CoordinatorError, match="Failed to get changed files"):
            coordinator.get_changed_files(from_commit="abc123")

    def test_match_files_to_tasks(self, mock_git_detector, sample_dependency_map):
        """Test matching files to tasks."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector
        coordinator.dependency_map = sample_dependency_map

        matched = coordinator.match_files_to_tasks(["file1.yml"])
        assert "task1" in matched

    def test_match_files_to_tasks_no_map(self, mock_git_detector):
        """Test matching files when dependency map not loaded."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        with pytest.raises(CoordinatorError, match="Dependency map not loaded"):
            coordinator.match_files_to_tasks(["file1.yml"])

    def test_resolve_dependencies(self, mock_git_detector, sample_dependency_map):
        """Test resolving dependencies."""
        from said.resolver import DependencyResolver

        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector
        coordinator.dependency_map = sample_dependency_map
        coordinator.resolver = DependencyResolver(sample_dependency_map)

        order = coordinator.resolve_dependencies({"task2"})
        assert "task1" in order  # Dependency
        assert "task2" in order

    def test_resolve_dependencies_no_resolver(self, mock_git_detector):
        """Test resolving dependencies when resolver not initialized."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        with pytest.raises(CoordinatorError, match="Resolver not initialized"):
            coordinator.resolve_dependencies({"task1"})

    def test_validate_variables(self, mock_git_detector, sample_dependency_map):
        """Test variable validation."""
        coordinator = WorkflowCoordinator(
            variables={"var1": "value1"}, logger=logging.getLogger("test")
        )
        coordinator.git_detector = mock_git_detector
        coordinator.dependency_map = sample_dependency_map

        # Should not raise
        coordinator.validate_variables({"task2"})

    def test_validate_variables_missing(self, mock_git_detector, sample_dependency_map):
        """Test variable validation with missing variables."""
        coordinator = WorkflowCoordinator(
            variables={}, logger=logging.getLogger("test")
        )
        coordinator.git_detector = mock_git_detector
        coordinator.dependency_map = sample_dependency_map

        with pytest.raises(CoordinatorError, match="Variable validation failed"):
            coordinator.validate_variables({"task2"})

    def test_check_safety_conditions_said_code(self, mock_git_detector):
        """Test safety check for SAID code changes."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        result = coordinator.check_safety_conditions(["src/said/orchestrator.py"])
        assert result is True

    def test_check_safety_conditions_dependency_map(self, mock_git_detector):
        """Test safety check for dependency map changes."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        result = coordinator.check_safety_conditions(["dependency_map.yml"])
        assert result is True

    def test_check_safety_conditions_normal(self, mock_git_detector):
        """Test safety check for normal changes."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector

        result = coordinator.check_safety_conditions(["normal_file.yml"])
        assert result is False

    def test_update_successful_commit(self, mock_git_detector, mock_state_store):
        """Test updating successful commit."""
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector
        coordinator.state_store = mock_state_store

        coordinator.update_successful_commit("abc123", "production")
        mock_state_store.set_last_successful_commit.assert_called_with(
            "abc123", "production"
        )

    def test_update_successful_commit_error(self, mock_git_detector, mock_state_store):
        """Test updating successful commit with error."""
        mock_state_store.set_last_successful_commit.side_effect = StateStoreError(
            "Store error"
        )
        coordinator = WorkflowCoordinator(logger=logging.getLogger("test"))
        coordinator.git_detector = mock_git_detector
        coordinator.state_store = mock_state_store

        with pytest.raises(CoordinatorError, match="Failed to update successful commit"):
            coordinator.update_successful_commit("abc123")

    def test_run_full_workflow_no_changes(
        self, mock_git_detector, mock_state_store, sample_dependency_map
    ):
        """Test running workflow with no changes."""
        mock_git_detector.get_changed_files.return_value = []
        with patch("said.coordinator.parse_dependency_map") as mock_parse:
            mock_parse.return_value = sample_dependency_map
            coordinator = WorkflowCoordinator(
                dependency_map_path="/path/to/map.yml",
                logger=logging.getLogger("test"),
            )
            coordinator.git_detector = mock_git_detector
            coordinator.state_store = mock_state_store

            result = coordinator.run_full_workflow()
            assert result["execution_order"] == []
            assert result["changed_files"] == []

    def test_run_full_workflow_full_deploy(
        self, mock_git_detector, mock_state_store, sample_dependency_map
    ):
        """Test running workflow with full deploy."""
        with patch("said.coordinator.parse_dependency_map") as mock_parse:
            mock_parse.return_value = sample_dependency_map
            coordinator = WorkflowCoordinator(
                dependency_map_path="/path/to/map.yml",
                variables={"var1": "value1"},  # Provide required variable
                logger=logging.getLogger("test"),
            )
            coordinator.git_detector = mock_git_detector
            coordinator.state_store = mock_state_store

            result = coordinator.run_full_workflow(full_deploy=True)
            assert len(result["execution_order"]) > 0
            assert "task1" in result["execution_order"]
            assert "task2" in result["execution_order"]
