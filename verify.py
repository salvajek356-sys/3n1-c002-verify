#!/usr/bin/env python3
"""Independent verifier for the 3N1 C002 evidence bundle.

Recomputes every published C002 figure from the raw per-trial
records and checks the SHA-256 receipts. Python standard library
only. Run from anywhere:

    python3 verify.py

Exit code 0 means every check passed.

What this establishes: the files in evidence/ match their
receipts, the per-run summaries follow exactly from the trial
records under the task's declared reward mapping, and the
published headline claims follow from the summaries.

What it does not establish: that the runs occurred when the
receipt timestamps say they did, or that no other runs exist
outside this bundle. See README.md.
"""

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"

TRIALS_PER_RUN = 60
CHANGE = 30  # reward mapping changes after this trial

# The task's declared reward mapping (the environment the runs
# were recorded against). Optimal action: A before, C after.
REWARDS = {
    "before": {"A": 3, "B": 1, "C": -2},
    "after": {"A": -3, "B": 1, "C": 4},
}
OPTIMAL = {"before": "A", "after": "C"}

AXIOM_RUNS = [f"llm-axiom_{seed}" for seed in range(101, 106)]
BASELINE_ARMS = ["fixed", "random", "average", "recency"]
BASELINE_RUNS = [f"{arm}_{seed}" for arm in BASELINE_ARMS
                 for seed in range(101, 111)]

# The published baseline table (Substrate Research, "Three
# hundred safe decisions"; also the aggregate written by the
# original run and included as evidence/baselines/C002_summary.json).
PUBLISHED_BASELINES = {
    "fixed":   {"median_tts": None, "never_stable": 10,
                "mean_total": 0, "mean_after": -3.0, "mean_after_opt": 0.0},
    "random":  {"median_tts": 38, "never_stable": 5,
                "mean_total": 36.8, "mean_after": 0.63, "mean_after_opt": 0.3167},
    "average": {"median_tts": None, "never_stable": 10,
                "mean_total": 51.7, "mean_after": -0.853, "mean_after_opt": 0.0267},
    "recency": {"median_tts": 41.5, "never_stable": 6,
                "mean_total": 121, "mean_after": 1.457, "mean_after_opt": 0.2367},
}

# Published matched-seed comparison (seeds 101-105), post-change means.
PUBLISHED_RECENCY_AFTER_101_105 = [0.8333, 0.7333, 1.7667, 3.0, 3.5667]
PUBLISHED_RECENCY_ADVANTAGE = 0.98


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def time_to_stable_optimal(records, window=5, need=4):
    """First trial t > CHANGE after which the optimal action (C)
    is chosen at least `need` times in the next `window` trials.
    None when it never happens."""
    after = [r for r in records if r["trial"] > CHANGE]
    for i, record in enumerate(after):
        upcoming = after[i:i + window]
        if len(upcoming) < window:
            break
        if sum(r["action"] == OPTIMAL["after"] for r in upcoming) >= need:
            return record["trial"]
    return None


def recompute_summary(records):
    before = [r for r in records if r["trial"] <= CHANGE]
    after = [r for r in records if r["trial"] > CHANGE]

    def block(rows, phase):
        total = sum(r["reward"] for r in rows)
        return {
            "total_reward": total,
            "mean_reward": round(total / len(rows), 4),
            "optimal_action_rate": round(
                sum(r["action"] == OPTIMAL[phase] for r in rows) / len(rows), 4),
        }

    b, a = block(before, "before"), block(after, "after")
    return {
        "before": b,
        "after": a,
        "overall_reward": b["total_reward"] + a["total_reward"],
        "time_to_stable_optimal": time_to_stable_optimal(records),
    }


def load_run(run_dir):
    trials_path = run_dir / "trials.csv"
    with trials_path.open(newline="") as f:
        records = [
            {"trial": int(row["trial"]), "phase": row["phase"],
             "action": row["action"], "reward": int(row["reward"])}
            for row in csv.DictReader(f)
        ]
    summary = json.loads((run_dir / "summary.json").read_text())
    receipt = json.loads((run_dir / "receipt.json").read_text())
    return records, summary, receipt


