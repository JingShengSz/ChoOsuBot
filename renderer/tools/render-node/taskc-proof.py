#!/usr/bin/env python
"""Prove the Task C gate with AstrBot's OWN check_admin_permission(), driven by the SAME
config the running bot reads. No message is sent anywhere.

Run: /opt/astrbot/.venv/bin/python /tmp/taskc-proof.py
"""
import json
import sys

sys.path.insert(0, "/opt/astrbot")

from astrbot.core.tools.computer_tools.util import check_admin_permission

CFG = json.load(open("/opt/astrbot/data/cmd_config.json", encoding="utf-8-sig"))
PS = CFG["provider_settings"]

print(f"provider_settings.computer_use_runtime       = {PS.get('computer_use_runtime')!r}")
print(f"provider_settings.computer_use_require_admin = {PS.get('computer_use_require_admin')!r}")
print(f"admins_id                                    = {CFG.get('admins_id')}")
print()


class PluginCtx:
    """Stands in for the AstrBot plugin Context; returns the real config."""

    def get_config(self, umo=None):
        return {"provider_settings": PS}


class Event:
    def __init__(self, role, sender_id):
        self.role = role
        self._sid = sender_id
        self.unified_msg_origin = "llbot:GroupMessage:0_0"

    def get_sender_id(self):
        return self._sid


class AgentCtx:
    def __init__(self, role, sender_id):
        self.context = PluginCtx()
        self.event = Event(role, sender_id)


class Wrapper:
    """Stands in for ContextWrapper[AstrAgentContext]."""

    def __init__(self, role, sender_id):
        self.context = AgentCtx(role, sender_id)


failures = []


def probe(label, role, op, expect_denied):
    err = check_admin_permission(Wrapper(role, "2896448692"), op)
    denied = err is not None
    ok = denied == expect_denied
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"         role={role!r} -> {'DENIED' if denied else 'allowed'}")
    if denied:
        print(f"         message: {err[:150]}...")
    if not ok:
        failures.append(label)
    return err


print("=== the gate, as AstrBot itself applies it to every call ===")
probe("ordinary group member + shell  -> DENIED", "member", "Shell execution", True)
probe("ordinary group member + python -> DENIED", "member", "Python execution", True)
probe("ordinary group member + file   -> DENIED", "member", "File access", True)
probe("admin + shell                  -> ALLOWED", "admin", "Shell execution", False)

# And the same function with the OLD value, to show the change is what does it.
PS_old = dict(PS, computer_use_require_admin=False)
PS_backup = dict(PS)
PS.clear()
PS.update(PS_old)
print("\n=== same call with the PREVIOUS value (require_admin=False) ===")
probe("ordinary group member + shell  -> ALLOWED (the bug)", "member", "Shell execution", False)
PS.clear()
PS.update(PS_backup)

print("\n" + "=" * 70)
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("TASK C GATE PROVEN")
