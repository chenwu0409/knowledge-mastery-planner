# 异步搜题交接

适用于已授权的搜题运行。可以由上游当场调用，也可以由用户或已配置的调度稍后指令另一个 Agent 执行。任务进入可搜索状态只表示资料就绪，执行仍以实际指令和授权为准。

## 契约校验

新写入的计划和验收采用 [KMP v1 schema](../schemas/kmp-v1.json)。在本地用 `python scripts/validate_contract.py plan.json` 校验。校验器依赖 `jsonschema>=4,<5`，可在隔离环境安装。写新验收加 `--delivery delivery.json --batch batch.json`，已有验收时必须加 `--previous current-delivery.json`，并在写前重读当前指针。制卷及发放前对飞书当前验收加 `--release` 校验，再比对实际待用题文和附件。若输入不匹配，保留待复核状态。历史计划可只读，旧结构进入新一轮制卷前由上游补齐并复验。

## 1. 上游先把任务写完整

将要求写在「训练任务库 → 训练目标」的 `[KMP/plan/v1]` 区块。训练任务关联原 ZSD。RW 由飞书产生。选题端按 RW 或已获授权的日期窗口读取，无需访问此前聊天。

新计划带稳定任务键、计划版本、范围状态、目标及搜索条件。按 [证据检查](evidence-preflight.md) 汇总每个 ZSD 的 confidence、evidence_refs 和 evidence_gaps。任务的 `minutes` 是该项要求所有题的总预算；同一任务的补搜轮次上限写在 `research_round_limit`，默认 2。每条 requirement 必须显式写 `required_actions`（带 ID 的可观察判定项），不得留空或用 ZSD 代理编号代替；并按 `image_requirement` 标 `required`（必需图）/ `illustrative`（示意图）/ `none`（无需图）。仅当搜索要求完整且满足放行条件时写 `state: ready`。`search_not_before` 用带时区的时间，表示最早可以搜题，和孩子实际做题的窗口分开。周、月暂定计划进入执行窗口前保留 `tentative`。以下为虚构示例。

```json
{
  "task_key": "example-math-daily-01",
  "plan_version": 2,
  "horizon": "day",
  "purpose": "迁移",
  "scope_key": "2026-11-midterm-v1",
  "zsd_ids": [
    "ZSD-000028"
  ],
  "window": {
    "start": "2026-11-06T19:00:00+08:00",
    "end": "2026-11-06T19:20:00+08:00"
  },
  "trigger": "到搜题时间且收到执行指令",
  "budget_minutes": 15,
  "state": "ready",
  "search_not_before": "2026-11-06T12:00:00+08:00",
  "search_request": {
    "region": "广东省广州市",
    "exam_type": "校内期中",
    "grade": "九年级上学期",
    "scope": "已学的二次函数和几何面积",
    "source_priority": [
      "广州九上期中原题"
    ],
    "allowed_fallback": [],
    "exclude_source_or_models": [
      "围栏单矩形模型",
      "以往已经用过的同源题"
    ],
    "requirements": [
      {
        "zsd_ids": [
          "ZSD-000028"
        ],
        "exam_target_level": "L3",
        "training_level": "L3",
        "question_type": "解答题",
        "count": 1,
        "minutes": 15,
        "required_actions": [
          {
            "id": "a1",
            "criterion": "自行分割或补形",
            "required": true
          },
          {
            "id": "a2",
            "criterion": "列面积函数及可行域",
            "required": true
          },
          {
            "id": "a3",
            "criterion": "求并验证最值",
            "required": true
          }
        ],
        "keywords": [
          "二次函数",
          "面积分割",
          "割补法",
          "动点",
          "最值"
        ],
        "keyword_variants": [
          "补形",
          "面积函数"
        ],
        "required_materials": [
          "完整题干",
          "几何图",
          "答案与解析"
        ],
        "image_requirement": "required",
        "exclude_question_ids": [],
        "requirement_id": "R1"
      }
    ]
  },
  "scope_status": "confirmed",
  "provisional_pack_authorized": false,
  "research_round_limit": 2,
  "evidence_rule_version": 1,
  "confidence": {
    "ZSD-000028": {
      "exam_target": "high",
      "mastery": "unknown",
      "stability": "unknown"
    }
  },
  "evidence_gaps": [
    {
      "zsd_id": "ZSD-000028",
      "axis": "mastery",
      "field": "目标层级独立作答",
      "status": "missing",
      "blocks": "当前目标已达成",
      "blocks_level": "L3",
      "fix": "收集首次独立作答"
    }
  ],
  "evidence_refs": {
    "ZSD-000028": [
      "示例同校原卷与教师范围"
    ]
  }
}
```

