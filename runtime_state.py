import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "runtime_state.json"


AGENTS = {
    "hq": "Market HQ",
    "news": "News Agent",
    "turkey_news": "Turkey News Agent",
    "turkey_market": "Turkey Market Data",
    "company_updates": "Company Updates",
    "market_data": "Market Data Agent",
    "analyst": "Analyst Agent",
    "performance": "Performance Tracker",
    "strategy_lab": "Strategy Lab",
    "fin_sys": "FIN[SYS] Method Engine",
    "youtube": "YouTube Visual Engine",
    "agentwork": "AgentWork Place",
}

TASK_QUEUED = "QUEUED"
TASK_WORKING = "WORKING"
TASK_COMPLETED = "COMPLETED"
TASK_ERROR = "ERROR"
TASK_CANCELLED = "CANCELLED"

PRIORITY_LOW = 1
PRIORITY_NORMAL = 2
PRIORITY_HIGH = 3
PRIORITY_CRITICAL = 4

def utc_now():



def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def create_default_state():

    agents = {}

    for agent_id, name in AGENTS.items():

        agents[agent_id] = {
            "name": name,
            "status": "IDLE",
            "detail": "Hazır.",
            "progress": 0,
            "updated_at": None,
            "last_started_at": None,
            "last_completed_at": None,
            "last_error": None,
            "current_task": None,
        }

    return {
        "version": 4,

        "system": {
            "status": "IDLE",
            "message": "MarketHQ hazır.",
            "run_count": 0,
            "started_at": None,
            "completed_at": None,
            "updated_at": utc_now(),
            "current_task": None,
            "current_run_id": None,
        },

        "agents": agents,

        "events": [],

        "tasks": [],
    }


def read_state():

    if not STATE_FILE.exists():

        state = create_default_state()

        write_state(state)

        return state

    try:

        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            state = json.load(file)

        if not isinstance(
            state,
            dict,
        ):

            state = create_default_state()

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):

        state = create_default_state()

    base = create_default_state()

    state.setdefault(
        "system",
        base["system"],
    )

    state.setdefault(
        "agents",
        {},
    )

    state.setdefault(
        "events",
        [],
    )

    state.setdefault(
        "tasks",
        [],
    )

    state["system"].setdefault(
        "current_task",
        None,
    )

    state["system"].setdefault(
        "current_run_id",
        None,
    )

    for agent_id, agent in base[
        "agents"
    ].items():

        if agent_id not in state["agents"]:

            state[
                "agents"
            ][agent_id] = agent

        else:

            existing = state[
                "agents"
            ][agent_id]

            existing.setdefault(
                "current_task",
                None,
            )

    return state


def write_state(state):

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="runtime_state_",
        suffix=".tmp",
        dir=str(BASE_DIR),
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                state,
                file,
                ensure_ascii=False,
                indent=2,
            )

            file.flush()

            os.fsync(
                file.fileno()
            )

        os.replace(
            temp_name,
            STATE_FILE,
        )

    finally:

        if os.path.exists(
            temp_name
        ):

            try:

                os.remove(
                    temp_name
                )

            except OSError:

                pass


def initialize_runtime_state():

    if not STATE_FILE.exists():

        write_state(
            create_default_state()
        )


def get_runtime_state():

    return read_state()


# =========================================================
# RUN ID
# =========================================================

def create_run_id():

    return (
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d-%H%M%S"
        )
        + "-"
        + uuid.uuid4().hex[:6]
    )


# =========================================================
# EVENTS
# =========================================================

def add_event(
    agent_id,
    event_type,
    message,
    metadata=None,
):

    state = read_state()

    agent = state[
        "agents"
    ].get(
        agent_id,
        {},
    )

    event = {
        "id": uuid.uuid4().hex,
        "timestamp": utc_now(),
        "agent_id": agent_id,
        "agent_name": agent.get(
            "name",
            agent_id,
        ),
        "event_type": event_type,
        "message": message,
        "metadata": metadata or {},
    }

    state["events"].append(
        event
    )

    state["events"] = (
        state["events"][-250:]
    )

    write_state(state)

    return event


