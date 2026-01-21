"""State storage module for SAID.

This module provides an abstraction for storing deployment state, including
the last successful commit SHA. Supports file-based storage with extensibility
for other backends (e.g., Redis).
"""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class StateStoreError(Exception):
    """Base exception for state store errors."""

    pass


class StateStore(ABC):
    """Abstract base class for state storage backends."""

    @abstractmethod
    def get_last_successful_commit(self, environment: str = "default") -> Optional[str]:
        """Get the last successful commit SHA for an environment.

        Args:
            environment: Environment name (e.g., 'production', 'staging').
                        Defaults to 'default'.

        Returns:
            Commit SHA as a string, or None if no successful commit exists.

        Raises:
            StateStoreError: If the operation fails.
        """
        pass

    @abstractmethod
    def set_last_successful_commit(
        self, commit_sha: str, environment: str = "default"
    ) -> None:
        """Set the last successful commit SHA for an environment.

        Args:
            commit_sha: The commit SHA to store.
            environment: Environment name (e.g., 'production', 'staging').
                        Defaults to 'default'.

        Raises:
            StateStoreError: If the operation fails.
        """
        pass

    @abstractmethod
    def clear_state(self, environment: str = "default") -> None:
        """Clear state for an environment.

        Args:
            environment: Environment name. Defaults to 'default'.

        Raises:
            StateStoreError: If the operation fails.
        """
        pass


class FileStateStore(StateStore):
    """File-based state store using JSON.

    Stores state in a JSON file, with support for multiple environments.
    """

    def __init__(self, state_file: Optional[str] = None):
        """Initialize the file-based state store.

        Args:
            state_file: Path to the state file. If None, uses `.said/state.json`
                       in the current working directory.

        Raises:
            StateStoreError: If the state file directory cannot be created.
        """
        if state_file is None:
            # Default to .said/state.json in current working directory
            state_dir = Path.cwd() / ".said"
            state_file = str(state_dir / "state.json")
        else:
            state_file = os.path.abspath(state_file)

        self.state_file = Path(state_file)
        self.state_dir = self.state_file.parent

        # Ensure the directory exists
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StateStoreError(
                f"Failed to create state directory '{self.state_dir}': {e}"
            )

    def _load_state(self) -> dict:
        """Load state from the JSON file.

        Returns:
            Dictionary containing state data.

        Raises:
            StateStoreError: If the file cannot be read or parsed.
        """
        if not self.state_file.exists():
            return {}

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError as e:
            raise StateStoreError(
                f"Failed to parse state file '{self.state_file}': {e}"
            )
        except OSError as e:
            raise StateStoreError(
                f"Failed to read state file '{self.state_file}': {e}"
            )

    def _save_state(self, state: dict) -> None:
        """Save state to the JSON file.

        Args:
            state: Dictionary containing state data to save.

        Raises:
            StateStoreError: If the file cannot be written.
        """
        try:
            # Write atomically by writing to a temp file first, then renaming
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.write("\n")  # Add trailing newline

            # Atomic rename (works on Unix and Windows)
            temp_file.replace(self.state_file)
        except OSError as e:
            raise StateStoreError(
                f"Failed to write state file '{self.state_file}': {e}"
            )

    def get_last_successful_commit(self, environment: str = "default") -> Optional[str]:
        """Get the last successful commit SHA for an environment.

        Args:
            environment: Environment name (e.g., 'production', 'staging').
                        Defaults to 'default'.

        Returns:
            Commit SHA as a string, or None if no successful commit exists.

        Raises:
            StateStoreError: If the operation fails.
        """
        try:
            state = self._load_state()
            environments = state.get("environments", {})
            return environments.get(environment, {}).get("last_successful_commit")
        except Exception as e:
            if isinstance(e, StateStoreError):
                raise
            raise StateStoreError(f"Error getting last successful commit: {e}")

    def set_last_successful_commit(
        self, commit_sha: str, environment: str = "default"
    ) -> None:
        """Set the last successful commit SHA for an environment.

        Args:
            commit_sha: The commit SHA to store.
            environment: Environment name (e.g., 'production', 'staging').
                        Defaults to 'default'.

        Raises:
            StateStoreError: If the operation fails.
        """
        if not commit_sha or not isinstance(commit_sha, str):
            raise StateStoreError("commit_sha must be a non-empty string")

        try:
            state = self._load_state()
            if "environments" not in state:
                state["environments"] = {}

            if environment not in state["environments"]:
                state["environments"][environment] = {}

            state["environments"][environment]["last_successful_commit"] = commit_sha
            self._save_state(state)
        except Exception as e:
            if isinstance(e, StateStoreError):
                raise
            raise StateStoreError(f"Error setting last successful commit: {e}")

    def clear_state(self, environment: str = "default") -> None:
        """Clear state for an environment.

        Args:
            environment: Environment name. Defaults to 'default'.

        Raises:
            StateStoreError: If the operation fails.
        """
        try:
            state = self._load_state()
            if "environments" in state and environment in state["environments"]:
                del state["environments"][environment]
                self._save_state(state)
        except Exception as e:
            if isinstance(e, StateStoreError):
                raise
            raise StateStoreError(f"Error clearing state: {e}")
