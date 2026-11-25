"""Adds (or with --remove, takes out) Sirena's hooks in ~/.claude/settings.json.

Safe to run twice: entries are recognised by the sirena_hook.py path and never
duplicated. Other hooks are left untouched. A backup is written first.
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
HOOK = os.path.join(HERE, "sirena_hook.py").replace("\\", "/")
COMMAND = f'"{sys.executable.replace(chr(92), "/")}" "{HOOK}"'
EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
          "SubagentStart", "PermissionRequest", "Notification", "Stop", "StopFailure", "SessionEnd"]


def is_sirena(group):
    return any("sirena_hook.py" in h.get("command", "") for h in group.get("hooks", []))


def main():
    remove = "--remove" in sys.argv
    with open(SETTINGS, encoding="utf-8") as f:
        settings = json.load(f)
    backup = SETTINGS + time.strftime(".bak-sirena-%Y%m%d-%H%M%S")
    n = 1
    while os.path.exists(backup):
        backup = f"{SETTINGS}.bak-sirena-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    shutil.copy2(SETTINGS, backup)

    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        groups = [g for g in hooks.get(event, []) if not is_sirena(g)]
        if not remove:
            groups.append({"hooks": [{"type": "command", "command": COMMAND, "timeout": 5, "async": True}]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)

    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, SETTINGS)
    print(("Removed" if remove else "Installed") + f" Sirena hooks for {len(EVENTS)} events.")


if __name__ == "__main__":
    main()