# =========================================================
# SYSTEM
# =========================================================

def set_system_status(
    status,
    message="",
    run_id=None,
):

    state = read_state()

    system = state["system"]
    now = utc_now()

    system["status"] = status
    system["message"] = message
    system["updated_at"] = now

    if run_id is not None:
        system["current_run_id"] = run_id

    if status == "WORKING":

        system["started_at"] = now
        system["completed_at"] = None

        system["run_count"] = (
            int(
                system.get(
                    "run_count",
                    0,
                )
            )
            + 1
        )

    elif status == "COMPLETED":

        system["completed_at"] = now
        system["current_task"] = None

    elif status == "ERROR":

        system["completed_at"] = now
        system["current_task"] = None

    write_state(state)


def set_system_task(
    task_id,
    task_name,
):

    state = read_state()

    state["system"]["current_task"] = {
        "id": task_id,
        "name": task_name,
        "updated_at": utc_now(),
    }

    write_state(state)


# =========================================================
# AGENT STATUS
# =========================================================

def set_agent_status(
    agent_id,
    status,
    detail="",
    progress=None,
    error=None,
):

    state = read_state()

    if agent_id not in state["agents"]:

        state["agents"][agent_id] = {
            "name": agent_id,
            "status": "IDLE",
            "detail": "",
            "progress": 0,
            "updated_at": None,
            "last_started_at": None,
            "last_completed_at": None,
            "last_error": None,
            "current_task": None,
        }

    agent = state[
        "agents"
    ][agent_id]

    now = utc_now()

    old_status = agent.get(
        "status",
        "IDLE",
    )

    agent["status"] = status
    agent["detail"] = detail
    agent["updated_at"] = now

    if progress is not None:

        agent["progress"] = max(
            0,
            min(
                100,
                int(progress),
            ),
        )

    if status == "WORKING":

        agent[
            "last_started_at"
        ] = now

        agent[
            "last_error"
        ] = None

    elif status == "COMPLETED":

        agent["progress"] = 100

        agent[
            "last_completed_at"
        ] = now

        agent[
            "last_error"
        ] = None

        agent[
            "current_task"
        ] = None

    elif status == "ERROR":

        agent[
            "last_error"
        ] = error or detail

        agent[
            "current_task"
        ] = None

    write_state(state)

    if old_status != status:

        event_type = "status_change"

        if status == "WORKING":
            event_type = "started"

        elif status == "COMPLETED":
            event_type = "completed"

        elif status == "ERROR":
            event_type = "error"

        add_event(
            agent_id,
            event_type,
            detail,
        )


# =========================================================
# TASKS
# =========================================================

def create_task(
    task_id,
    task_name,
    owner="hq",
    run_id=None,
    metadata=None,
):

    state = read_state()

    task = {
        "id": task_id,
        "name": task_name,
        "owner": owner,
        "agent_id": None,
        "run_id": run_id,
        "status": "QUEUED",
        "created_at": utc_now(),
        "started_at": None,
        "completed_at": None,
        "metadata": metadata or {},
    }

    state["tasks"].append(
        task
    )

    state["tasks"] = (
        state["tasks"][-150:]
    )

    write_state(state)

    add_event(
        owner,
        "task_created",
        f"Görev oluşturuldu: {task_name}",
        {
            "task_id": task_id,
            "run_id": run_id,
        },
    )

    return task


