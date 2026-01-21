# SAID Build Plan

## Overview
This plan breaks down the SAID project into small, incremental tasks suitable for recursive/iterative development. Each task should be completable in a single focused session and committed to git before moving to the next.

## Phase 1: Foundation & Setup (Tasks 1-5)

### Task 1: Repository Structure
- [x] Create `src/said/` directory structure
- [x] Create `tests/` directory
- [x] Create `examples/` directory for sample Ansible playbooks
- [x] Create `docs/` directory
- [x] Add `.gitignore` for Python/Ansible
- [x] Create `README.md` with project overview
- **Deliverable**: Basic repo structure
- **Commit**: "feat: initialize repository structure" ✅

### Task 2: Python Project Setup
- [x] Create `pyproject.toml` or `setup.py`
- [x] Define dependencies: `ansible`, `networkx`, `pyyaml`, `gitpython`
- [x] Create `requirements.txt` and `requirements-dev.txt`
- [x] Create `src/said/__init__.py`
- [x] Set up basic package structure
- **Deliverable**: Python package ready for development
- **Commit**: "feat: set up Python project structure and dependencies" ✅

### Task 3: Git Integration Module
- [x] Create `src/said/git_detector.py`
- [x] Implement function to get changed files between commits
- [x] Implement function to get commit SHA
- [x] Add error handling for git operations
- [x] Write unit tests in `tests/test_git_detector.py`
- **Deliverable**: Git change detection module
- **Commit**: "feat: implement git change detector module" ✅

### Task 4: State Store Interface
- [x] Create `src/said/state_store.py`
- [x] Define abstract base class for state storage
- [x] Implement file-based state store (JSON/YAML)
- [x] Implement methods: `get_last_successful_commit()`, `set_last_successful_commit()`
- [x] Write unit tests
- **Deliverable**: State storage abstraction
- **Commit**: "feat: implement state store interface and file-based backend" ✅

### Task 5: Configuration Schema
- [x] Create `src/said/schema.py` for dependency map validation
- [x] Define Pydantic models or dataclasses for:
  - Task metadata
  - Dependency map structure
  - Variable requirements
- [x] Add validation logic
- [x] Write unit tests
- **Deliverable**: Data models and validation
- **Commit**: "feat: define dependency map schema and validation" ✅

## Phase 2: Dependency Engine Core (Tasks 6-10)

### Task 6: Dependency Map Parser
- [x] Create `src/said/parser.py`
- [x] Implement YAML parser for `dependency_map.yml`
- [x] Parse task metadata (name, provides, requires_vars, triggers, watch_files, depends_on)
- [x] Handle both standalone manifest and inline metadata
- [x] Write unit tests with sample dependency maps
- **Deliverable**: Dependency map parsing
- **Commit**: "feat: implement dependency map parser" ✅

### Task 7: DAG Builder
- [x] Create `src/said/dag_builder.py`
- [x] Use NetworkX to build directed graph from dependency map
- [x] Implement graph construction from parsed tasks
- [x] Add cycle detection (should fail if cycles found)
- [x] Write unit tests with various dependency scenarios
- **Deliverable**: DAG construction from dependency map
- **Commit**: "feat: implement DAG builder with NetworkX" ✅

### Task 8: File-to-Task Matcher
- [x] Create `src/said/matcher.py`
- [x] Implement function to match changed files to tasks via `watch_files`
- [x] Handle glob patterns and exact matches
- [x] Return list of impacted task names
- [x] Write unit tests
- **Deliverable**: File change to task mapping
- **Commit**: "feat: implement file-to-task matching logic" ✅

### Task 9: Recursive Dependency Resolver
- [x] Create `src/said/resolver.py`
- [x] Implement recursive traversal of dependency graph
- [x] For each matched task, collect all dependencies (depends_on)
- [x] For each matched task, collect all triggered tasks (triggers)
- [x] Use topological sort to determine execution order
- [x] Write unit tests with complex dependency chains
- **Deliverable**: Complete dependency resolution
- **Commit**: "feat: implement recursive dependency resolution with topological sort" ✅

### Task 10: Variable Validator
- [x] Create `src/said/validator.py`
- [x] Implement function to check required variables exist
- [x] Integrate with Ansible hostvars or inventory
- [x] Return validation errors with missing variable names
- [x] Write unit tests
- **Deliverable**: Pre-flight variable validation
- **Commit**: "feat: implement variable validation module" ✅

## Phase 3: Orchestration (Tasks 11-15)

### Task 11: Ansible Integration
- [x] Create `src/said/orchestrator.py`
- [x] Implement function to generate Ansible command with --tags
- [x] Handle tag list formatting
- [x] Add dry-run mode support
- [x] Write unit tests
- **Deliverable**: Ansible command generation
- **Commit**: "feat: implement Ansible orchestrator with tag generation" ✅

