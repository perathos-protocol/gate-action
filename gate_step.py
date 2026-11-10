"""Ask Perathos Gate for a passkey approval of this workflow run, verify and keep the receipt.

Run by action.yml. Exit 0 only when a pinned approver approved exactly this run.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# An empty, private home: the runner must not pick up a perathos config from anywhere else.
home = Path(os.environ.get("IN_HOME") or ".perathos-home").resolve()
home.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)

from perathos.gate import ApprovalDenied, ApprovalTimeout, GateError, require_approval  # noqa: E402


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def annotate(level: str, message: str) -> None:
    # Workflow commands end at the first newline; keep messages to one line.
    print(f"::{level}::{' '.join(message.split())}", flush=True)


def write_lines(env_file: str, lines: list[str]) -> None:
    path = os.environ.get(env_file)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def cell(text: str) -> str:
    """Text made safe for one Markdown table cell."""
    return " ".join(str(text).split()).replace("|", "/").replace("`", "'").replace("<", "(").replace(">", ")")


def bounded(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(env(name, str(default)))))
    except ValueError:
        return default


def main() -> int:
    # The approval is bound to these values through args_hash: an approval given for one
    # commit, run or attempt cannot be replayed for another.
    run = {key: env(var) for key, var in (
        ("repository", "GITHUB_REPOSITORY"), ("sha", "GITHUB_SHA"), ("ref", "GITHUB_REF"),
        ("workflow", "GITHUB_WORKFLOW"), ("job", "GITHUB_JOB"), ("run_id", "GITHUB_RUN_ID"),
        ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("actor", "GITHUB_ACTOR"), ("event", "GITHUB_EVENT_NAME"))}
    summary = env("IN_SUMMARY")
    if not summary:
        annotate("error", "Perathos Gate: the 'summary' input is empty")
        return 2
    detail = env("IN_DETAIL") or (
        f"{run['repository']} at {run['sha'][:12]} ({run['ref']}), workflow '{run['workflow']}' "
        f"run {run['run_id']} attempt {run['run_attempt']}, started by {run['actor']}")
    if not env("PERATHOS_GATE_APPROVERS"):
        annotate("warning", "Perathos Gate: no approver keys are pinned (input 'approver-keys'), so the Gate "
                            "server decides who counts as an approver")

    def created(request: dict) -> None:
        # The approve link carries a token and this log may be public: approvers get it by notification.
        print(f"Perathos Gate: waiting for approval of {request['id']} (link not shown; "
              f"approvers are notified by the Gate)", flush=True)

    try:
        receipt = require_approval(
            summary, tool="github-actions", args={"summary": summary, "run": run},
            target=env("IN_TARGET") or None, detail=detail, agent="github-actions",
            session_id=f"{run['repository']}/{run['run_id']}/{run['run_attempt']}",
            wait_seconds=bounded("IN_WAIT", 900, 1, 3600), ttl_seconds=bounded("IN_TTL", 1800, 60, 3600),
            on_created=created)
    except ApprovalDenied as exc:
        annotate("error", f"Perathos Gate: {exc}")
        write_lines("GITHUB_STEP_SUMMARY", ["### Perathos Gate: denied", "", str(exc)])
        return 1
    except ApprovalTimeout as exc:
        annotate("error", f"Perathos Gate: no decision in time. {exc}")
        write_lines("GITHUB_STEP_SUMMARY", ["### Perathos Gate: no decision in time"])
        return 1
    except GateError as exc:
        annotate("error", f"Perathos Gate: {exc}")
        return 1

    path = Path(env("IN_RECEIPT", "perathos-approval-receipt.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    approver = " ".join(str(receipt["approver"].get("name", "")).split())
    pinned = bool(env("PERATHOS_GATE_APPROVERS"))
    print(f"Perathos Gate: APPROVED by {approver} at {receipt['decided_at']} (passkey, user verified)", flush=True)
    write_lines("GITHUB_OUTPUT", [f"receipt_path={path}", f"receipt_hash={receipt['receipt_hash']}",
                                  f"approver={approver}"])
    write_lines("GITHUB_STEP_SUMMARY", [
        "### Perathos Gate: approved", "",
        "| | |", "|---|---|",
        f"| Action | {cell(summary)} |",
        f"| Approved by | {cell(approver)} ({'pinned passkey' if pinned else 'passkey NOT pinned'}) |",
        f"| Decided at | {receipt['decided_at']} |",
        f"| Bound to | `{run['repository']}` at `{run['sha'][:12]}`, run {run['run_id']} attempt {run['run_attempt']} |",
        f"| Receipt hash | `{receipt['receipt_hash']}` |", "",
        "The receipt is attached to this run as an artifact. Check it offline with "
        "`perathos gate verify <file> --gate-key <key>`.",
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
