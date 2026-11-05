# Knowledge Mastery Planner

这是用于广东省广州市训练项目的上游 Skill。它根据考试证据维护知识点和目标能力层级，结合孩子的独立作答更新掌握证据，生成日、周、月训练计划。搜题和题包制作由下游完成，上游负责候选题交叉验收。 [下游 question-bank-selection](https://github.com/chenwu0409/question-bank-selection)

## 在任意支持文件指令的 Agent 中使用

1. 将本仓库作为 Skill 目录载入，或让 Agent 读取 [SKILL.md](SKILL.md) 并按其中链接查阅需要的说明。入口使用常见的 Markdown 和 YAML front matter。能读取这些文件并访问飞书即可执行，不依赖特定产品的配置文件。
2. 给 Agent 配置可用的飞书连接器、API 或 CLI 权限，并提供本轮动作，例如「审核明天的训练题」或「处理这份作答，更新后续计划」。
3. 小兔项目从 [飞书主库与七表结构](references/feishu-project.md) 定位现有 Base。做题证据和业务状态留在飞书。

## 两个 Skill 如何接续

| 上游 Knowledge Mastery Planner | 下游搜题 Skill |
|---|---|
| 维护范围与知识点，定目标能力，写任务及完整搜索条件 | 按任务 ID 或到期时间读取飞书，搜题、筛选并落库候选 |
| 候选落库后立即交叉验收，写入放行清单或补搜要求 | 读取放行清单后制作题包。收到退回则按要求补搜并再次交验 |
| 收到作答后更新独立能力和掌握稳定性，迭代下一次计划 | 后续收到指令后从飞书读取新的计划版本 |

未来任务的领取和孩子作答可以异步。候选落库后，同一轮由 Agent 接续上游验收，飞书中的计划版本、检索批次和验收记录用于恢复。执行时读 [异步搜题交接](references/async-selection.md) 和 [飞书读写 SOP](references/feishu-sop.md)。
