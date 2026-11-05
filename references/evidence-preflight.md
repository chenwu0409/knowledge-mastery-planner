# 定级前证据检查

上游在发布或改版计划前执行本检查。先读取相关范围与原卷证据、考试成绩库、关联作答和错题诊断、知识点最近复测日期。用有效记录的实际日期交叉核对复测。区分空白、明确为零、无权限及未查询。只有证据可核实时填 true 或 false，尚不可判填 null。保留用于判断的来源定位和对应小问。无权限或未查询时保留待补状态。

将下列快照传给 `python scripts/evidence_preflight.py <snapshot.json>`。脚本为纯本地计算。第一次运行可先传 `target_level: null`；上游拟定层级后用同一证据复算，将输出字段连同证据引用写入计划。

| 输入 | 口径 |
|---|---|
| scope_status | confirmed、provisional 或 unknown。仅当本次考试范围有直接证据时标 confirmed。 |
| zsd_id / target_level | 原 ZSD ID 和暂拟 L1–L4，层级未知用 null。 |
| direct_exam_requirement / comparable_exam_item | 前者须有能支持拟定层级的同校直接要求或充分同校原卷证据，后者为至少一道同阶段可比原卷小问。 |
| official_score | 是否有适用本次校准的真实分值或失分记录。 |
| independence_recorded / hints_recorded / timing_recorded | 是否有对应小问的明确独立性、提示和用时记录。零提示是有效记录。 |
| retest_date_recorded / unresolved_diagnosis | 是否有实际复测日期、是否存在未解决的关联诊断。未核实用 null。 |
| independent_target_attempts / independent_delayed_retests | 不同题面、过程可查、无提示的同层级达标次数。延迟复测计入前一项。仅计有证据的小问，零表示无达标证据，不推断为能力不足。 |

考试目标置信度依次判断。范围确认且有直接层级证据为 high。有直接或可比试题证据且范围至少暂定为 medium。其余为 low。掌握与稳定性分别按同层级有效次数计算。0 为 unknown，1 为 medium，2 或以上为 high。成绩、用时与错因缺口仅影响各自结论。每条 `evidence_gaps[]` 的 `blocks_level` 仅在缺项确实阻断某个已知层级时填写，否则为 null。补齐资料后重新判断，补齐本身不保证升级。

根据题目实际证据定级。题库难度、孩子作答情况与考试目标置信度分别判断。没有独立作答时可安排诊断。
