"""Claude Code hook for Sirena.

Claude Code pipes each hook event to this script as JSON on stdin. The script
records what that session is doing in states/<session_id>.json, and the
floating Sirena window (sirena.py) reads those files to choose her animation.
It never blocks Claude: any error is swallowed and it always exits 0.
"""
import json
import os
import sys
import time

STATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states")

# hook event -> Sirena state
EVENT_STATE = {
    "SessionStart": "hello",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "SubagentStart": "working",
    "PostToolUseFailure": "oops",  # brief sigh, then back to working
    "PermissionRequest": "needs_you",
    "Stop": "waiting",  # finished its turn: now waiting for your reply
    "StopFailure": "failed",
}


def _log_event(data):
    """Keeps a short trail of received events in events.log, so the mapping can be checked."""
    path = os.path.join(os.path.dirname(STATES_DIR), "events.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 200_000:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s %s %s mode=%s\n" % (time.strftime("%H:%M:%S"), str(data.get("session_id", ""))[:8],
                                               data.get("hook_event_name", ""), data.get("notification_type", ""),
                                               data.get("permission_mode", "")))
    except Exception:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    event = data.get("hook_event_name", "")
    _log_event(data)
    session ="".join(c for c in str(data.get("session_id", "unknown")) if c.isalnum() or c in "-_")[:80]
    path = os.path.join(STATES_DIR, session + ".json")

    if event == "SessionEnd":
        try:
            os.remove(path)
        except OSError:
            pass
        return

    if event == "PermissionRequest" and data.get("permission_mode") == "bypassPermissions":
        return  # approved automatically, nobody is asked; a real prompt also sends a Notification

    if event == "Notification":
        if data.get("notification_type") == "idle_prompt":
            return  # Sirena times her own nap; this reminder would only restart the clock
        state = "needs_you"
    else:
        state = EVENT_STATE.get(event)
    if not state:
        return

    cwd = data.get("cwd") or ""
    record = {
        "state": state,
        "event": event,
        "project": os.path.basename(cwd.rstrip("\\/")) or "Claude",
        "ts": time.time(),
    }
    os.makedirs(STATES_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(tmp, path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
