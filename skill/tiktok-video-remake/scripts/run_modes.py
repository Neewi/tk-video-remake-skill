"""Canonical run modes and delivery plans for TikTok remake jobs."""

from __future__ import annotations


REVIEW_INCREMENTAL = "REVIEW_INCREMENTAL"
DIRECT_BATCH = "DIRECT_BATCH"
BATCH_SCRIPT_IDS = ("BASE", "V01", "V02", "V03", "V04", "V05")

MODE_ALIASES = {
    "review": REVIEW_INCREMENTAL,
    "incremental": REVIEW_INCREMENTAL,
    REVIEW_INCREMENTAL.casefold(): REVIEW_INCREMENTAL,
    "batch": DIRECT_BATCH,
    "direct": DIRECT_BATCH,
    DIRECT_BATCH.casefold(): DIRECT_BATCH,
}


def normalize_run_mode(value: str | None) -> str:
    key = str(value or "review").strip().casefold()
    try:
        return MODE_ALIASES[key]
    except KeyError as exc:
        raise ValueError("mode 必须是 review 或 batch") from exc


def delivery_plan(mode: str) -> list[str]:
    return list(BATCH_SCRIPT_IDS) if mode == DIRECT_BATCH else []