若改动范围、训练层级、来源限制、题量或其他影响交付的要求，递增 `plan_version`，保留原任务键和已发放版本的记录。同版补搜只开新批次。重复读取或相同决定重试沿用原审核版本。每次新的验收决定用任务内单调递增的 `review_revision`，它就是审核轮次。

`scope_status: provisional` 默认允许搜候选。经本轮明确授权时，才写 `provisional_pack_authorized: true` 和授权引用，并以暂定范围制卷。题目已合格但范围未放行时写 `scope_hold`。范围不明时保持候选阶段。正式范围到达后比较当前内容，影响交付时升级计划版本、撤销旧的未发放放行并重验；历史题包和作答继续按原版本追溯。审核与成品记下 scope_key 和 scope_status。

## 2. 下游搜题，先交候选

1. 按 [项目绑定](feishu-project.md) 读取 RW、当前 plan 及关联 ZSD。校验任务未取消、plan 为 `ready`、`search_not_before <= now < window.end`、关联知识点与要求一致。首次批次槽为 `01`。先按稳定「检索批次ID」建或续用批次，重试先回读。同一个批次由一个执行者写入。
2. 按 `search_request` 搜题、筛题，把候选逐条写进「选题候选」表（按 `候选ID` 幂等）：题干摘要、图表、来源、标准答案、解析、风险、六项 checks、命中的必测动作与目标层级；状态初始为 `待复核`。候选不写检索记录正文，也不先进题目库。题干截断、图不可读、平台无答案或答案墙导致无法核验时，不标 `已放行`，在批次 `gaps` 写 `needs_evidence` 和具体缺项（题面截断／图不可读／平台无答案／答案墙），退回补题面或换源，不消耗补搜轮次。
3. 在「每题评估与淘汰原因」保存 `[KMP/selection_result/v1]`，候选明细留在「选题候选」表。批次处理中的状态为 `staged`；回读候选、链接并核对当前版本后改为 `published`，表示候选已可供上游验收；候选表状态同步为 `待复核`，上游放行后由下游改为 `已放行`，制卷后改 `已采用`。版本已变化或任务已取消时批次记 `stale`、候选记 `已弃用`。RW 的「关联题目」用于追溯，不能代替放行记录。
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

