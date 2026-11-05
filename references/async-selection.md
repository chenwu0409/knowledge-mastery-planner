# 异步搜题交接

适用于已授权的搜题运行。可以由上游当场调用，也可以由用户或已配置的调度稍后指令另一个 Agent 执行。任务进入可搜索状态只表示资料就绪，执行仍以实际指令和授权为准。

## 1. 上游先把任务写完整

将要求写在「训练任务库 → 训练目标」的 `[KMP/plan/v1]` 区块。训练任务关联原 ZSD。RW 由飞书产生。选题端按 RW 或已获授权的日期窗口读取，无需访问此前聊天。

一份可交接的 plan 至少包括稳定 `task_key`、递增 `plan_version`、`horizon`、`purpose`、`scope_key`、`zsd_ids`、`window`、`trigger`、`budget_minutes`、`state`、`search_not_before` 和 `search_request`。仅当搜索要求完整且满足放行条件时写 `state: ready`。`search_not_before` 用带时区的时间，表示最早可以搜题，和孩子实际做题的窗口分开。周、月暂定计划进入执行窗口前保留 `tentative`。以下为虚构示例。

```json
{
  "task_key": "example-math-daily-01",
  "plan_version": 2,
  "horizon": "day",
  "purpose": "迁移",
  "scope_key": "2026-11-midterm-v1",
  "zsd_ids": ["ZSD-000028"],
  "window": {"start": "2026-11-06T19:00:00+08:00", "end": "2026-11-06T19:20:00+08:00"},
  "trigger": "到搜题时间且收到执行指令",
  "budget_minutes": 15,
  "state": "ready",
  "search_not_before": "2026-11-06T12:00:00+08:00",
  "search_request": {
    "region": "广东省广州市",
    "exam_type": "校内期中",
    "grade": "九年级上学期",
    "scope": "已学的二次函数和几何面积",
    "source_priority": ["广州九上期中原题"],
    "allowed_fallback": [],
    "exclude_source_or_models": ["围栏单矩形模型", "以往已经用过的同源题"],
    "requirements": [{
      "zsd_ids": ["ZSD-000028"],
      "exam_target_level": "L3",
      "training_level": "L3",
      "question_type": "解答题",
      "count": 1,
      "minutes": 15,
      "required_actions": ["自行分割或补形", "列面积函数及可行域", "求并验证最值"],
      "keywords": ["二次函数", "面积分割", "割补法", "动点", "最值"],
      "keyword_variants": ["补形", "面积函数"],
      "required_materials": ["完整题干", "几何图", "答案与解析"],
      "exclude_question_ids": []
    }]
  }
}
```

若改动范围、训练层级、来源限制、题量或其他影响交付的要求，递增 `plan_version`，保留原任务键和已发放版本的记录。以当前版本为下一次检索的依据。

## 2. 下游领取、搜题、制作题包并回写

1. 读取 [项目绑定](feishu-project.md) 和 [飞书字段与关联](feishu-sop.md)。校验 RW 未取消，plan 为 `ready`，`search_not_before <= now < window.end`，关联 ZSD 与请求一致。搜题可早于做题窗口的开始时间。用当前版本和批次槽查询「检索与选题记录」，首次默认槽为 `01`。同一批次已发布时回报现有结果，已暂存时恢复该批。没有完整 plan 的旧任务请上游补齐，已有题包仍可独立审核。
2. 按稳定「检索批次ID」先建或续用暂存批次，在「每题评估与淘汰原因」写 `[KMP/selection_result/v1]`，状态为 `staged`。写任务与知识点关联和检索条件。同一批次的写入由一个执行者负责，发现并发或创建结果不明时先按键回读。需要另开一轮重搜时，使用另一个经指令确认的批次槽。
3. 按 search_request 搜题和筛题。将候选及入选题按去重键写入或复用「题目库」，填题干、必要原图、题源、答案、解析、出处和风险。题量不足或无匹配时如实写缺口，遵守已记录的放宽条件。按批次 ID 和版本定位或制作学生版与答案版，分别保存到项目授权位置。学生版保留题面，答案及解析放答案版。保存后将引用写回暂存批次。若工具超时，先按批次标识查找已有成品，再继续写入。按 [飞书 SOP](feishu-sop.md) 填好批次的来源、筛选过程、候选题、最终入选题及结果区块。稳定「检索批次ID」由 task_key、plan_version、批次槽构成，同一次重试沿用。
4. 发布前重读任务版本。版本仍匹配时，将入选 TM 合并进任务「关联题目」，回读链接、题包和结果，再改该批次为 `published`。版本已变化或已取消时，将批次标为 `stale`，保留题目和批次历史供追溯。上游只有在批次已发布且与当前 task_key、plan_version 匹配时，才用其入选清单进行审核。即使版本在回写期间变化，留在 RW 的题目关联也只作为追溯链接。
5. 回报 RW、版本、批次 ID、结果、已选 TM、题包引用及未满足条件。只更新下游拥有的字段，保持 plan、上游审核、作答和掌握证据由上游维护。

`selection_result` 示例。结果状态为 `complete`、`partial` 或 `no_match`。无题时清单为空，仍可发布有原因的检索结果。

```json
{
  "task_id": "RW-示例",
  "task_key": "example-math-daily-01",
  "plan_version": 2,
  "batch_id": "example-math-daily-01-v2-01",
  "status": "published",
  "outcome": "complete",
  "selected_question_ids": ["TM-示例"],
  "student_pack_ref": "<授权飞书学生版入口>",
  "answer_pack_ref": "<授权飞书答案版入口>",
  "gaps": []
}
```

没有可访问的题包引用时，记录缺口。入选清单按小问可补充具体 ZSD、考查层级、预计用时及答案出处。发布表示下游已完成交付或已反馈缺口。上游审核后记录可发小问，实际发出和作答分别留证。

## 3. 上游恢复

从 RW 和当前版本读取已发布批次，无需依赖下游的即时回复。按实际题文、原图、答案和必测动作审核，在「任务复盘」写本次可用小问、退回原因和交付状态。若同一版本出现多个已发布批次，使用任务明确指定的批次，否则先核对再发放。收到孩子作答后，按原发放版本关联到作答记录，再更新知识点掌握证据、迭代后续任务。
