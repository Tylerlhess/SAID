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

## Phase 4: Advanced Features (Tasks 16-20)

### Task 16: Flat-File Fast-Track
- [ ] Create `src/said/fasttrack.py`
- [ ] Detect if changes are only non-binary config files
- [ ] Implement logic to skip service restarts unless required
- [ ] Integrate with dependency resolver
- [ ] Write unit tests
- **Deliverable**: Fast-track optimization
- **Commit**: "feat: implement flat-file fast-track optimization"

### Task 17: Logging & Observability
- [ ] Set up structured logging (use `logging` module)
- [ ] Add log levels and formatting
- [ ] Log: changed files, matched tasks, resolved dependencies, execution plan
- [ ] Create log output file option
- **Deliverable**: Comprehensive logging
- **Commit**: "feat: add structured logging and observability"

### Task 18: Error Handling & Recovery
- [ ] Add try-catch blocks throughout
- [ ] Implement graceful error messages
- [ ] Add rollback suggestions on failure
- [ ] Handle edge cases (empty diffs, missing files, etc.)
- **Deliverable**: Robust error handling
- **Commit**: "feat: improve error handling and recovery"

### Task 19: Example Playbooks & Documentation
- [ ] Create `examples/simple_playbook/` with sample Ansible structure
- [ ] Create example `dependency_map.yml`
- [ ] Create `docs/USAGE.md` with usage examples
- [ ] Create `docs/ARCHITECTURE.md` explaining design decisions
- **Deliverable**: Examples and documentation
- **Commit**: "docs: add examples and usage documentation"

### Task 20: Integration Tests
- [ ] Create `tests/integration/` directory
- [ ] Write end-to-end test with mock Ansible playbook
- [ ] Test full workflow: git diff → dependency resolution → command generation
- [ ] Test edge cases and error scenarios
- **Deliverable**: Integration test suite
- **Commit**: "test: add integration tests for full workflow"

## Phase 5: Polish & Production Readiness (Tasks 21-25)

### Task 21: Performance Optimization
- [ ] Profile dependency resolution for large playbooks
- [ ] Optimize file matching algorithm if needed
- [ ] Add caching for parsed dependency maps
- [ ] Benchmark and document performance
- **Deliverable**: Optimized performance
- **Commit**: "perf: optimize dependency resolution and file matching"

### Task 22: Configuration File Discovery
- [ ] Auto-discover `dependency_map.yml` in common locations
- [ ] Support multiple dependency map files
- [ ] Add config file validation
- **Deliverable**: Flexible configuration discovery
- **Commit**: "feat: add automatic dependency map discovery"

### Task 23: Output Formatting
- [ ] Create human-readable execution plan output
- [ ] Add JSON output option for CI/CD integration
- [ ] Format variable validation results clearly
- **Deliverable**: Improved output formats
- **Commit**: "feat: improve output formatting and add JSON mode"

### Task 24: Unit Test Coverage
- [ ] Achieve >80% code coverage
- [ ] Add tests for all edge cases
- [ ] Use pytest fixtures for common test data
- **Deliverable**: Comprehensive test coverage
- **Commit**: "test: achieve >80% code coverage"

### Task 25: Final Documentation
- [ ] Complete README.md with installation and quick start
- [ ] Add API documentation (docstrings)
- [ ] Create CHANGELOG.md
- [ ] Add CONTRIBUTING.md if needed
- **Deliverable**: Complete documentation
- **Commit**: "docs: complete project documentation"

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
