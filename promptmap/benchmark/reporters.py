from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def create_run_directory(output_dir: str | None = None) -> Path:
    root = Path(output_dir or os.path.expanduser("~/.promptmap/benchmarks"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / f"{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    with (run_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)


def write_raw_results(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = run_dir / "raw_results.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_aggregate_outputs(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    aggregate = {
        "attack_summary": _attack_summary(rows),
        "objective_summary": _objective_summary(rows),
        "target_summary": _target_summary(rows),
    }
    with (run_dir / "aggregate.json").open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, ensure_ascii=False, default=str)
    _write_csv(run_dir / "attack_summary.csv", aggregate["attack_summary"])
    _write_csv(run_dir / "objective_summary.csv", aggregate["objective_summary"])
    _write_csv(run_dir / "target_summary.csv", aggregate["target_summary"])


def _attack_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["attack_id"]].append(row)
    summary: list[dict[str, Any]] = []
    for attack_id, bucket in sorted(groups.items()):
        summary.append(
            {
                "attack_id": attack_id,
                "registered_name": bucket[0]["registered_name"],
                "display_name": bucket[0]["display_name"],
                "runs": len(bucket),
                "achieved_count": sum(1 for row in bucket if row["achieved"]),
                "success_rate": round(sum(1 for row in bucket if row["achieved"]) / len(bucket), 4),
                "avg_score": round(mean(row["score"] for row in bucket), 4),
                "avg_turns": round(mean(row["turns"] for row in bucket), 4),
            }
        )
    return summary


def _objective_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["objective_id"]].append(row)
    summary: list[dict[str, Any]] = []
    for objective_id, bucket in sorted(groups.items()):
        summary.append(
            {
                "objective_id": objective_id,
                "atlas_technique": bucket[0]["atlas_technique"],
                "prompt_technique": bucket[0]["prompt_technique"],
                "runs": len(bucket),
                "achieved_count": sum(1 for row in bucket if row["achieved"]),
                "success_rate": round(sum(1 for row in bucket if row["achieved"]) / len(bucket), 4),
                "avg_score": round(mean(row["score"] for row in bucket), 4),
                "avg_turns": round(mean(row["turns"] for row in bucket), 4),
            }
        )
    return summary


def _target_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["target_label"]].append(row)
    summary: list[dict[str, Any]] = []
    for target_label, bucket in sorted(groups.items()):
        summary.append(
            {
                "target_label": target_label,
                "runs": len(bucket),
                "achieved_count": sum(1 for row in bucket if row["achieved"]),
                "success_rate": round(sum(1 for row in bucket if row["achieved"]) / len(bucket), 4),
                "avg_score": round(mean(row["score"] for row in bucket), 4),
                "avg_turns": round(mean(row["turns"] for row in bucket), 4),
            }
        )
    return summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
