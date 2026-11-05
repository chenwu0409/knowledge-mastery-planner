"""Validate new KMP plan and review writes before using them as a release gate."""
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas/kmp-v1.json").read_text(encoding="utf-8"))
GATE_KEYS = ("plan_version", "batch_id", "review_revision")


def validate_shape(kind, document):
    schema = {**SCHEMA, "$ref": f"#/$defs/{kind}"}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


def validate_plan(plan):
    validate_shape("plan", plan)
    points = set(plan["zsd_ids"])
    if set(plan["confidence"]) != points or set(plan["evidence_refs"]) != points or any(
        gap["zsd_id"] not in points for gap in plan["evidence_gaps"]
    ):
        raise ValueError("evidence does not match the task knowledge points")
    if plan["provisional_pack_authorized"] and (
        plan["scope_status"] != "provisional" or not plan.get("provisional_authorization_ref")
    ):
        raise ValueError("provisional packaging requires an explicit authorization reference")
    if plan["state"] != "ready":
        return
    if any(plan[key] is None for key in ("window", "search_not_before", "budget_minutes", "search_request")):
        raise ValueError("ready plan lacks executable search conditions")
    parse = datetime.fromisoformat
    start, end = (parse(plan["window"][key]) for key in ("start", "end"))
    if not (start < end and parse(plan["search_not_before"]) < end):
        raise ValueError("invalid search or training window")
    requirements = plan["search_request"]["requirements"]
    if len({req["requirement_id"] for req in requirements}) != len(requirements):
        raise ValueError("duplicate requirement ID")
    if {zsd for req in requirements for zsd in req["zsd_ids"]} != points:
        raise ValueError("requirements do not cover the plan knowledge points")
    if sum(req["minutes"] for req in requirements) > plan["budget_minutes"]:
        raise ValueError("requirements exceed the planned budget")
    for requirement in requirements:
        actions = requirement["required_actions"]
        if len({action["id"] for action in actions}) != len(actions) or not any(a["required"] for a in actions):
            raise ValueError("each requirement needs unique action IDs and at least one mandatory action")


def validate_delivery(plan, delivery, batch, previous=None, *, for_release=False):
    validate_plan(plan)
    validate_shape("delivery", delivery)
    gate = {key: delivery[key] for key in GATE_KEYS}
    if gate != delivery["active_review"] or delivery["batch_id"] != batch.get("batch_id"):
        raise ValueError("review is not the active batch and revision")
    if plan["state"] != "ready" or delivery["plan_version"] != plan["plan_version"] or (
        delivery["scope_status"], delivery["scope_key"]
    ) != (plan["scope_status"], plan["scope_key"]):
        raise ValueError("review scope or plan version is stale")
    if batch.get("status") != "published" or any(batch.get(key) != value for key, value in {
        "task_id": delivery["task_id"], "task_key": plan["task_key"], "plan_version": plan["plan_version"],
    }.items()):
        raise ValueError("candidate batch is not published for this task and version")
    if previous is not None and previous != delivery:
        if previous["task_id"] != delivery["task_id"] or delivery["review_revision"] != previous["review_revision"] + 1:
            raise ValueError("review revision must advance exactly once for this task")
        if previous["plan_version"] == delivery["plan_version"] and previous["batch_id"] != delivery["batch_id"]:
            if batch.get("supersedes_batch_id") != previous["batch_id"]:
                raise ValueError("candidate batch is not the active review's authorized successor")
    elif previous is None and not for_release and delivery["review_revision"] != 1:
        raise ValueError("first review revision must be 1")

    status = delivery["status"]
    if for_release and status != "approved_for_pack":
        raise ValueError("review has not released a pack")
    if status != "approved_for_pack":
        if delivery["approved_items"] or not delivery["gaps"]:
            raise ValueError("a held or returned review must explain gaps and release no items")
        if status == "needs_research" and not delivery["research_instructions"]:
            raise ValueError("a returned review needs actionable search instructions")
        return
    if delivery["gaps"] or delivery["research_instructions"]:
        raise ValueError("approval has unresolved gaps")
    if plan["scope_status"] != "confirmed" and not plan["provisional_pack_authorized"]:
        raise ValueError("scope does not authorize packaging")

    candidates = set(batch.get("candidate_question_ids", []))
    requirements = {req["requirement_id"]: req for req in plan["search_request"]["requirements"]}
    seen = set()
    counts = Counter()
    for item in delivery["approved_items"]:
        qid = item["question_id"]
        requirement = requirements.get(item["requirement_id"])
        if not requirement or qid not in candidates or qid in seen:
            raise ValueError("approved item must be a unique candidate assigned to a requirement")
        if item["actual_level"] != requirement["training_level"] or qid in requirement["exclude_question_ids"]:
            raise ValueError("approved item has the wrong level or is excluded")
        seen.add(qid)
        counts[item["requirement_id"]] += 1
        actions = {action["id"]: action["required"] for action in requirement["required_actions"]}
        results = {result["id"]: result["result"] for result in item["action_results"]}
        if len(results) != len(item["action_results"]) or actions.keys() != results.keys() or any(
            mandatory and results[key] != "pass" for key, mandatory in actions.items()
        ):
            raise ValueError("approved item lacks passing evidence for mandatory actions")
    if counts != Counter({key: req["count"] for key, req in requirements.items()}):
        raise ValueError("approved items do not satisfy the requested counts")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--delivery", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--previous", type=Path, help="current persisted delivery before a new review write")
    parser.add_argument("--release", action="store_true", help="check the persisted current gate for packaging")
    args = parser.parse_args()
    try:
        plan = read(args.plan)
        if args.delivery and args.batch:
            if args.release and args.previous:
                parser.error("--release reads the current gate, not a proposed transition")
            validate_delivery(plan, read(args.delivery), read(args.batch),
                              read(args.previous) if args.previous else None, for_release=args.release)
        elif args.delivery or args.batch or args.previous or args.release:
            parser.error("delivery operations require both --delivery and --batch")
        else:
            validate_plan(plan)
        print("KMP contract valid")
    except (OSError, ValueError, ValidationError) as error:
        parser.exit(1, f"{error}\n")