def start_task(
    task_id,
    agent_id,
):

    state = read_state()

    target = None

    for task in state["tasks"]:

        if task.get("id") == task_id:

            target = task
            break

    if target is None:

        raise ValueError(
            f"Görev bulunamadı: {task_id}"
        )

    now = utc_now()

    target["status"] = "WORKING"
    target["agent_id"] = agent_id
    target["started_at"] = now

    state["agents"][
        agent_id
    ]["current_task"] = {
        "id": task_id,
        "name": target["name"],
        "started_at": now,
    }

    state["system"][
        "current_task"
    ] = {
        "id": task_id,
        "name": target["name"],
        "agent_id": agent_id,
        "updated_at": now,
    }

    write_state(state)

    add_event(
        agent_id,
        "task_started",
        (
            f"Görev başladı: "
            f"{target['name']}"
        ),
        {
            "task_id": task_id,
        },
    )


def complete_task(
    task_id,
    agent_id,
    detail="Görev tamamlandı.",
):

    state = read_state()

    target = None

    for task in state["tasks"]:

        if task.get("id") == task_id:

            target = task
            break

    if target is None:
        return

    now = utc_now()

    target["status"] = "COMPLETED"
    target["completed_at"] = now
    target["agent_id"] = agent_id

    if agent_id in state["agents"]:

        current_task = (
            state["agents"][agent_id]
            .get("current_task")
        )

        if (
            current_task
            and current_task.get("id")
            == task_id
        ):

            state["agents"][
                agent_id
            ]["current_task"] = None

    current_system_task = (
        state["system"].get(
            "current_task"
        )
    )

    if (
        current_system_task
        and current_system_task.get("id")
        == task_id
    ):

        state["system"][
            "current_task"
        ] = None

    write_state(state)

    add_event(
        agent_id,
        "task_completed",
        detail,
        {
            "task_id": task_id,
        },
    )


def fail_task(
    task_id,
    agent_id,
    error,
):

    state = read_state()

    target = None

    for task in state["tasks"]:

        if task.get("id") == task_id:

            target = task
            break

    if target is None:
        return

    target["status"] = "ERROR"
    target["completed_at"] = utc_now()
    target["agent_id"] = agent_id

    if agent_id in state["agents"]:

        state["agents"][
            agent_id
        ]["current_task"] = None

    write_state(state)

    add_event(
        agent_id,
        "task_error",
        (
            "Görev hata verdi: "
            f"{error}"
        ),
        {
            "task_id": task_id,
        },
    )


def handoff_task(
    from_agent,
    to_agent,
    task_id,
    task_name,
    run_id=None,
    metadata=None,
):

    state = read_state()

    task = None

    for item in state["tasks"]:

        if item.get("id") == task_id:

            task = item
            break

    if task is None:

        task = create_task(
            task_id,
            task_name,
            owner=from_agent,
            run_id=run_id,
            metadata=metadata,
        )

    task["status"] = "QUEUED"
    task["agent_id"] = to_agent
    task["run_id"] = run_id

    if metadata:

        task["metadata"] = metadata

    write_state(state)

    add_event(
        from_agent,
        "handoff",
        (
            f"{task_name} → "
            f"{AGENTS.get(to_agent, to_agent)}"
        ),
        {
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "run_id": run_id,
            "task_name": task_name,
        },
    )


# =========================================================
# HELPERS
# =========================================================

def get_tasks(
    run_id=None,
    limit=50,
):

    state = read_state()

    tasks = state.get(
        "tasks",
        [],
    )

    if run_id:

        tasks = [
            task
            for task in tasks
            if task.get("run_id")
            == run_id
        ]

    return list(
        reversed(
            tasks[-limit:]
        )
    )



# ========================================================
# AGENTWORK PLACE TASK MANAGEMENT
# ========================================================

def create_agentwork_task(
    task_id,
    task_name,
    owner="hq",
    agent_id=None,
    metadata=None,
    priority=PRIORITY_NORMAL,
):
    """Create a new task in the AgentWork Place queue."""
    state = read_state()
    task = {
        "id": task_id,
        "name": task_name,
        "owner": owner,
        "agent_id": agent_id,
        "status": TASK_QUEUED,
        "priority": priority,
        "created_at": utc_now(),
        "started_at": None,
        "completed_at": None,
        "metadata": metadata or {},
    }
    state["tasks"].append(task)
    state["tasks"] = state["tasks"][-200:]  # keep last 200
    write_state(state)
    add_event(
        owner,
        "agentwork_task_created",
        f"AgentWork task created: {task_name}",
        {"task_id": task_id, "priority": priority},
    )
    return task