### Task 12: Main Workflow Coordinator
- [x] Create `src/said/main.py` or `src/said/coordinator.py`
- [x] Implement main workflow:
  1. Get changed files from git
  2. Load dependency map
  3. Match files to tasks
  4. Resolve dependencies
  5. Validate variables
  6. Generate Ansible command
- [x] Add error handling and logging
- **Deliverable**: End-to-end workflow
- **Commit**: "feat: implement main workflow coordinator" ✅

### Task 13: CLI Interface
- [x] Create `src/said/cli.py` using `click` or `argparse`
- [x] Add commands: `analyze`, `execute`, `validate`
- [x] Add options: `--dry-run`, `--full-deploy`, `--commit-range`
- [x] Add help text and usage examples
- **Deliverable**: Command-line interface
- **Commit**: "feat: implement CLI interface" ✅

### Task 14: Safety Checks
- [x] Add check: if SAID code itself changed, force full deploy
- [x] Add check: if dependency_map.yml changed, force full deploy
- [x] Add check: validate git repository state before proceeding
- [x] Implement these in coordinator
- **Deliverable**: Safety mechanisms
- **Commit**: "feat: add safety checks for orchestrator changes" ✅

### Task 15: State Persistence Integration
- [x] Integrate state store into workflow
- [x] Update last successful commit after successful deployment
- [x] Read last successful commit at start of workflow
- [x] Handle case where no previous successful commit exists
- **Deliverable**: State tracking in workflow
- **Commit**: "feat: integrate state store into deployment workflow" ✅

## Phase 4: Advanced Features & Git Integration (Tasks 16-25)

### Task 16: Enhanced Git Integration
- [ ] Extend `src/said/git_detector.py` with additional methods:
  - [ ] `get_commit_message()` - Extract commit message for context
  - [ ] `get_commit_author()` - Get commit author information
  - [ ] `get_file_diff()` - Get actual diff content for changed files
  - [ ] `get_branch_name()` - Get current branch name
  - [ ] `is_merge_commit()` - Detect merge commits
  - [ ] `get_commit_range()` - Get all commits in a range
- [ ] Add support for git tags as commit references
- [ ] Add support for relative commit references (HEAD~1, HEAD~2, etc.)
- [ ] Write unit tests for new git methods
- **Deliverable**: Enhanced git detection capabilities
- **Commit**: "feat: enhance git detector with commit metadata and range support"

### Task 17: Git Branch & PR Support
- [ ] Create `src/said/git_branch.py` module
- [ ] Implement branch comparison (compare current branch to base branch)
- [ ] Add support for PR/MR workflows (detect base branch automatically)
- [ ] Implement `get_changed_files_between_branches()` method
- [ ] Add CLI option `--base-branch` for branch comparisons
- [ ] Write unit tests
- **Deliverable**: Branch and PR workflow support
- **Commit**: "feat: add git branch and PR comparison support"

### Task 18: Git Hooks Integration
- [ ] Create `src/said/git_hooks.py` module
- [ ] Implement pre-commit hook generator (validate dependency map before commit)
- [ ] Implement post-commit hook generator (auto-update state store on successful deploy)
- [ ] Add CLI command `said hooks install` to set up hooks
- [ ] Add CLI command `said hooks uninstall` to remove hooks
- [ ] Create hook templates in `templates/git_hooks/`
- [ ] Write unit tests
- **Deliverable**: Git hooks for automated validation and state tracking
- **Commit**: "feat: implement git hooks integration for pre/post-commit automation"

### Task 19: Git Submodule Support
- [ ] Extend `GitDetector` to detect submodule changes
- [ ] Add `get_submodule_changes()` method to detect submodule commit updates
- [ ] Handle submodule paths in file matching logic
- [ ] Add support for nested submodules
- [ ] Update coordinator to handle submodule changes appropriately
- [ ] Write unit tests
- **Deliverable**: Git submodule change detection
- **Commit**: "feat: add git submodule change detection support"

### Task 20: Git History Analysis
- [ ] Create `src/said/git_history.py` module
- [ ] Implement `analyze_change_frequency()` - Track which files change most often
- [ ] Implement `get_related_commits()` - Find commits that touched similar files
- [ ] Add `suggest_dependency_updates()` - Suggest dependency map improvements based on history
- [ ] Integrate with coordinator for smarter change detection
- [ ] Write unit tests
- **Deliverable**: Git history analysis for optimization
- **Commit**: "feat: add git history analysis for change pattern detection"

### Task 21: Flat-File Fast-Track
- [ ] Create `src/said/fasttrack.py`
- [ ] Implement `is_config_file_only_change()` - Detect if changes are only non-binary config files
- [ ] Implement `should_skip_service_restart()` - Logic to skip service restarts unless required
- [ ] Add file type detection (binary vs text, config vs code)
- [ ] Integrate with dependency resolver to respect fast-track rules
- [ ] Add CLI option `--fast-track` to enable optimization
- [ ] Write unit tests
- **Deliverable**: Fast-track optimization for config-only changes
- **Commit**: "feat: implement flat-file fast-track optimization"

