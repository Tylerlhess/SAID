# Product Requirements Document: Project SAID

## 1. Executive Summary

Project SAID is an automation wrapper for Ansible that eliminates redundant tasks. Instead of running a 20-minute full playbook, SAID analyzes the Git diff, identifies which files changed, maps those files to specific Ansible tasks via a Dependency Dictionary, and executes only the minimum required operations.

## 2. Core Functional Requirements

- **Git Delta Analysis**: Identify specific changed files between the current HEAD and the LAST_SUCCESSFUL_COMMIT.
- **Variable Validation**: Dynamically verify that all variables required for the impacted templates are present in the environment before execution.
- **Recursive Dependency Resolution**: If Task B depends on Task A, and Task B's config file changed, both A and B must be queued.
- **Flat-File Fast-Track**: If changes are restricted to non-binary configuration files, bypass service restarts unless explicitly required by the dependency tree.

## 3. The Dependency Builder (Logic Design)

The "Dependency Builder" is a pre-processor script (likely Python) that parses your Ansible directory. It builds a Directed Acyclic Graph (DAG) of your deployment.

### A. The Metadata Dictionary Structure

We will use a custom key within Ansible tasks or a standalone manifest.yml.

```yaml
# dependency_map.yml
tasks:
  - name: "generate_nginx_conf"
    provides: "web_config"
    requires_vars: ["http_port", "domain_name"]
    triggers: ["restart_nginx"]
    watch_files: ["templates/nginx.conf.j2", "vars/web.yml"]

  - name: "restart_nginx"
    provides: "web_service_state"
    requires_vars: []
    depends_on: ["web_config"]
```

### B. Recursive Resolution Algorithm

1. **Input**: A list of changed files from git diff.
2. **Match**: Find all tasks where watch_files matches the diff.
3. **Recursion**: For every matched task, look at the depends_on or triggers tags.
4. **Verification**: Check the requires_vars list against the current Ansible hostvars.
5. **Execution Order**: Sort the tasks using a topological sort to ensure dependencies run before dependents.

## 4. Technical Architecture

| Component | Technology | Responsibility |
|-----------|-----------|---------------|
| Change Detector | Git / Python | Exports CHANGED_FILES and COMMIT_RANGE. |
| Dependency Engine | Python / NetworkX | Builds the DAG and outputs a list of Ansible --tags. |
| Orchestrator | Ansible | Receives the filtered tag list and executes the play. |
| State Store | Redis or File | Tracks the last successful commit SHA per environment. |

## 5. Implementation Workflow

### Step 1: Scanning the Playbook

The builder combs through the playbooks. It looks for a specific vars block or comment-based metadata:

```
task_id: db_migration | deps: [db_conn_check] | vars: [db_password]
```

### Step 2: Building the Runtime List

If a developer changes `roles/db/templates/schema.sql.j2`:

- The engine identifies `db_migration` is impacted.
- It sees `db_migration` depends on `db_conn_check`.
- It adds both to the execution queue.
- It validates that `db_password` is not null.

### Step 3: Execution

The final command generated is:

```bash
ansible-playbook site.yml --tags "db_conn_check,db_migration"
```

## 6. Success Metrics

- **Deployment Velocity**: Reduce average deployment time by > 60% for config-only changes.
- **Reliability**: Zero "Missing Variable" errors during execution phase due to pre-flight validation.
- **Safety**: The system must default to a "Full Deploy" if the Git diff contains changes to the Orchestrator itself.
