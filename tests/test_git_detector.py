"""Unit tests for git_detector module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError, GitCommandError

from said.git_detector import GitDetector, GitDetectorError


class TestGitDetector:
    """Test cases for GitDetector class."""

    def test_init_with_valid_repo(self):
        """Test initialization with a valid git repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            # Create an initial commit
            (Path(tmpdir) / "test.txt").write_text("test")
            repo.index.add(["test.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            assert detector.repo_path == Path(tmpdir).resolve()
            assert detector.repo is not None
            detector.repo.close()

    def test_init_with_invalid_repo(self):
        """Test initialization with a non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(GitDetectorError) as exc_info:
                GitDetector(tmpdir)
            assert "not a valid git repository" in str(exc_info.value)

    def test_init_with_default_path(self):
        """Test initialization with default path (current directory)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                repo = Repo.init(tmpdir)
                # Create an initial commit
                (Path(tmpdir) / "test.txt").write_text("test")
                repo.index.add(["test.txt"])
                repo.index.commit("Initial commit")
                repo.close()

                detector = GitDetector()
                assert detector.repo_path == Path(tmpdir).resolve()
                detector.repo.close()
            finally:
                os.chdir(original_cwd)

    def test_get_current_commit_sha(self):
        """Test getting current commit SHA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            # Create an initial commit
            (Path(tmpdir) / "test.txt").write_text("test")
            repo.index.add(["test.txt"])
            commit = repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            sha = detector.get_current_commit_sha()
            assert sha == commit.hexsha
            assert len(sha) == 40  # SHA-1 is 40 characters
            detector.repo.close()

    def test_get_current_commit_sha_no_commits(self):
        """Test getting commit SHA from repository with no commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Repo.init(tmpdir)
            detector = GitDetector(tmpdir)

            with pytest.raises(GitDetectorError) as exc_info:
                detector.get_current_commit_sha()
            assert "no commits" in str(exc_info.value).lower()
            detector.repo.close()

    def test_get_commit_sha_with_ref(self):
        """Test getting commit SHA with a specific reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            # Create an initial commit
            (Path(tmpdir) / "test.txt").write_text("test")
            repo.index.add(["test.txt"])
            commit1 = repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            sha = detector.get_commit_sha("HEAD")
            assert sha == commit1.hexsha

            # Test with commit SHA directly
            sha2 = detector.get_commit_sha(commit1.hexsha)
            assert sha2 == commit1.hexsha
            detector.repo.close()

    def test_get_commit_sha_invalid_ref(self):
        """Test getting commit SHA with invalid reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "test.txt").write_text("test")
            repo.index.add(["test.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            with pytest.raises(GitDetectorError) as exc_info:
                detector.get_commit_sha("invalid-ref-12345")
            assert "Invalid git reference" in str(exc_info.value)
            detector.repo.close()

    def test_get_changed_files_between_commits(self):
        """Test getting changed files between two commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)

            # Create initial commit
            (Path(tmpdir) / "file1.txt").write_text("content1")
            (Path(tmpdir) / "file2.txt").write_text("content2")
            repo.index.add(["file1.txt", "file2.txt"])
            commit1 = repo.index.commit("Initial commit")

            # Create second commit with changes
            (Path(tmpdir) / "file1.txt").write_text("modified content1")
            (Path(tmpdir) / "file3.txt").write_text("content3")
            repo.index.add(["file1.txt", "file3.txt"])
            commit2 = repo.index.commit("Second commit")
            repo.close()

            detector = GitDetector(tmpdir)
            # Get changed files between commits
            changed = detector.get_changed_files(commit1.hexsha, commit2.hexsha)
            assert "file1.txt" in changed
            assert "file3.txt" in changed
            assert "file2.txt" not in changed  # Not modified
            detector.repo.close()

    def test_get_changed_files_no_changes(self):
        """Test getting changed files when there are no changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)

            # Create initial commit
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            commit1 = repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            # Get changed files (same commit to same commit)
            changed = detector.get_changed_files(commit1.hexsha, commit1.hexsha)
            assert changed == []
            detector.repo.close()

    def test_get_changed_files_invalid_commit(self):
        """Test getting changed files with invalid commit reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            with pytest.raises(GitDetectorError) as exc_info:
                detector.get_changed_files("invalid-commit", "HEAD")
            assert "Error getting changed files" in str(exc_info.value)
            detector.repo.close()

    def test_is_dirty_clean_repo(self):
        """Test is_dirty on a clean repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            assert detector.is_dirty() is False
            detector.repo.close()

    def test_is_dirty_with_uncommitted_changes(self):
        """Test is_dirty on a repository with uncommitted changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            # Make uncommitted change
            (Path(tmpdir) / "file1.txt").write_text("modified content")

            detector = GitDetector(tmpdir)
            assert detector.is_dirty() is True
            detector.repo.close()

    def test_get_uncommitted_files(self):
        """Test getting uncommitted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            # Make uncommitted changes
            (Path(tmpdir) / "file1.txt").write_text("modified content")
            (Path(tmpdir) / "file2.txt").write_text("new file")

            detector = GitDetector(tmpdir)
            uncommitted = detector.get_uncommitted_files()
            assert "file1.txt" in uncommitted
            assert "file2.txt" in uncommitted
            detector.repo.close()

    def test_get_uncommitted_files_no_changes(self):
        """Test getting uncommitted files when repository is clean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            repo.index.commit("Initial commit")
            repo.close()

            detector = GitDetector(tmpdir)
            uncommitted = detector.get_uncommitted_files()
            assert uncommitted == []
            detector.repo.close()

    @patch("said.git_detector.Repo")
    def test_init_git_error_handling(self, mock_repo_class):
        """Test error handling during initialization."""
        mock_repo_class.side_effect = InvalidGitRepositoryError("test error")

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(GitDetectorError) as exc_info:
                GitDetector(tmpdir)
            assert "not a valid git repository" in str(exc_info.value)

    @patch("said.git_detector.Repo")
    def test_get_changed_files_git_command_error(self, mock_repo_class):
        """Test error handling when git command fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_repo = Mock()
            mock_repo.git.diff.side_effect = GitCommandError("git", "diff error")
            mock_repo_class.return_value = mock_repo

            detector = GitDetector(tmpdir)
            with pytest.raises(GitDetectorError) as exc_info:
                detector.get_changed_files("commit1", "commit2")
            assert "Error getting changed files" in str(exc_info.value)

    def test_get_changed_files_filters_correctly(self):
        """Test that get_changed_files only returns added, copied, modified, renamed, or type-changed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repo.init(tmpdir)

            # Create initial commit
            (Path(tmpdir) / "file1.txt").write_text("content1")
            repo.index.add(["file1.txt"])
            commit1 = repo.index.commit("Initial commit")

            # Create second commit with various changes
            (Path(tmpdir) / "file1.txt").write_text("modified")  # Modified
            (Path(tmpdir) / "file2.txt").write_text("new")  # Added
            (Path(tmpdir) / "file3.txt").write_text("to delete")
            repo.index.add(["file1.txt", "file2.txt", "file3.txt"])
            commit2 = repo.index.commit("Second commit")

            # Delete a file in third commit
            repo.index.remove(["file3.txt"])
            commit3 = repo.index.commit("Third commit")
            repo.close()

            detector = GitDetector(tmpdir)
            # Get changed files (should not include deleted files due to --diff-filter=ACMRT)
            changed = detector.get_changed_files(commit1.hexsha, commit2.hexsha)
            assert "file1.txt" in changed
            assert "file2.txt" in changed

            # Deleted files should not appear
            changed2 = detector.get_changed_files(commit2.hexsha, commit3.hexsha)
            # file3.txt was deleted, so it should not be in the list
            assert "file3.txt" not in changed2
            detector.repo.close()
