"""Git change detection module for SAID.

This module provides functions to detect changed files between git commits
and retrieve commit information.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from git import Repo, InvalidGitRepositoryError, GitCommandError
from git.exc import GitError
from gitdb.exc import BadName


class GitDetectorError(Exception):
    """Base exception for git detector errors."""

    pass


class GitDetector:
    """Detects changes in a git repository."""

    def __init__(self, repo_path: Optional[str] = None):
        """Initialize the git detector.

        Args:
            repo_path: Path to the git repository. If None, uses current working directory.

        Raises:
            GitDetectorError: If the path is not a valid git repository.
        """
        if repo_path is None:
            repo_path = os.getcwd()

        self.repo_path = Path(repo_path).resolve()

        try:
            self.repo = Repo(self.repo_path)
        except InvalidGitRepositoryError:
            raise GitDetectorError(
                f"Path '{self.repo_path}' is not a valid git repository"
            )
        except GitError as e:
            raise GitDetectorError(f"Error accessing git repository: {e}")

    def get_changed_files(
        self, from_commit: str, to_commit: str = "HEAD"
    ) -> List[str]:
        """Get list of changed files between two commits.

        Args:
            from_commit: Starting commit SHA, branch name, or tag.
            to_commit: Ending commit SHA, branch name, or tag. Defaults to "HEAD".

        Returns:
            List of file paths relative to repository root that changed between commits.

        Raises:
            GitDetectorError: If commits are invalid or git operation fails.
        """
        try:
            # Get the diff between commits
            diff = self.repo.git.diff(
                "--name-only", "--diff-filter=ACMRT", from_commit, to_commit
            )

            if not diff:
                return []

            # Split by newlines and filter out empty strings
            changed_files = [f.strip() for f in diff.split("\n") if f.strip()]

            return changed_files

        except GitCommandError as e:
            raise GitDetectorError(
                f"Error getting changed files between '{from_commit}' and '{to_commit}': {e}"
            )
        except GitError as e:
            raise GitDetectorError(f"Git error while getting changed files: {e}")

    def get_current_commit_sha(self) -> str:
        """Get the SHA of the current HEAD commit.

        Returns:
            Commit SHA as a string.

        Raises:
            GitDetectorError: If git operation fails or repository has no commits.
        """
        try:
            # Try to get HEAD commit - this will fail if there are no commits
            return self.repo.head.commit.hexsha
        except (ValueError, GitCommandError) as e:
            # ValueError is raised when HEAD doesn't point to a valid commit
            raise GitDetectorError(
                "Repository has no commits. Cannot get current commit SHA."
            )
        except GitError as e:
            raise GitDetectorError(f"Git error while getting commit SHA: {e}")

    def get_commit_sha(self, ref: str = "HEAD") -> str:
        """Get the SHA of a specific commit reference.

        Args:
            ref: Git reference (commit SHA, branch name, or tag). Defaults to "HEAD".

        Returns:
            Commit SHA as a string.

        Raises:
            GitDetectorError: If the reference is invalid or git operation fails.
        """
        try:
            commit = self.repo.commit(ref)
            return commit.hexsha
        except (ValueError, GitCommandError, BadName) as e:
            raise GitDetectorError(
                f"Invalid git reference '{ref}' or error accessing commit: {e}"
            )
        except GitError as e:
            raise GitDetectorError(f"Git error while getting commit SHA for '{ref}': {e}")

    def is_dirty(self) -> bool:
        """Check if the working directory has uncommitted changes.

        Returns:
            True if there are uncommitted changes, False otherwise.

        Raises:
            GitDetectorError: If git operation fails.
        """
        try:
            return self.repo.is_dirty()
        except GitError as e:
            raise GitDetectorError(f"Error checking repository status: {e}")

    def get_uncommitted_files(self) -> List[str]:
        """Get list of uncommitted changed files.

        Returns:
            List of file paths relative to repository root that have uncommitted changes.

        Raises:
            GitDetectorError: If git operation fails.
        """
        try:
            # Get modified, added, and renamed files
            diff = self.repo.git.diff("--name-only", "--diff-filter=ACMRT", "HEAD")

            if not diff:
                return []

            changed_files = [f.strip() for f in diff.split("\n") if f.strip()]

            # Also get untracked files
            untracked = self.repo.untracked_files

            # Combine and return unique files
            all_files = set(changed_files) | set(untracked)
            return sorted(list(all_files))

        except GitCommandError as e:
            raise GitDetectorError(f"Error getting uncommitted files: {e}")
        except GitError as e:
            raise GitDetectorError(f"Git error while getting uncommitted files: {e}")
