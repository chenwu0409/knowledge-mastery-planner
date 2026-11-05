"""Derive reproducible confidence and evidence gaps from one normalized evidence snapshot."""
import argparse
import json
import re
from pathlib import Path

LEVELS = {"L1", "L2", "L3", "L4"}
FLAGS = {
    "direct_exam_requirement", "comparable_exam_item", "official_score",
    "independence_recorded", "hints_recorded", "timing_recorded",
    "retest_date_recorded", "unresolved_diagnosis",
}
COUNTS = {"independent_target_attempts", "independent_delayed_retests"}


def assess(snapshot):
    expected = FLAGS | COUNTS | {"scope_status", "target_level", "zsd_id"}
    if snapshot.keys() != expected:
        raise ValueError(f"unexpected or missing evidence keys: {sorted(snapshot.keys() ^ expected)}")
    if snapshot["scope_status"] not in {"confirmed", "provisional", "unknown"}:
        raise ValueError("invalid scope_status")
    zsd_id = snapshot["zsd_id"]
    if not isinstance(zsd_id, str) or not re.fullmatch(r"ZSD-[0-9]+", zsd_id):
        raise ValueError("invalid zsd_id")
    level = snapshot["target_level"]
    if level not in LEVELS | {None}:
        raise ValueError("invalid target_level")
    for key in FLAGS:
        if snapshot[key] is not None and type(snapshot[key]) is not bool:
            raise ValueError(f"{key} must be true, false or null")
    for key in COUNTS:
        if type(snapshot[key]) is not int or snapshot[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if snapshot["independent_target_attempts"] and (
        level is None or not snapshot["independence_recorded"] or not snapshot["hints_recorded"]
    ):
        raise ValueError("independent target attempts require level and independence/hint evidence")
    if snapshot["independent_delayed_retests"] > snapshot["independent_target_attempts"]:
        raise ValueError("delayed retests must be counted among independent target attempts")
    if snapshot["independent_delayed_retests"] and not snapshot["retest_date_recorded"]:
        raise ValueError("delayed retests require a date")

    gaps = []

    def gap(axis, field, blocks, fix, value, blocks_level=None):
        gaps.append({
            "zsd_id": zsd_id, "axis": axis, "field": field,
            "status": "unknown" if value is None else "unresolved" if value is True else "missing",
            "blocks": blocks, "blocks_level": blocks_level, "fix": fix,
        })

    scope = snapshot["scope_status"]
    exam_evidence = snapshot["direct_exam_requirement"] or snapshot["comparable_exam_item"]
    if scope != "confirmed":
        gap("exam_target", "范围状态", "正式范围确认", "补当次考试范围或教师复习提纲",
            None if scope == "unknown" else False)
    if not exam_evidence:
        gap("exam_target", "考试范围确认依据", "目标层级校准",
            "补明确考查要求或可比原卷的小问及解题步骤", exam_evidence, level)
    for key, axis, field, blocks, fix in [
        ("official_score", "score_calibration", "考试成绩库", "分值或失分校准", "补正式成绩或小问得分"),
        ("independence_recorded", "mastery", "是否独立完成", "独立达标认定", "补首次作答的独立性"),
        ("hints_recorded", "mastery", "提示次数", "独立达标认定", "补提示次数与发生步骤，明确零提示"),
        ("timing_recorded", "timing", "作答用时(秒)", "限时达标认定", "补真实作答用时"),
        ("retest_date_recorded", "stability", "最近复测日期", "延迟复测认定", "补实际复测日期及作答"),
    ]:
        if not snapshot[key]:
            gap(axis, field, blocks, fix, snapshot[key], level if axis == "mastery" else None)
    if not snapshot["independent_target_attempts"]:
        gap("mastery", "目标层级独立作答", "当前目标已达成", "收集同层级可核对的首次独立作答",
            False, level)
    if not snapshot["independent_delayed_retests"]:
        gap("stability", "延迟复测证据", "稳定掌握认定", "收集间隔后的同层级独立变式",
            False)
    if snapshot["unresolved_diagnosis"] is not False:
        gap("diagnosis", "错题诊断库", "错因结论", "查阅关联错题并核对首个错误步骤",
            snapshot["unresolved_diagnosis"])

    attempts = snapshot["independent_target_attempts"]
    retests = snapshot["independent_delayed_retests"]
    target = ("high" if scope == "confirmed" and snapshot["direct_exam_requirement"]
              else "medium" if scope != "unknown" and exam_evidence else "low")
    return {
        "evidence_rule_version": 1,
        "scope_status": scope,
        "confidence": {zsd_id: {
            "exam_target": target,
            "mastery": "high" if attempts >= 2 else "medium" if attempts else "unknown",
            "stability": "high" if retests >= 2 else "medium" if retests else "unknown",
        }},
        "evidence_gaps": gaps,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(assess(json.loads(args.snapshot.read_text(encoding="utf-8"))),
                         ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