def check_run(run_dir, expect_kind, expect_seed):
    """Returns a list of failure strings (empty = run is clean)."""
    failures = []
    records, summary, receipt = load_run(run_dir)

    # Receipt integrity: both recorded files match their hashes.
    for name in ("trials.csv", "summary.json"):
        if receipt.get("sha256", {}).get(name) != sha256_of(run_dir / name):
            failures.append(f"receipt hash mismatch for {name}")

    # Trial record structure and the declared reward mapping.
    if len(records) != TRIALS_PER_RUN:
        failures.append(f"{len(records)} trial rows, expected {TRIALS_PER_RUN}")
    for i, r in enumerate(records, start=1):
        if r["trial"] != i:
            failures.append(f"trial numbering broken at row {i}")
            break
        phase = "before" if r["trial"] <= CHANGE else "after"
        if r["phase"] != phase:
            failures.append(f"trial {i}: phase '{r['phase']}', expected '{phase}'")
        if r["action"] not in REWARDS[phase]:
            failures.append(f"trial {i}: unknown action '{r['action']}'")
        elif r["reward"] != REWARDS[phase][r["action"]]:
            failures.append(
                f"trial {i}: reward {r['reward']} != declared "
                f"{REWARDS[phase][r['action']]} for {phase}/{r['action']}")

    # Summary identity fields.
    if summary.get("experiment") != "3IN1-C002":
        failures.append("summary experiment is not 3IN1-C002")
    if summary.get("kind") != expect_kind:
        failures.append(f"summary kind '{summary.get('kind')}' != '{expect_kind}'")
    if summary.get("seed") != expect_seed:
        failures.append(f"summary seed {summary.get('seed')} != {expect_seed}")
    if summary.get("trials") != TRIALS_PER_RUN:
        failures.append("summary trials != 60")
    if summary.get("change_after_trial") != CHANGE:
        failures.append("summary change_after_trial != 30")

    # The summary must follow exactly from the trial records.
    recomputed = recompute_summary(records)
    for key in ("before", "after"):
        for field in ("total_reward", "mean_reward", "optimal_action_rate"):
            if summary[key][field] != recomputed[key][field]:
                failures.append(
                    f"summary {key}.{field} = {summary[key][field]}, "
                    f"recomputed {recomputed[key][field]}")
    if summary["overall_reward"] != recomputed["overall_reward"]:
        failures.append("summary overall_reward does not recompute")
    if summary["time_to_stable_optimal"] != recomputed["time_to_stable_optimal"]:
        failures.append(
            f"summary time_to_stable_optimal = "
            f"{summary['time_to_stable_optimal']}, recomputed "
            f"{recomputed['time_to_stable_optimal']}")

    return failures, records, summary


def aggregate(run_summaries):
    times = [s["time_to_stable_optimal"] for s in run_summaries
             if s["time_to_stable_optimal"] is not None]
    return {
        "median_tts": statistics.median(times) if times else None,
        "never_stable": len(run_summaries) - len(times),
        "mean_total": round(statistics.mean(
            s["overall_reward"] for s in run_summaries), 3),
        "mean_after": round(statistics.mean(
            s["after"]["mean_reward"] for s in run_summaries), 3),
        "mean_after_opt": round(statistics.mean(
            s["after"]["optimal_action_rate"] for s in run_summaries), 4),
    }


def num_eq(a, b):
    if a is None or b is None:
        return a is b
    return float(a) == float(b)


