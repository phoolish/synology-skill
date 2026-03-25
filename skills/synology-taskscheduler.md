---
name: synology-taskscheduler
description: Use when listing, creating, running, enabling, disabling, or deleting scheduled tasks on a Synology NAS Task Scheduler.
---

# Synology Task Scheduler

Prerequisites: ensure env vars from `synology-nas` (SKILL.md) are set.
Authorization: follow the tier model defined in SKILL.md (🟢 SAFE / 🔵 SENSITIVE / ⚠️ DESTRUCTIVE).

```python
from tools.synology_client import get_taskscheduler
ts = get_taskscheduler()
```

Full reference: [`references/taskscheduler-api.md`](../references/taskscheduler-api.md)

---

## Finding task_id and owner

Both are needed for most methods. Always retrieve from `list_tasks()`:

```python
result = ts.list_tasks()
for task in result['data']['tasks']:
    print(task['id'], task['owner'], task['name'], task['enable'])
    # task_id = task['id']   (integer)
    # owner   = task['owner']  (DSM username string, e.g. "admin")
```

## Checking recent task failures (common workflow)

`get_task_results()` requires a `task_id` — there is no bulk "all recent results" endpoint.
To find tasks with recent failures, iterate `list_tasks()` first:

```python
ts = get_taskscheduler()
tasks = ts.list_tasks()
for task in tasks['data']['tasks']:
    results = ts.get_task_results(task['id'])
    runs = results.get('data', [])
    failed = [r for r in runs if r['exit_code'] != 0]
    if failed:
        print(f"Task '{task['name']}' (id={task['id']}): {len(failed)} failed run(s)")
        print(f"  Last failure: {failed[-1]['time']} (exit {failed[-1]['exit_code']})")
```

**Session note:** If using TaskScheduler alongside other modules (FileStation, etc.) in one script,
all share the same DSM session. `logout()` on any instance invalidates all. See SKILL.md.

---

## Methods

### `list_tasks(sort_by="name", sort_direction="ASC")` — 🟢 SAFE
List all scheduled tasks.

```python
result = ts.list_tasks()
for task in result['data']['tasks']:
    enabled = "✓" if task['enable'] else "✗"
    print(f"[{enabled}] {task['id']} {task['name']} (owner: {task['owner']})")
```

### `get_task(task_id, owner, task_type="script")` — 🔵 SENSITIVE
Get task configuration including script source.

🔵 **Intent declaration required** before calling:
"I'm going to read task `[task_id]` (`[name]`), which contains script source code that may include credentials or sensitive commands."

```python
result = ts.get_task(5, "admin")
script = result['data']['script']
```

`task_type`: `"script"` (default) | `"beep_control"` | `"service_control"`

### `get_task_results(task_id)` — 🟢 SAFE
Get execution history for a task.

```python
result = ts.get_task_results(5)
for run in result['data']:
    print(run['time'], "exit:", run['exit_code'], "duration:", run['duration'], "s")
```

`exit_code` 0 = success; non-zero = script error.

### `run_now(task_id, owner)` — ⚠️ DESTRUCTIVE
Trigger immediate execution of a task.

⚠️ **Confirmation gate required** before calling:
1. "This will immediately execute task `[task_id]` (`[name]`) owned by `[owner]`."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
ts.run_now(5, "admin")
```

### `enable(task_id, owner)` — 🟢 SAFE
Enable a disabled scheduled task.

```python
ts.enable(5, "admin")
```

### `disable(task_id, owner)` — 🟢 SAFE
Disable a scheduled task without deleting it.

```python
ts.disable(5, "admin")
```

### `delete(task_id, owner)` — ⚠️ DESTRUCTIVE
Permanently delete a scheduled task. **Irreversible.**

⚠️ **Confirmation gate required** before calling:
1. "This will permanently delete task `[task_id]` (`[name]`) owned by `[owner]`."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
ts.delete(5, "admin")
```

### `create_script_task(name, owner, script, schedule, ...)` — 🔵 SENSITIVE
Create a new scheduled script task.

🔵 **Intent declaration required** before calling:
"I'm going to create a scheduled script named `[name]` on the NAS, running as `[owner]`."

```python
schedule = {
    "run_frequently": True,
    "repeat": "daily",
    "run_days": "0,1,2,3,4,5,6",
    "start_time_h": 2,
    "start_time_m": 30,
    "same_day_repeat_h": 0,
    "same_day_repeat_m": 0,
    "same_day_repeat_until": None,
}

ts.create_script_task(
    name="Daily Backup",
    owner="admin",
    script="#!/bin/bash\n/usr/local/bin/backup.sh",
    schedule=schedule,
    enable=True,
)
```

Full `schedule` dict schema: [`references/taskscheduler-api.md`](../references/taskscheduler-api.md)

`owner` must be a valid DSM username. Tasks run as that user (non-root by default).

### `modify_script_task(task_id, **kwargs)` — ⚠️ DESTRUCTIVE
Modify an existing script task. Overwrites current configuration.

⚠️ **Confirmation gate required** before calling:
1. "This will modify task `[task_id]`. Fields being changed: `[list kwargs keys]`."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
ts.modify_script_task(5, enable=False, script="#!/bin/bash\necho updated")
```