1. 重读当前 plan、指定的已发布批次和题目记录，按 [验收要求](assessment-and-handoff.md#候选题与题包验收) 逐题逐小问核对原图、答案、实际考查层级、必测动作、来源限制、重复与时间。此前已核验的题若纳入补搜批次，复核题文未变化且仍符合本轮计划。当前计划下已有活跃审核时，只有同批新决定或明确继承该批次的后续批次可更新指针。已被替代的批次只读。题目库与候选记录只有下游写；上游只读，不建 TM、不改题，复核结论以回库回读结果为准，不采信下游自报清单。
2. 把决定写入「训练任务库 → 任务复盘」的 `[KMP/delivery/v1]`，按计划版本与批次保留历史。上游同时写唯一的 `active_review` 指向当前 plan_version、batch_id 与 review_revision。新验收或退回取代旧指针，已被替代的放行只作历史。写 `plan_version`、`batch_id`、`review_revision`、`status`、审核理由及缺口。新制卷同时写必填的 `checks`：必测动作、难度档、配图、答案可验算、去重键、科目配比逐项给 `pass` / `fail` / `unknown` 及证据，禁止「基本符合」「大致达标」这类模糊表述。历史已写入的 delivery 缺 `checks` 不追溯校验，校验器标 `legacy_no_checks: true` 并放行。每个获批项引用 requirement_id，并对 required_actions 的每个动作 ID 写 pass、fail 或 unknown 和小问证据。必测动作全部 pass 才能放行。只有拟入包的每道题或小问均通过、且整组满足当前搜索要求时，才记 `approved_for_pack`。同时保存 `approved_items`，逐项列 TM、允许的小问及受审内容指纹或可核对的题文版本。被排除的冗余候选无需通过。
3. 条件未满足时记 `needs_research`，逐条写不通过题号、未满足的要求、修正搜索词或筛选条件，以及可保留的小问。任务复盘中的当前 delivery 是补搜原因唯一权威，题目侧只留 RW 和批次指针。题目自身的通用缺陷可另记。在原计划约束内补搜时，Agent 把退回记录交给下游，另开稳定批次槽，记录 `supersedes_batch_id` 并关联本轮保留和替换的候选，回到第 2 节。改变难度、题源边界、题量等任务要求时由上游更新 plan_version，再开启新版本批次。补搜上限按 plan 的 `research_round_limit`（默认 2）：未达上限且缺的是「可搜到的合规题」时立即补搜；达到上限仍不满足，按 ① 换情境不换知识点 → ② 换源/补题面 → ③ 上游显式重定目标层级（写 `level_change` 的 from/to/reason 并升 `plan_version`）→ ④ 交人工 的顺序降级，把 `round`、`option`、`reason` 写入 delivery 的 `degradation`。禁止为凑层级把 L3 降到易档，禁止下游自行换到其他 ZSD。

缺的不是题而是证据时（题面截断、图不可读、平台无答案、答案墙），**不进补搜循环**：记 `needs_evidence`，在 `evidence_gaps` 逐条写类型、题号和细节，退回补题面或换源。补件后重跑复核；仍缺则交用户确认。`needs_evidence` 既不消耗 `research_round_limit`，也不触发 `degradation`。

## 4. 下游凭放行记录制作题包

1. 收到放行指令后重读 RW，确认当前版本、批次、`review_revision` 与 `active_review` 指向的 `approved_for_pack` 相符，题文和附件仍与审过的版本一致。按 `approved_items` 制作学生版与答案版，学生版仅含可发题面。成品先暂存在项目授权的工作位置。若获批小问无法保留必要图文并安全独立呈现，退回上游换题或重审。条件不符则回到上游验收。
2. 把放行清单对应的 TM 写入该批次「最终入选题」并合并到任务「关联题目」。在同一批次的「每题评估与淘汰原因」另写 `[KMP/pack_result/v1]`，记录 RW、plan_version、batch_id、review_revision、所用 TM 和小问、学生版及答案版引用、生成状态。用批次键与验收版本定位已有产物，超时先查找再续作。记录已生成前回读题包、链接和放行记录。计划或放行变化时将产物标记为过期并停止交付。
3. Agent 核对成品顺序、图表、公式、最后一题和答案隔离，提供任何成品链接前，最后回读同一 RW、plan_version、batch_id、review_revision 和 `active_review`，确认仍然有效，再反馈上游或用户。已过期或被替代的版本停止发放。上游在 delivery 中记成品验收及实际发出证据。旧记录即使有题包链接，也须有本轮放行证据才可用于本轮新发放。

## 5. 作答后重新进入计划

孩子可晚些作答。收到作答后由 Agent 调用上游，按原发放版本和小问写入作答、诊断与掌握证据，再更新日、周、月计划。未来计划进入可搜窗口后，Agent 依指令启动新一轮。同步环节是候选落库后立即交叉验收与放行，未来任务领取及作答回收可以异步。