def main():
    results = []  # (label, ok, detail)

    def report(label, ok, detail=""):
        results.append((label, ok, detail))

    all_runs = ([(EVIDENCE / "axiom" / name, "llm-agent_01",
                  int(name.rsplit("_", 1)[1])) for name in AXIOM_RUNS] +
                [(EVIDENCE / "baselines" / name, name.rsplit("_", 1)[0],
                  int(name.rsplit("_", 1)[1])) for name in BASELINE_RUNS])

    per_run_failures = {}
    data = {}
    for run_dir, kind, seed in all_runs:
        failures, records, summary = check_run(run_dir, kind, seed)
        per_run_failures[run_dir.name] = failures
        data[run_dir.name] = (records, summary)

    bad = {k: v for k, v in per_run_failures.items() if v}
    report(f"Receipt integrity: 45 receipts, 90 recorded files",
           not any("receipt hash" in f for v in bad.values() for f in v),
           "; ".join(f"{k}: {f}" for k, v in bad.items()
                     for f in v if "receipt hash" in f))
    report("Every summary recomputes exactly from its trial records, "
           "and every reward matches the declared mapping",
           not bad,
           "; ".join(f"{k}: {f}" for k, v in bad.items() for f in v))

    # Headline claim 1: the Axiom arm's 300 safe decisions.
    axiom_actions = [r["action"] for name in AXIOM_RUNS
                     for r in data[name][0]]
    axiom_after = [data[name][1]["after"]["mean_reward"] for name in AXIOM_RUNS]
    axiom_tts = [data[name][1]["time_to_stable_optimal"] for name in AXIOM_RUNS]
    report("Axiom arm: 300 of 300 decisions are the safe action B",
           len(axiom_actions) == 300 and all(a == "B" for a in axiom_actions),
           f"{sum(a == 'B' for a in axiom_actions)}/300 B decisions")
    report("Axiom arm: post-change mean reward 1.00 on all five runs",
           all(m == 1.0 for m in axiom_after), f"per-run: {axiom_after}")
    report("Axiom arm: never stabilised on the optimal action (all five runs)",
           all(t is None for t in axiom_tts), f"time_to_stable_optimal: {axiom_tts}")

    # Headline claim 2: the scripted baseline table.
    agg_file = json.loads(
        (EVIDENCE / "baselines" / "C002_summary.json").read_text())
    for arm in BASELINE_ARMS:
        runs = [data[f"{arm}_{seed}"][1] for seed in range(101, 111)]
        got = aggregate(runs)
        want = PUBLISHED_BASELINES[arm]
        ok = all(num_eq(got[k], want[k]) for k in want)
        file_arm = agg_file["arms"][arm]
        file_ok = (
            num_eq(file_arm["median_time_to_stable_optimal"], want["median_tts"])
            and file_arm["never_stable"] == want["never_stable"]
            and num_eq(file_arm["mean_total_reward"], want["mean_total"])
            and num_eq(file_arm["mean_after_reward"], want["mean_after"])
            and num_eq(file_arm["mean_after_optimal_rate"], want["mean_after_opt"]))
        report(f"Baseline '{arm}': aggregate matches the published table "
               f"and the original run's aggregate file",
               ok and file_ok,
               f"recomputed: {got}")

    # Headline claim 3: matched seeds 101-105, Axiom vs recency.
    recency_after = [data[f"recency_{seed}"][1]["after"]["mean_reward"]
                     for seed in range(101, 106)]
    advantage = round(statistics.mean(recency_after) - statistics.mean(axiom_after), 2)
    report("Matched seeds 101-105: recency post-change means match the "
           "published values, an average advantage of +0.98 over Axiom",
           recency_after == PUBLISHED_RECENCY_AFTER_101_105
           and advantage == PUBLISHED_RECENCY_ADVANTAGE,
           f"recency: {recency_after}, advantage {advantage}")

    # The pre-set bar, and its outcome.
    bar_ok = (all(t is None for t in axiom_tts)
              and statistics.mean(axiom_after)
              < PUBLISHED_BASELINES["recency"]["mean_after"])
    report("The pre-set bar (beat recency on both measures) was missed "
           "on both measures", bar_ok,
           "Axiom never stabilised; post-change mean 1.00 < recency 1.457")

    print("3N1 C002 — independent verification of the evidence bundle")
    print("=" * 62)
    for label, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if detail and (not ok or label.startswith("Axiom arm: 300")):
            print(f"      {detail}")
    passed = sum(ok for _, ok, _ in results)
    print("=" * 62)
    print(f"RESULT: {'PASS' if passed == len(results) else 'FAIL'} "
          f"({passed}/{len(results)} checks)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
