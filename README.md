# SAID - Smart Ansible Incremental Deployer

An automation wrapper for Ansible that eliminates redundant tasks by analyzing Git diffs and executing only the minimum required operations.

## Overview

Instead of running a 20-minute full playbook, SAID:
1. Analyzes the Git diff to identify changed files
2. Maps those files to specific Ansible tasks via a Dependency Dictionary
3. Resolves dependencies recursively
4. Validates required variables
5. Executes only the necessary tasks

## Installation

### Prerequisites

- Python 3.10 or higher
- Git repository with your Ansible playbooks
- Ansible 6.0.0 or higher

### Install from Source

```bash
git clone <repository-url>
cd said
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

### 1. Create a Dependency Map

Create a `dependency_map.yml` file in your project root or `ansible/` directory:

```yaml
tasks:
  - name: generate_nginx_conf
    provides: ["web_config"]
    requires_vars: ["http_port", "domain_name"]
    triggers: ["restart_nginx"]
    watch_files: ["templates/nginx.conf.j2", "vars/web.yml"]

  - name: restart_nginx
    provides: ["web_service_state"]
    requires_vars: []
    depends_on: ["web_config"]
```

### 2. Analyze Changes

```bash
# See what would be executed
said analyze

# Analyze specific commit range
said analyze --from-commit HEAD~5 --to-commit HEAD

# Output as JSON for CI/CD
said analyze --json
```

### 3. Execute Deployment

```bash
# Execute based on git changes
said execute

# Dry run first
said execute --dry-run

# Full deployment
said execute --full-deploy
```

### 4. Validate Configuration

```bash
# Validate dependency map and variables
said validate
```

## CLI Commands

### `said analyze`

Analyze changes and generate execution plan without executing.

**Options:**
- `--dependency-map, -d`: Path to dependency_map.yml (auto-discovered if not specified)
- `--from-commit, -f`: Starting commit SHA, branch, or tag
- `--to-commit, -t`: Ending commit (default: HEAD)
- `--repo-path, -r`: Path to git repository
- `--playbook, -p`: Path to Ansible playbook (default: playbook.yml)
- `--inventory, -i`: Path to Ansible inventory file
- `--no-triggers`: Do not include triggered tasks
- `--no-validate`: Skip variable validation
- `--json`: Output results in JSON format

### `said execute`

Execute Ansible tasks based on git changes.

**Options:**
- All options from `analyze` command
- `--dry-run`: Generate command with --check flag
- `--full-deploy`: Execute all tasks regardless of changes
- `--environment, -e`: Environment name for state tracking (default: default)
- `--no-state-update`: Do not update state store after execution

### `said validate`

Validate dependency map and required variables.

**Options:**
- `--dependency-map, -d`: Path to dependency_map.yml
- `--inventory, -i`: Path to Ansible inventory file
- `--variables, -v`: Path to YAML file containing variables

## Dependency Map Format

The dependency map defines tasks, their dependencies, and which files trigger them:

```yaml
tasks:
  - name: task_name              # Unique task identifier
    provides: [resource1]        # Resources this task provides
    depends_on: [resource2]      # Resources this task depends on
    triggers: [task3]            # Tasks triggered by this task
    watch_files:                 # Files that trigger this task
      - "templates/*.j2"
      - "vars/*.yml"
    requires_vars:               # Required variables
      - "var1"
      - "var2"
```

## Architecture

- **Change Detector** (`git_detector.py`): Git-based file change detection
- **Dependency Engine** (`dag_builder.py`, `resolver.py`): DAG-based dependency resolution using NetworkX
- **Parser** (`parser.py`): YAML parsing with caching and auto-discovery
- **Matcher** (`matcher.py`): File-to-task matching with glob patterns
- **Validator** (`validator.py`): Pre-flight variable validation
- **Orchestrator** (`orchestrator.py`): Ansible integration with tag-based execution
- **State Store** (`state_store.py`): Tracks last successful commit per environment
- **Coordinator** (`coordinator.py`): Main workflow orchestration

## Performance Features

- **Caching**: Parsed dependency maps are cached based on file modification time
- **Auto-Discovery**: Automatically finds dependency_map.yml in common locations
- **Multiple Maps**: Supports merging multiple dependency map files
- **Optimized Matching**: Efficient file-to-task matching algorithm

## Safety Features

- **Full Deploy on SAID Changes**: If SAID code itself changes, forces full deploy
- **Full Deploy on Map Changes**: If dependency_map.yml changes, forces full deploy
- **Git State Validation**: Warns if repository has uncommitted changes
- **Variable Validation**: Pre-flight checks for required variables

## Development

This project uses a recursive development model. See:
- [BUILD_PLAN.md](BUILD_PLAN.md) - Detailed task breakdown
- [PRD.md](PRD.md) - Product requirements document
- [CHANGELOG.md](CHANGELOG.md) - Version history

### Running Tests

```bash
pytest
pytest --cov=src/said --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

## License

MIT License - see LICENSE file for details
