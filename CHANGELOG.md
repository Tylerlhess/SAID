# Changelog

All notable changes to SAID will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-XX

### Added
- Initial release of SAID (Smart Ansible Incremental Deployer)
- Git change detection module (`git_detector.py`)
- State store interface with file-based backend (`state_store.py`)
- Dependency map schema and validation (`schema.py`)
- Dependency map parser supporting YAML files and inline metadata (`parser.py`)
- DAG builder using NetworkX for dependency resolution (`dag_builder.py`)
- File-to-task matcher with glob pattern support (`matcher.py`)
- Recursive dependency resolver with topological sort (`resolver.py`)
- Variable validator for pre-flight checks (`validator.py`)
- Ansible orchestrator for command generation (`orchestrator.py`)
- Main workflow coordinator (`coordinator.py`)
- CLI interface with `analyze`, `execute`, and `validate` commands (`cli.py`)

### Performance
- Added caching for parsed dependency maps (Task 26)
- Cache invalidation based on file modification time
- Optimized file matching algorithm

### Features
- Auto-discovery of dependency_map.yml in common locations (Task 27)
- Support for multiple dependency map files with merging
- Enhanced output formatting with human-readable and JSON modes (Task 28)
- Improved execution plan display with visual indicators

### Testing
- Comprehensive unit test suite
- Test coverage for all core modules
- Integration test framework

### Documentation
- Complete README with installation and usage instructions
- API documentation via docstrings
- CHANGELOG for version tracking
