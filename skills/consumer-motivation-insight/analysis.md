# 消费动机洞察 · 本地分析适配 v1

分析仅使用本次 evidence 输入。先还原消费者的处境和变化诉求，再归纳候选人群；不能直接用一个宽泛身份词代替动机。

## 1. 情境 Context
逐条识别物理环境、身份/场景、个人属性。分别落实到现有输出的 layers.scene、layers.social、layers.natural；人生阶段写 life_stage。
未提到的年龄、收入、家庭状态不推定为事实。

## 2. 推力 Push
识别功能性问题、情绪状态、社交困扰。功能问题写 needs.explicit；情绪写 layers.emotion；社交困扰如有证据，在 barriers 中单独以“社交困扰”开头说明。
这些是当前处境中为什么想改变的原因，不是抽象人设。

## 3. 拉力 Pull
识别功能性期望、情感期望、社交期望。功能期望写 needs.implicit；情感和社交期望分别在 needs.deep.text 内明确标注，保留引用及推断标记。
不存在的维度写未知及验证方法，不以负面情绪反向推导隐秘欲望。

## 4. 由证据形成策略
buying_motivation 串起“在什么情境下，因为哪个阻碍，希望得到什么改变”。
audience_map 解释为什么同一关键词/身份下需要拆分，以及哪些候选可能重叠。
每个人群的营销建议都要回应其已识别的推力或拉力；产品、渠道、内容、达人、促销各写具体行动、适配原因与验证方式。
词只是搜索线索；缺少原帖或评论时明确 quality=limited。没有证据支撑的细分不凑数量。

## 5. 来源与能力边界
不是实时搜索：不得声称执行原 xhs-search 的远程检索、拥有其数据库或返回 ES 分数。
需要补充证据时，在 validation_questions 给出2至4条带维度前缀的检索建议，例如“环境：办公室”“问题：清洗费时”“期望：省时”。这是建议，不是已执行的查询。
继续遵守 segments 原有 JSON schema，不新增顶层字段；所有分析引用保持本模块 evidence_ids，未知项保留验证步骤。

## 独立动机字段
现在为每个人群输出 motives 对象，分别填写 environment、identity、attributes、functional_problem、emotion、social_friction、functional_expectation、emotional_expectation、social_expectation。每项独立提供 text、basis、evidence_ids、validation；未知也要明确标注，不从其他字段强行拆分。旧字段用于兼容和总体叙述，不代替这些独立记录。
