# Task Scheduler API Reference

Reference for `SynologyTaskScheduler` in `tools/synology_client.py`.

---

## Schedule Dict Schema

Used by `create_script_task(schedule=...)` and `modify_script_task(...)`.

| Field | Type | Required | Values / Notes |
|-------|------|----------|----------------|
| `run_frequently` | bool | ✅ | `True` = repeat on schedule; `False` = one-time run |
| `run_days` | str | if repeat | Comma-separated integers: `"0,1,2,3,4,5,6"` (0=Sunday, 6=Saturday) |
| `repeat` | str | if run_frequently | `"daily"` \| `"weekly"` \| `"monthly"` |
| `start_time_h` | int | ✅ | Hour to start: 0–23 |
| `start_time_m` | int | ✅ | Minute to start: 0–59 |
| `same_day_repeat_h` | int | ✅ | Hours between intraday repeats; `0` = no intraday repeat |
| `same_day_repeat_m` | int | ✅ | Minutes between intraday repeats |
| `same_day_repeat_until` | int \| None | — | Hour to stop intraday repeats; `None` = until end of day |
| `monthly_week` | list[str] | if monthly | `["first"]` \| `["second"]` \| `["third"]` \| `["fourth"]` \| `["last"]` |

### Common schedule examples

```python
# Daily at 02:30
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

# Every weekday at 08:00
schedule = {
    "run_frequently": True,
    "repeat": "weekly",
    "run_days": "1,2,3,4,5",   # Mon-Fri
    "start_time_h": 8,
    "start_time_m": 0,
    "same_day_repeat_h": 0,
    "same_day_repeat_m": 0,
    "same_day_repeat_until": None,
}

# Every hour during business hours (09:00–17:00), weekdays
schedule = {
    "run_frequently": True,
    "repeat": "weekly",
    "run_days": "1,2,3,4,5",
    "start_time_h": 9,
    "start_time_m": 0,
    "same_day_repeat_h": 1,    # repeat every 1 hour
    "same_day_repeat_m": 0,
    "same_day_repeat_until": 17,  # stop at 17:00
}

# One-time run
schedule = {
    "run_frequently": False,
    "start_time_h": 23,
    "start_time_m": 0,
    "same_day_repeat_h": 0,
    "same_day_repeat_m": 0,
    "same_day_repeat_until": None,
}
```

---

## Task Types

The `task_type` parameter in `get_task()`:

| Type | Description |
|------|-------------|
| `"script"` | User-defined shell script (most common) |
| `"beep_control"` | System beep schedule (enable/disable beeps at times) |
| `"service_control"` | Service start/stop schedule |

`create_script_task()` always creates `"script"` type tasks.

---

## Task Result Object Schema

From `get_task_results(task_id)['data']` (array):

```json
{
  "task_id": 5,
  "time": "2024-01-15 02:30:00",
  "duration": 12,
  "exit_code": 0
}
```

`exit_code`: 0 = success; non-zero = script exited with error.
`duration`: seconds the script ran.
`time`: local NAS time (not UTC unless NAS timezone is UTC).

---

## Finding task_id and owner

```python
ts = get_taskscheduler()
result = ts.list_tasks()
for task in result['data']['tasks']:
    print(task['id'], task['owner'], task['name'], task['enable'])
    # task_id = task['id']  (integer)
    # owner   = task['owner']  (DSM username string)
```

---

## Output / Logging Configuration

Task script output is not captured by default. To log script output:

Use `self._api.set_output_config(task_id=task_id, enable=True, log_path="/path/to/log.txt")`
directly on the underlying library object if output logging is needed.
This is not wrapped by `SynologyTaskScheduler` — call `get_taskscheduler()._api.set_output_config(...)`.

---

## Event-Triggered Tasks

`SynologyTaskScheduler` wraps **scheduled** tasks only. Event-triggered tasks
(USB connect, boot-up, shutdown) use a different API (`SYNO.Core.EventScheduler`)
not covered by `synology-api`. Use SSH + `synowebapi` for event triggers:

```bash
# Example via SSH
synowebapi --exec api=SYNO.Core.EventScheduler version=1 method=list
```

---

## Root Tasks

Tasks created by `create_script_task()` run as the connected DSM user (SYNOLOGY_USER).
Root tasks (run as system root) require a separate root token. The factory function
does not support root tasks. To create root tasks, call the underlying library directly:

```python
ts = get_taskscheduler()
# ts._api exposes the raw TaskScheduler instance
# Consult synology-api source for root token flow
```

Root tasks have access to the full NAS filesystem and system commands. Use only when necessary.
