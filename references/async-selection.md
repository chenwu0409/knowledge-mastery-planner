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

## 2. 下游搜题，先交候选

1. 按 [项目绑定](feishu-project.md) 读取 RW、当前 plan 及关联 ZSD。校验任务未取消、plan 为 `ready`、`search_not_before <= now < window.end`、关联知识点与要求一致。首次批次槽为 `01`。先按稳定「检索批次ID」建或续用批次，重试先回读。同一个批次由一个执行者写入。
2. 按 `search_request` 搜题、筛题，把候选的题干、图表、来源、标准答案、解析及风险写入或去重关联到题目库。按 [飞书 SOP](feishu-sop.md) 在「检索与选题记录」写筛选过程及 RW／ZSD／候选题链接。「最终入选题」等待上游放行后再由下游写入。
3. 在「每题评估与淘汰原因」保存 `[KMP/selection_result/v1]`。处理中的状态为 `staged`。回读候选题、链接并核对当前版本后改为 `published`，表示候选已可供上游验收。版本已变化或任务已取消时记为 `stale`。RW 的「关联题目」用于追溯，不能代替放行记录。
4. 候选批次落库后，Agent 在同一轮立即调用上游验收，传 RW、plan_version 和 batch_id。若上游暂时不可用，保留已发布候选并回报「待上游验收」。恢复时用这三个值继续。候选阶段截止于验收交接。

```json
{
  "task_id": "RW-示例",
  "task_key": "example-math-daily-01",
  "plan_version": 2,
  "batch_id": "example-math-daily-01-v2-01",
  "status": "published",
  "outcome": "complete",
  "candidate_question_ids": ["TM-示例"],
  "gaps": []
}
```

`outcome` 为 `complete`、`partial` 或 `no_match`，表示下游初筛结果。无题时清单为空，仍要写缺口交给上游。批次键由 task_key、plan_version 和批次槽组成。重试同一轮时使用原键。

## 3. 上游验收，放行或退回

1. 重读当前 plan、指定的已发布批次和题目记录，按 [验收要求](assessment-and-handoff.md#候选题与题包验收) 逐题逐小问核对原图、答案、实际考查层级、必测动作、来源限制、重复与时间。此前已核验的题若纳入补搜批次，复核题文未变化且仍符合本轮计划。
2. 把决定写入「训练任务库 → 任务复盘」的 `[KMP/delivery/v1]`，按计划版本与批次保留历史。上游同时写唯一的 `active_review` 指向当前 plan_version、batch_id 与 review_revision。新验收或退回取代旧指针，已被替代的放行只作历史。写 `plan_version`、`batch_id`、`review_revision`、`status`、审核理由及缺口。只有拟入包的每道题或小问均通过、且整组满足当前搜索要求时，才记 `approved_for_pack`。同时保存 `approved_items`，逐项列 TM、允许的小问及受审内容指纹或可核对的题文版本。被排除的冗余候选无需通过。
3. 条件未满足时记 `needs_research`，逐条写不通过题号、未满足的要求、修正搜索词或筛选条件，以及可保留的小问。在原计划约束内补搜时，Agent 把退回记录交给下游，另开稳定批次槽，记录 `supersedes_batch_id` 并关联本轮保留和替换的候选，回到第 2 节。改变难度、题源边界、题量等任务要求时由上游更新 plan_version，再开启新版本批次。默认同一轮执行最多立即补搜一次，之后将缺口留给下一次明确指令或既定重试规则。

## 4. 下游凭放行记录制作题包

1. 收到放行指令后重读 RW，确认当前版本、批次、`review_revision` 与 `active_review` 指向的 `approved_for_pack` 相符，题文和附件仍与审过的版本一致。按 `approved_items` 制作学生版与答案版，学生版仅含可发题面。成品先暂存在项目授权的工作位置。若获批小问无法保留必要图文并安全独立呈现，退回上游换题或重审。条件不符则回到上游验收。
2. 把放行清单对应的 TM 写入该批次「最终入选题」并合并到任务「关联题目」。在同一批次的「每题评估与淘汰原因」另写 `[KMP/pack_result/v1]`，记录 RW、plan_version、batch_id、review_revision、所用 TM 和小问、学生版及答案版引用、生成状态。用批次键与验收版本定位已有产物，超时先查找再续作。记录已生成前回读题包、链接和放行记录。计划或放行变化时将产物标记为过期并停止交付。
3. Agent 核对成品顺序、图表、公式、最后一题和答案隔离，提供任何成品链接前，最后回读同一 RW、plan_version、batch_id、review_revision 和 `active_review`，确认仍然有效，再反馈上游或用户。已过期或被替代的版本停止发放。上游在 delivery 中记成品验收及实际发出证据。旧记录即使有题包链接，也须有本轮放行证据才可用于本轮新发放。

## 5. 作答后重新进入计划

孩子可晚些作答。收到作答后由 Agent 调用上游，按原发放版本和小问写入作答、诊断与掌握证据，再更新日、周、月计划。未来计划进入可搜窗口后，Agent 依指令启动新一轮。同步环节是候选落库后立即交叉验收与放行，未来任务领取及作答回收可以异步。
