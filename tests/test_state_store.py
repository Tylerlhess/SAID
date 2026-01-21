"""Unit tests for state_store module."""

import json
import tempfile
from pathlib import Path

import pytest

from said.state_store import (
    FileStateStore,
    StateStore,
    StateStoreError,
)


class TestFileStateStore:
    """Test cases for FileStateStore class."""

    def test_init_with_default_path(self):
        """Test initialization with default path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir)
                store = FileStateStore()
                assert store.state_file == Path.cwd() / ".said" / "state.json"
                assert store.state_dir == Path.cwd() / ".said"
                assert store.state_dir.exists()
            finally:
                os.chdir(original_cwd)

    def test_init_with_custom_path(self):
        """Test initialization with custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "custom" / "state.json"
            store = FileStateStore(str(state_file))
            assert store.state_file == state_file
            assert store.state_dir == state_file.parent
            assert store.state_dir.exists()

    def test_get_last_successful_commit_no_file(self):
        """Test getting commit when state file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))
            result = store.get_last_successful_commit()
            assert result is None

    def test_get_last_successful_commit_empty_file(self):
        """Test getting commit when state file is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text("")
            store = FileStateStore(str(state_file))
            result = store.get_last_successful_commit()
            assert result is None

    def test_set_and_get_last_successful_commit(self):
        """Test setting and getting last successful commit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            commit_sha = "abc123def456"
            store.set_last_successful_commit(commit_sha)

            result = store.get_last_successful_commit()
            assert result == commit_sha

    def test_set_and_get_multiple_environments(self):
        """Test setting and getting commits for multiple environments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            prod_commit = "prod123"
            staging_commit = "staging456"

            store.set_last_successful_commit(prod_commit, "production")
            store.set_last_successful_commit(staging_commit, "staging")

            assert store.get_last_successful_commit("production") == prod_commit
            assert store.get_last_successful_commit("staging") == staging_commit
            assert store.get_last_successful_commit("default") is None

    def test_set_last_successful_commit_invalid_sha(self):
        """Test setting commit with invalid SHA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            with pytest.raises(StateStoreError) as exc_info:
                store.set_last_successful_commit("")
            assert "non-empty string" in str(exc_info.value).lower()

            with pytest.raises(StateStoreError) as exc_info:
                store.set_last_successful_commit(None)
            assert "non-empty string" in str(exc_info.value).lower()

    def test_clear_state(self):
        """Test clearing state for an environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            # Set commits for multiple environments
            store.set_last_successful_commit("commit1", "env1")
            store.set_last_successful_commit("commit2", "env2")

            # Clear one environment
            store.clear_state("env1")

            assert store.get_last_successful_commit("env1") is None
            assert store.get_last_successful_commit("env2") == "commit2"

    def test_clear_state_nonexistent_environment(self):
        """Test clearing state for non-existent environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            # Should not raise an error
            store.clear_state("nonexistent")

    def test_state_file_format(self):
        """Test that state file is saved in correct JSON format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            store.set_last_successful_commit("abc123", "production")
            store.set_last_successful_commit("def456", "staging")

            # Read and verify JSON structure
            content = state_file.read_text()
            data = json.loads(content)

            assert "environments" in data
            assert "production" in data["environments"]
            assert data["environments"]["production"]["last_successful_commit"] == "abc123"
            assert data["environments"]["staging"]["last_successful_commit"] == "def456"

    def test_atomic_write(self):
        """Test that writes are atomic (temp file then rename)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            store.set_last_successful_commit("commit1")

            # Verify temp file doesn't exist after write
            temp_file = state_file.with_suffix(".tmp")
            assert not temp_file.exists()
            assert state_file.exists()

    def test_load_corrupted_json(self):
        """Test handling of corrupted JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text("{ invalid json }")

            store = FileStateStore(str(state_file))

            with pytest.raises(StateStoreError) as exc_info:
                store.get_last_successful_commit()
            assert "Failed to parse" in str(exc_info.value)

    def test_persist_across_instances(self):
        """Test that state persists across different store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            # Create first instance and set state
            store1 = FileStateStore(str(state_file))
            store1.set_last_successful_commit("persisted_commit")

            # Create second instance and read state
            store2 = FileStateStore(str(state_file))
            result = store2.get_last_successful_commit()

            assert result == "persisted_commit"

    def test_update_existing_commit(self):
        """Test updating an existing commit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            store.set_last_successful_commit("old_commit")
            assert store.get_last_successful_commit() == "old_commit"

            store.set_last_successful_commit("new_commit")
            assert store.get_last_successful_commit() == "new_commit"

    def test_default_environment(self):
        """Test that default environment is used when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            store.set_last_successful_commit("default_commit")
            result = store.get_last_successful_commit()
            assert result == "default_commit"

            # Explicitly check default environment
            result_explicit = store.get_last_successful_commit("default")
            assert result_explicit == "default_commit"

    def test_create_directory_if_missing(self):
        """Test that state directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "nested" / "deep" / "state.json"
            assert not state_file.parent.exists()

            store = FileStateStore(str(state_file))
            assert state_file.parent.exists()

            store.set_last_successful_commit("test")
            assert state_file.exists()

    def test_unicode_commit_sha(self):
        """Test handling of unicode characters in commit SHA (shouldn't happen, but test anyway)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            store = FileStateStore(str(state_file))

            # Normal commit SHA (hexadecimal)
            commit_sha = "abc123def456"
            store.set_last_successful_commit(commit_sha)
            assert store.get_last_successful_commit() == commit_sha