def start_agentwork_task(task_id, agent_id):
    """Start working on an AgentWork task."""
    state = read_state()
    target = None
    for task in state["tasks"]:
        if task.get("id") == task_id:
            target = task
            break
    if target is None:
        raise ValueError(f"AgentWork task not found: {task_id}")
    now = utc_now()
    target["status"] = TASK_WORKING
    target["agent_id"] = agent_id
    target["started_at"] = now
    # Update agent status
    if agent_id in state["agents"]:
        state["agents"][agent_id]["current_task"] = {
            "id": task_id,
            "name": target["name"],
            "started_at": now,
        }
        state["agents"][agent_id]["status"] = TASK_WORKING
        state["agents"][agent_id]["detail"] = f"Calışiyor: {task_name}"
        state["agents"][agent_id]["progress"] = 50
    # Update system task
    state["system"]["current_task"] = {
        "id": task_id,
        "name": target["name"],
        "agent_id": agent_id,
        "updated_at": now,
    }
    write_state(state)
    add_event(
        agent_id,
        "task_started",
        f"AgentWork görev başladı: {target['name']}",
        {"task_id": task_id},
    )
    return target


def complete_agentwork_task(task_id, agent_id, detail="Görev tamamlandı."):
    """Mark an AgentWork task as completed."""
    state = read_state()
    target = None
    for task in state["tasks"]:
        if task.get("id") == task_id:
            target = task
            break
    if target is None:
        return
    now = utc_now()
    target["status"] = TASK_COMPLETED
    target["completed_at"] = now
    target["agent_id"] = agent_id
    # Clear agent current task
    if agent_id in state["agents"]:
        current_task = state["agents"][agent_id].get("current_task")
        if current_task and current_task.get("id") == task_id:
            state["agents"][agent_id]["current_task"] = None
        # Reset agent status
        state["agents"][agent_id]["status"] = TASK_IDLE if "IDLE" in str(state["agents"][agent_id]) else "IDLE"
        state["agents"][agent_id]["detail"] = ""
        state["agents"][agent_id]["progress"] = 0
    # Clear system task
    if state["system"].get("current_task", {}).get("id") == task_id:
        state["system"]["current_task"] = None
    write_state(state)
    add_event(
        agent_id,
        "task_completed
        detail,
        {"task_id": task_id},
    )
    return target


def fail_agentwork_task(task_id, agent_id, error):
    """Mark an AgentWork task as failed."""
    state = read_state()
    target = None
    for task in state["tasks"]:
        if task.get("id") == task_id:
            target = task
            break
    if target is None:
        return
    target["status"] = TASK_ERROR
    target["completed_at"] = utc_now()
    target["agent_id"] = agent_id
    if agent_id in state["agents"]:
        if agent_id in state["agents"]:
            state["agents"][agent_id]["current_task"] = None
        state["agents"][agent_id]["status"] = TASK_ERROR
        state["agents"][agent_id]["detail"] = error
        state["agents"][agent_id]["progress"] = 0
    write_state(state)
    add_event(
        agent_id,
        "task_error",
        f"AgentWork görev hata verdi: {error}",
        {"task_id": task_id},
    )
    return target


def get_agentwork_tasks(
    agent_id=None,
    status=None,
    limit=50,
):
    """Get AgentWork tasks filtered by agent or status."""
    state = read_state()
    tasks = state.get("tasks", [])
    if agent_id:
        tasks = [t for t in tasks if t.get("agent_id") == agent_id]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return list(reversed(tasks[-limit:]))

initialize_runtime_state()

