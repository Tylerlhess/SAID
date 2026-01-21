# SAID - Smart Ansible Incremental Deployer

An automation wrapper for Ansible that eliminates redundant tasks by analyzing Git diffs and executing only the minimum required operations.

## Overview

Instead of running a 20-minute full playbook, SAID:
1. Analyzes the Git diff to identify changed files
2. Maps those files to specific Ansible tasks via a Dependency Dictionary
3. Resolves dependencies recursively
4. Validates required variables
5. Executes only the necessary tasks

## Status

🚧 **Under Development** - See [BUILD_PLAN.md](BUILD_PLAN.md) for current progress.

## Quick Start

*Coming soon - project is in active development*

## Architecture

- **Change Detector**: Git-based file change detection
- **Dependency Engine**: DAG-based dependency resolution using NetworkX
- **Orchestrator**: Ansible integration with tag-based execution
- **State Store**: Tracks last successful commit per environment

## Development

This project uses a recursive development model. See:
- [BUILD_PLAN.md](BUILD_PLAN.md) - Detailed task breakdown
- [.cursor/rules/](.cursor/rules/) - Development workflow rules

## License

*TBD*
