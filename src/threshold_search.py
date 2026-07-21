#!/usr/bin/env python3
"""Bracket and bisect the all-severe fluence threshold on one compute node."""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

import build_threshold_case as builder
import queue_runner as queue


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "threshold_search_status.json"


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_state(**fields) -> None:
    current = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    current.update(fields, updated_at=stamp())
    STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def result(q: int) -> dict | None:
    case_dir = builder.OUTPUT / f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_threshold"
    path = case_dir / "damage_assessment.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_q(node: str, q: int) -> dict:
    case_dir = builder.build(q)
    case_name = case_dir.name
    existing = result(q)
    if existing and existing.get("sim_t_s", 0) >= 1500:
        return existing
    write_state(state="waiting_for_node", node=node, current_Q=q, case=case_name)
    queue.wait_for_idle(node)
    write_state(state="preflight", node=node, current_Q=q, case=case_name)
    if not queue.run_preflight(node, case_name):
        raise RuntimeError(f"Preflight failed for {case_name}")
    write_state(state="running", node=node, current_Q=q, case=case_name)
    if not queue.run_case(node, case_name):
        raise RuntimeError(f"FDS or assessment failed for {case_name}")
    assessed = result(q)
    if not assessed:
        raise RuntimeError(f"Assessment missing for {case_name}")
    return assessed


def search(args: argparse.Namespace) -> None:
    history = []
    high = args.high
    high_result = run_q(args.node, high)
    history.append({"Q": high, "severe": high_result["severe_count"], "all_severe": high_result["all_severe"]})
    low = args.low

    while not high_result["all_severe"]:
        low = high
        if high >= args.max_q:
            write_state(state="no_successful_upper_bound", bracket=[low, None], history=history)
            return
        high = min(args.max_q, int(math.ceil(high * 1.5 / 10.0) * 10))
        high_result = run_q(args.node, high)
        history.append({"Q": high, "severe": high_result["severe_count"], "all_severe": high_result["all_severe"]})
        write_state(state="bracketing", bracket=[low, high], history=history)

    while high - low > args.tolerance:
        midpoint = int(round(((low + high) / 2.0) / args.tolerance) * args.tolerance)
        if midpoint <= low:
            midpoint = low + args.tolerance
        if midpoint >= high:
            break
        assessed = run_q(args.node, midpoint)
        history.append({"Q": midpoint, "severe": assessed["severe_count"], "all_severe": assessed["all_severe"]})
        if assessed["all_severe"]:
            high = midpoint
        else:
            low = midpoint
        write_state(state="bisecting", bracket=[low, high], history=history)

    write_state(state="complete", bracket=[low, high], threshold_upper_J_cm2=high,
                tolerance_J_cm2=args.tolerance, history=history)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node04")
    parser.add_argument("--low", type=int, default=100)
    parser.add_argument("--high", type=int, default=400)
    parser.add_argument("--tolerance", type=int, default=5)
    parser.add_argument("--max-q", type=int, default=1200)
    args = parser.parse_args()

    lock = ROOT / "queue" / f"{args.node}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
    except FileExistsError:
        raise SystemExit(f"Queue already exists for {args.node}")
    try:
        search(args)
    except Exception as exc:
        write_state(state="failed", node=args.node, error=str(exc))
        raise
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
