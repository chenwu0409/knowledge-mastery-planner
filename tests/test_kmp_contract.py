import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evidence_preflight import assess
from validate_contract import validate_delivery, validate_plan, ValidationError


class GateTest(unittest.TestCase):
    def setUp(self):
        docs = (ROOT / "references/async-selection.md").read_text(encoding="utf-8")
        self.plan = json.loads(re.search(r"```json\n(.*?)\n```", docs, re.S).group(1))
        self.plan["zsd_ids"] = ["ZSD-000036"]
        self.plan["confidence"] = {"ZSD-000036": {"exam_target": "medium", "mastery": "unknown", "stability": "unknown"}}
        self.plan["evidence_gaps"] = []
        self.plan["evidence_refs"] = {"ZSD-000036": ["fixture school evidence"]}
        req = self.plan["search_request"]["requirements"][0]
        req.update(zsd_ids=self.plan["zsd_ids"], exam_target_level="L2", training_level="L2",
                   question_type="作图题", count=2, required_actions=[
                       {"id": "pivot", "criterion": "识别支点", "required": True},
                       {"id": "arm", "criterion": "在变式中作力臂垂线", "required": True}])
        self.b01 = {"task_id": "RW-000001", "task_key": self.plan["task_key"], "plan_version": 2,
                    "batch_id": "B01", "status": "published", "candidate_question_ids": ["TM-000001", "TM-000002"]}
        self.b02 = dict(self.b01, batch_id="B02", supersedes_batch_id="B01",
                        candidate_question_ids=["TM-000001", "TM-000003"])
        self.checks = [dict(item=item, result="pass", evidence="见候选记录")
                       for item in ("必测动作", "难度档", "配图", "答案可验算", "去重键", "科目配比")]
        self.reject = dict(task_id="RW-000001", plan_version=2, batch_id="B01", review_revision=1,
                           scope_key=self.plan["scope_key"], scope_status="confirmed",
                           status="needs_research", reason="缺另一种作用线情境",
                           active_review=dict(plan_version=2, batch_id="B01", review_revision=1),
                           gaps=["第二题重复"], research_instructions=["搜索斜向作用线"], approved_items=[],
                           checks=self.checks)
        self.approve = dict(self.reject, batch_id="B02", review_revision=2, status="approved_for_pack",
                            reason="两题均满足要求", gaps=[], research_instructions=[],
                            active_review=dict(plan_version=2, batch_id="B02", review_revision=2),
                            approved_items=[
                                dict(question_id=qid, subitems=["1"], requirement_id="R1", actual_level="L2",
                                     content_ref="fixture-v1", action_results=[
                                         dict(id=action, result="pass", evidence="见小问1")
                                         for action in ("pivot", "arm")])
                                for qid in self.b02["candidate_question_ids"]])

    def test_return_replace_and_replay(self):
        validate_delivery(self.plan, self.reject, self.b01)
        validate_delivery(self.plan, self.approve, self.b02, self.reject)
        validate_delivery(self.plan, self.approve, self.b02, self.approve)
        validate_delivery(self.plan, self.approve, self.b02, for_release=True)
        replay = dict(self.reject, review_revision=3, active_review=dict(self.reject["active_review"], review_revision=3))
        with self.assertRaisesRegex(ValueError, "authorized successor"):
            validate_delivery(self.plan, replay, self.b01, self.approve)
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_delivery(dict(self.plan, plan_version=3), self.approve, self.b02, for_release=True)

    def test_legacy_delivery_is_marked_not_rejected(self):
        legacy = {key: value for key, value in self.approve.items() if key != "checks"}
        self.assertIsNone(validate_delivery(self.plan, self.approve, self.b02, for_release=True))
        self.assertEqual(validate_delivery(self.plan, legacy, self.b02, for_release=True),
                         {"legacy_no_checks": True})
        with self.assertRaisesRegex(ValueError, "six checks"):
            validate_delivery(self.plan, legacy, self.b02)

    def test_missing_action_and_provisional(self):
        incomplete = copy.deepcopy(self.approve)
        incomplete["approved_items"][0]["action_results"][0]["result"] = "unknown"
        with self.assertRaisesRegex(ValueError, "mandatory actions"):
            validate_delivery(self.plan, incomplete, self.b02, for_release=True)
        plan = dict(self.plan, scope_status="provisional")
        provisional = dict(self.approve, scope_status="provisional")
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            validate_delivery(plan, provisional, self.b02, for_release=True)
        plan.update(provisional_pack_authorized=True, provisional_authorization_ref="fixture-user-approval")
        validate_delivery(plan, provisional, self.b02, for_release=True)

    def test_strict_fields(self):
        with self.assertRaises(ValidationError):
            validate_plan(dict(self.plan, plan_versoin=2))

    def test_missing_scores_do_not_change_target(self):
        evidence = dict(zsd_id="ZSD-000036", scope_status="confirmed", target_level="L2",
                        direct_exam_requirement=True, comparable_exam_item=True, official_score=False,
                        independence_recorded=None, hints_recorded=None, timing_recorded=None,
                        retest_date_recorded=False, unresolved_diagnosis=True,
                        independent_target_attempts=0, independent_delayed_retests=0)
        result = assess(evidence)
        self.assertEqual(result["confidence"][evidence["zsd_id"]],
                         {"exam_target": "high", "mastery": "unknown", "stability": "unknown"})
        self.assertIn("unresolved", {gap["status"] for gap in result["evidence_gaps"]})
        self.assertEqual(assess(dict(evidence, official_score=True))["confidence"], result["confidence"])