### Task 22: Logging & Observability
- [ ] Enhance logging in `src/said/coordinator.py` and other modules
- [ ] Set up structured logging with JSON output option
- [ ] Add log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- [ ] Log key events: changed files, matched tasks, resolved dependencies, execution plan, git operations
- [ ] Add `--log-file` CLI option for log output
- [ ] Add `--log-level` CLI option for verbosity control
- [ ] Create log formatter with timestamps and context
- [ ] Write unit tests for logging
- **Deliverable**: Comprehensive structured logging
- **Commit**: "feat: add structured logging and observability"

### Task 23: Error Handling & Recovery
- [ ] Review and enhance error handling throughout codebase
- [ ] Add try-catch blocks in critical paths with specific exception types
- [ ] Implement graceful error messages with actionable suggestions
- [ ] Add rollback suggestions on failure (suggest previous successful commit)
- [ ] Handle edge cases: empty diffs, missing files, invalid commits, corrupted state store
- [ ] Add `--continue-on-error` option for partial deployments
- [ ] Create error recovery strategies for common failure modes
- [ ] Write unit tests for error scenarios
- **Deliverable**: Robust error handling and recovery mechanisms
- **Commit**: "feat: improve error handling and recovery"

### Task 24: Example Playbooks & Documentation
- [ ] Create `examples/simple_playbook/` directory structure
- [ ] Create sample Ansible playbook with roles and tasks
- [ ] Create example `dependency_map.yml` with comprehensive metadata
- [ ] Create `examples/complex_playbook/` with advanced dependency scenarios
- [ ] Create `docs/USAGE.md` with usage examples and common workflows
- [ ] Create `docs/ARCHITECTURE.md` explaining design decisions and component interactions
- [ ] Create `docs/GIT_INTEGRATION.md` documenting git features and workflows
- [ ] Add inline code examples and diagrams
- **Deliverable**: Comprehensive examples and documentation
- **Commit**: "docs: add examples and comprehensive usage documentation"

### Task 25: Integration Tests
- [ ] Create `tests/integration/` directory
- [ ] Create `tests/integration/fixtures/` with sample git repos and playbooks
- [ ] Write `test_full_workflow.py` - End-to-end test with mock Ansible playbook
- [ ] Write `test_git_integration.py` - Test git operations and workflows
- [ ] Write `test_branch_comparison.py` - Test branch and PR comparison features
- [ ] Write `test_error_scenarios.py` - Test error handling and edge cases
- [ ] Test full workflow: git diff → dependency resolution → command generation
- [ ] Test git hooks installation and execution
- [ ] Test submodule change detection
- [ ] Add CI/CD integration test configuration
- **Deliverable**: Comprehensive integration test suite
- **Commit**: "test: add comprehensive integration tests for full workflow"

## Phase 5: Polish & Production Readiness (Tasks 26-30)

### Task 26: Performance Optimization
- [x] Profile dependency resolution for large playbooks
- [x] Optimize file matching algorithm if needed
- [x] Add caching for parsed dependency maps
- [x] Benchmark and document performance
- **Deliverable**: Optimized performance
- **Commit**: "perf: optimize dependency resolution and file matching" ✅

### Task 27: Configuration File Discovery
- [x] Auto-discover `dependency_map.yml` in common locations
- [x] Support multiple dependency map files
- [x] Add config file validation
- **Deliverable**: Flexible configuration discovery
- **Commit**: "feat: add automatic dependency map discovery" ✅

### Task 28: Output Formatting
- [x] Create human-readable execution plan output
- [x] Add JSON output option for CI/CD integration
- [x] Format variable validation results clearly
- **Deliverable**: Improved output formats
- **Commit**: "feat: improve output formatting and add JSON mode" ✅

### Task 29: Unit Test Coverage
- [x] Achieve >80% code coverage
- [x] Add tests for all edge cases
- [x] Use pytest fixtures for common test data
- **Deliverable**: Comprehensive test coverage
- **Commit**: "test: achieve >80% code coverage" ✅

### Task 30: Final Documentation
- [x] Complete README.md with installation and quick start
- [x] Add API documentation (docstrings)
- [x] Create CHANGELOG.md
- [x] Add CONTRIBUTING.md if needed
- **Deliverable**: Complete documentation
- **Commit**: "docs: complete project documentation" ✅

## Development Workflow

1. **Start with Task 1** - Complete it fully, test it, commit it
2. **Move to Task 2** - Build on Task 1, commit separately
3. **Continue sequentially** - Each task builds on previous work
4. **After each commit**: Review git history to understand current state
5. **Use git heavily**: Commit after each logical unit of work
6. **Pass context by state**: Read files, git history, and current codebase state

## Notes

- Each task should be small enough to complete in 30-60 minutes
- Always commit working code, even if incomplete
- Use descriptive commit messages
- Run tests before committing
- Review git diff before each new task to understand current state
