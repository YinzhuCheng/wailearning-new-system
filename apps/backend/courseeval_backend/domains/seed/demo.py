"""Default demo data: teacher `teacher`, class 人工智能1班, students stu1–stu5.

- **必修课**「数据挖掘」：教师按班级花名册统一入课（`sync_course_enrollments` / `subject_class_links`），含演示章节与第一次作业。
  演示作业区分「学生可见评分要点」与「仅教师可见评分细则」，并包含「参考答案或思路」字段（教师侧与 LLM 评分可见；学生 API 不返回）。
  演示会为前 3 名示例学生（stu1–stu3）幂等写入**已提交但未打分**的作业正文，便于查看提交列表。
- **选修课**「大语言模型」：由 `teacher` 授课；学生需自主选课；演示种子**不为全班自动入课**；**课程行不再绑定行政班**（`subjects.class_id = NULL`，列表班级列显示 `-`）。
- **选修课**「初等概率论」：由独立演示账号 `teacher_pro`（口令 `teacher_pro`）授课；资料与作业正文大量使用 Markdown + LaTeX；演示种子仅为 **stu1、stu2、stu4** 写入 `CourseEnrollment`，**stu3、stu5 不入课**以展示「有人选了有人没选」；并为 stu1、stu2 幂等写入未打分的提交样例。

若数据库中已有**通过校验且可用于评分**的全局 LLM 端点预设（见 `bootstrap._ensure_default_llm_endpoint_preset`，可在配置 `DEFAULT_LLM_API_KEY` 时于首次启动尝试文本+图像自检），本种子会为演示必修课/各选修课**幂等绑定**首个可用预设（或在无校验端点时退回到内置 `gpt-5.4` 行）并启用课程 LLM。

必修课资料区含三层演示章节。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseDiscussionEntry,
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialHomeworkLink,
    CourseMaterialSection,
    DiscussionLLMJob,
    Homework,
    HomeworkAttempt,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    LearningNote,
    LearningNoteChapter,
    LearningNoteDiscussionEntry,
    LearningNoteResource,
    Semester,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.llm_grading import refresh_submission_summary
from apps.backend.courseeval_backend.domains.roster.sync import reconcile_student_users_and_roster
from apps.backend.courseeval_backend.domains.seed.demo_courses import (
    ensure_demo_course_time as _ensure_demo_course_time,
    ensure_demo_subject_llm_binding as _ensure_demo_subject_llm_binding,
    ensure_required_demo_course,
    seed_demo_grade_weights as _seed_demo_grade_weights,
)
from apps.backend.courseeval_backend.domains.seed.demo_users import (
    DEMO_CLASS_NAME as _CLASS_NAME,
    DEMO_PASSWORD as _DEMO_PASSWORD,
    DEMO_TEACHER_DISPLAY_NAME as _TEACHER_DISPLAY_NAME,
    TEACHER_PRO_DISPLAY_NAME as _TEACHER_PRO_DISPLAY_NAME,
    TEACHER_PRO_PASSWORD as _TEACHER_PRO_PASSWORD,
    TEACHER_PRO_USERNAME as _TEACHER_PRO_USERNAME,
    ensure_demo_roster_context,
)

_SYSTEM_LLM_ASSISTANT_USERNAME = "__system_llm_assistant__"


_DEMO_NOTE_IMAGE_PATH = "/markdown-demo-card-image.svg"

_COURSE_NAME = "数据挖掘"

_LLM_COURSE_NAME = "大语言模型"
_LLM_COURSE_DESCRIPTION = (
    "全校默认选修示例：大语言模型基础与应用入门。完成本课需由学生在「我的课程」中自主选课；"
    "内容包含提示工程简介与一次实践作业。"
)
_LLM_COURSE_TIMES = "4@8,9"
_LLM_MATERIAL_TITLE = "【选修】大语言模型：课程说明与阅读材料"
_LLM_MATERIAL_CONTENT = """## 欢迎选修「大语言模型」

本课程为**选修课**，请在「我的课程」页面使用**选课**按钮加入后，方可查看作业与完整资料池。

### 学习目标

- 了解大语言模型的基本能力与局限；
- 掌握提示（Prompt）书写的基本结构；
- 完成一次简短的实践作业。

### 推荐阅读

1. 关注课程通知与 LLM 使用规范；
2. 课前可预习「提示工程」基础概念。
"""
_LLM_HOMEWORK_TITLE = "大语言模型入门作业：提示工程小练习"
_LLM_HOMEWORK_CONTENT = """请完成以下任务（建议 300–800 字或等价条目）：

1. 用你自己的话解释：什么是「提示工程」？它为什么会影响大语言模型的输出质量？
2. 设计一个用于「总结一段中文新闻要点」的提示模板，并说明每个部分的作用。
3. 指出使用大语言模型辅助学习时，你认为需要注意的两条风险或边界。

提交形式：纯文本或 Markdown 均可。"""
_LLM_RUBRIC_TEXT = """总分 100。关注是否理解提示工程、模板结构是否清楚、风险意识是否到位；表达清晰即可，不必长篇。
"""
_LLM_ELECTIVE_ENROLLED_STUDENT_NOS = ("stu1", "stu3", "stu5")
_LLM_PREFILL_STUDENT_NOS = ("stu1", "stu3")
_LLM_PREFILL_BODIES = (
    """# 提示工程练习 - stu1

我理解提示工程是把任务、背景、约束和输出格式写清楚，让模型更容易生成可检查的结果。

## 新闻摘要提示模板

请阅读下面这段新闻，并按以下格式输出：

1. 事实要点：列出 3-5 条；
2. 涉及主体：说明人物、机构或地点；
3. 不确定信息：标出原文没有直接说明的部分；
4. 一句话摘要：不超过 40 字。

## 风险

- 不能把模型生成内容当成事实来源，需要回看原文。
- 模型可能遗漏数字、时间和责任主体，摘要后要人工核对。""",
    """# 大语言模型入门作业 - stu3

提示工程不是“让模型猜我想要什么”，而是把目标拆成模型能执行的步骤。我设计的模板会先给角色和任务，再给材料，最后规定输出结构。

示例：

> 你是课堂助教，请把新闻材料整理成面向高中生的 5 条要点，并指出哪些地方需要进一步查证。

我认为风险主要有两点：第一是幻觉，第二是过度依赖。如果作业完全照搬模型输出，就可能没有真正理解材料。""",
)

_PROB_COURSE_NAME = "初等概率论"
_PROB_COURSE_DESCRIPTION = (
    "面向理工科低年级同学的初等概率论选修示例：从样本空间与 Kolmogorov 公理出发，介绍条件概率、"
    "Bayes 公式与常见离散分布，强调计算与直觉并重。课堂鼓励使用 Markdown + LaTeX 书写推导。"
    "【演示】本课由独立教师账号 teacher_pro 授课，资料与作业含大量公式排版示例。"
)
_PROB_COURSE_TIMES = "3@3,4"
_PROB_MATERIAL_TITLE = "【选修】初等概率论：导读、记号与核心公式"
_PROB_MATERIAL_CONTENT = r"""## 课程说明（选修）

本资料为「初等概率论」演示课程的**阅读材料**，正文使用 **Markdown**，数学公式使用 **LaTeX**（前端以 KaTeX 渲染）。约定：

- **行内公式**：`\(a+b\)` 或 `$P(A)$`
- **独立公式**：`$$...$$` 或 `\[...\]`

### 样本空间与事件

随机试验所有可能结果构成样本空间 \(\Omega\)。（入门课常用有限或可数 \(\Omega\)。）事件 \(A\) 为 \(\Omega\) 的子集；本书写采用经典集合记号。

### Kolmogorov 公理（重温）

概率测度 \(P\) 满足：对任意事件 \(A\)，\(P(A)\ge 0\)；\(P(\Omega)=1\)；对两两不交的可列事件列 \(\{A_i\}\)，有可数可加性
$$
P\Bigl(\bigcup_{i=1}^{\infty} A_i\Bigr)=\sum_{i=1}^{\infty} P(A_i).
$$

### 条件概率与 Bayes

若 \(P(B)>0\)，定义
$$
P(A\mid B)=\frac{P(AB)}{P(B)}.
$$

设 \(\{B_i\}\) 为 \(\Omega\) 的划分且 \(P(B_i)>0\)，则 **全概率公式**
$$
P(A)=\sum_i P(B_i)\,P(A\mid B_i),
$$
以及 **Bayes 公式**
$$
P(B_j\mid A)=\frac{P(B_j)\,P(A\mid B_j)}{\sum_i P(B_i)\,P(A\mid B_i)}.
$$

### 离散分布速查

- **Bernoulli(\(p\))**：\(P(X=1)=p,\ P(X=0)=1-p\)。
- **Binomial(\(n,p\))**：\(P(X=k)=\binom{n}{k}p^k(1-p)^{n-k}\)，\(k=0,\ldots,n\)。
- **Poisson(\(\lambda\))**：\(P(X=k)=\mathrm{e}^{-\lambda}\lambda^k/k!\)。

### 推荐阅读（杜撰书目条目，仅供 UI 演示）

1. 《概率论基础教程》风格读物（离散概率与极限定理导引）。
2. 任意一本工科「概率论与数理统计」教材的第 1–2 章作为对照阅读。

:::example 课程阅读方式
1. 先看中文语义，再看公式；
2. 先分清“已知什么”，再分清“要求什么”；
3. 若概念还不稳，优先画事件树或列两向表。
:::

:::pricing 本单元重点
- 记号与样本空间：建立统一表达基础
- 条件概率与 Bayes：建立“先验 → 证据 → 后验”的推理链
- 离散分布：建立“随机变量含义 + 参数解释 + 场景匹配”的专业表达
:::

:::note 专业表达提醒
概率论写作里，公式本身不是最终目标。真正重要的是：符号定义、推理顺序、结论解释要能让别人复核。
:::

:::warning 常见误区
- 把 \(P(A\mid B)\) 与 \(P(B\mid A)\) 当成“形式差不多的两个量”；
- 只写最终概率，不说明样本空间或分母从哪里来；
- 把“模型名”当成结论，而没有解释为何适合当前问题。
:::
"""

_PROB_HOMEWORK_TITLE = "初等概率论第一次作业：古典概型与 Bayes 计算"
_PROB_HOMEWORK_CONTENT = r"""本次作业练习集合运算、古典概率、条件概率与 Bayes 公式，请在答题区使用 Markdown；涉及公式时请用 LaTeX（例如 `\(P(A)\)`、`$$...$$`）。

---

### 题 1（古典概率）

一枚公平骰子掷两次，记录有序对 \((i,j)\)。

1. 写出样本空间 \(\Omega\) 的元素个数。
2. 求两次点数之和为 \(7\) 的概率。
3. 求最大点数不超过 \(4\) 的概率。

### 题 2（条件概率）

某班级学生参加两次模拟测验。已知随机抽一名学生，其第一次及格的概率为 \(0.7\)；在第一次及格的条件下第二次及格的概率为 \(0.85\)；在第一次不及格的条件下第二次及格的概率为 \(0.4\)。

1. 若已知该生第二次及格，求其第一次也及格的后验概率（化为最简分数或保留三位小数均可，但需给出推导）。
2. 指出你在哪一步使用了 Bayes 公式。

### 题 3（概念简述）

用自己的话解释：**统计独立性**与**条件概率**之间的关系（无需长篇，3–6 句即可）。

---

**提交说明**：字数不限，但必须按题号作答；推导清晰即可，数值可与参考答案不完全一致但需自洽。
"""

_PROB_RUBRIC_STUDENT = """满分 100。学生可见导向：是否在三题中分别给出可检查的样本空间/计数或方程推导；Bayes 题是否体现「由结果反推原因」的结构；概念题是否区分独立与条件概率。细则与配分表仅供教师与自动评分模型内部参照。"""

_PROB_RUBRIC_STAFF_ONLY = r"""内部评分细则（总分 100；宽松鼓励型演示）

1. 古典概率（35 分）：正确样本空间规模与计数思路 15 分；和为 7 的概率 10 分；最大值约束题 10 分。
2. Bayes（45 分）：正确设定事件记号（如 A=第一次及格，B=第二次及格）10 分；全概率求 P(B) 15 分；Bayes 反推 P(A|B) 15 分；指出 Bayes 步骤 5 分。
3. 概念简述（20 分）：提到 P(AB)=P(A)P(B) 与独立时 P(A|B)=P(A) 等关键结论即可满分区间；泛泛而谈酌情扣分。

常见可接受答案提示：题 1 中 |\Omega|=36；和为 7 的有利结果数为 6；最大点数 ≤4 可利用对立或逐计数得到 4/9（需与学生推导一致）。"""

_PROB_REFERENCE_OR_APPROACH = r"""（教师侧核对）题1：|\Omega|=36；P(和为7)=6/36=1/6；P(\max\le 4)=16/36=4/9。题2：记 A 第一次及格，B 第二次及格；P(B)=P(A)P(B|A)+P(A^c)P(B|A^c)=0.7\times0.85+0.3\times0.4=0.715；Bayes 得 P(A|B)=\frac{0.7\times0.85}{0.715}=\frac{119}{143}\approx0.832。题3：独立则条件概率等于边际概率；一般不独立时 P(AB)=P(A)P(B|A)。"""

_PROB_CARD_SHOWCASE = f""":::example 示例用法
1. 公式推导、评分标准、课堂节奏都适合放进彩色卡片。
2. 卡片内部依然支持 **粗体**、列表、`行内代码`、图片和公式。
3. 这部分写法直接复用系统内置 Markdown 演示语法。
:::

:::pricing 课程结构速览
- 单元一：样本空间、事件与古典概型
- 单元二：条件概率、全概率公式与 Bayes 推断
- 单元三：离散分布、事件树表达与阶段复盘
:::

:::note 插图示例
下图是演示课程统一使用的示意图资源，采用标准 Markdown 图片语法插入。

![概率课事件树示意图]({_DEMO_NOTE_IMAGE_PATH})
:::

:::tip 当前结论
- 先让学生把中文语义写清楚，再写 Bayes 公式，整体错误率会明显下降。
:::

:::warning 待确认
- 如果一次材料里同时放事件树、表格、完整推导，课堂上应提醒学生区分“表达结构”与“重复抄写”。
:::
"""

_PROB_READER_SHOWCASE = r"""## Bayes 推断的阅读页样板

本页不是“只给几个公式”，而是按课堂阅读逻辑组织：

1. 先用文字说明问题背景；
2. 再给出事件定义与推理顺序；
3. 最后用卡片总结常见误区、建模边界和作业表达规范。

### 一个更完整的后验推断例子

设 \(D\) 表示“样本来自缺陷批次”，\(T\) 表示“检测阳性”。若
\[
P(D)=0.08,\qquad P(T\mid D)=0.96,\qquad P(T\mid D^c)=0.05,
\]
则先由全概率公式得到
\[
P(T)=P(D)P(T\mid D)+P(D^c)P(T\mid D^c)
=0.08\times0.96+0.92\times0.05=0.1228.
\]
于是 Bayes 公式给出
\[
P(D\mid T)=\frac{P(D)P(T\mid D)}{P(T)}
=\frac{0.08\times0.96}{0.1228}\approx 0.625.
\]

这说明：即使检测对缺陷批次非常敏感，若先验缺陷率并不高，阳性结果的后验概率也未必接近 1。后验判断永远要同时看**先验**和**证据质量**。

:::example 阅读顺序
1. 先确认事件定义；
2. 再看证据来自哪几条路径；
3. 最后解释“后验为什么不是直觉上的 96%”。
:::

:::pricing 专业术语分层
- 先验（prior）：尚未观察证据前的背景概率
- 似然（likelihood）：在给定原因下观察到证据的可能性
- 证据（evidence）：当前观察到的整体事件
- 后验（posterior）：观察到证据后对原因的更新判断
:::

:::note 课堂提醒
在真实教学里，学生最容易忽略的是“分母 \(P(T)\) 不是 1，也不是 \(P(T\mid D)\)”。它必须是所有导致阳性的路径总和。
:::

:::tip 写作建议
若要把这类题写得更专业，除了公式本身，还应补一句解释：为什么先验较低时，阳性结果的后验不会像灵敏度那样高。
:::

:::warning 模型边界
Bayes 公式本身始终成立，但具体应用时必须保证事件定义一致、条件概率来自同一抽样口径，且证据没有被重复计算。
:::

:::danger 常见误判
- 把 \(P(T\mid D)\) 当成 \(P(D\mid T)\)
- 只看检测灵敏度，不看先验比例
- 分母漏掉 \(D^c\) 分支上的阳性路径
:::

"""
_PROB_READER_SHOWCASE += f"\n\n![概率课事件树示意图]({_DEMO_NOTE_IMAGE_PATH})\n"

_PROB_CHAPTER_TREE = (
    {
        "title": "第一单元：概率空间、事件与计数方法",
        "sort_order": 10,
        "children": (
            {
                "title": "1.1 课程导读与记号约定",
                "sort_order": 0,
                "materials": (
                    {
                        "title": _PROB_MATERIAL_TITLE,
                        "sort_order": 0,
                        "content": _PROB_MATERIAL_CONTENT,
                    },
                    {
                        "title": "课程导学：学习目标、先修要求与作业规范",
                        "sort_order": 10,
                        "content": rf"""## 课程定位

本课面向理工科低年级学生，强调**概念清晰、推导规范、书写可检查**。课程展示的不是“题海题库”，而是一个较完整的教学样板：目录、资料、作业、讨论、笔记、反馈都尽量贴近真实教学组织方式。

### 学习目标

1. 理解样本空间、事件、概率公理、条件概率与独立性的基本概念；
2. 能用规范记号完成古典概型与 Bayes 公式的基础计算；
3. 能把文字说明、公式推导、表格与图示组织成一份可阅读的作业或笔记。

### 建议书写规范

- 事件建议统一写成 \(A,B,C\) 或 \(E_1,E_2,\ldots\)；
- 条件概率、全概率、Bayes 的推导请尽量逐步写出，不要只给最终数值；
- 若使用 Markdown + LaTeX，请保证行内公式与独立公式格式一致；
- 若采用事件树、两向表、流程图等辅助表达，请在文字中说明其作用。

:::tip 演示课程说明
本课程允许在资料区、作业区、讨论区、学习笔记中使用 Markdown、LaTeX、分块卡片和图片插入。演示数据会刻意展示这些能力，方便部署后验收。
:::

{_PROB_CARD_SHOWCASE}
""",
                    },
                ),
                "homework_links": (
                    {"title_contains": "第一次作业", "sort_order": 0},
                ),
            },
            {
                "title": "1.2 古典概型与组合计数",
                "sort_order": 10,
                "materials": (
                    {
                        "title": "讲义：古典概型中的样本空间构造",
                        "sort_order": 0,
                        "content": r"""## 样本空间的构造原则

在古典概型中，关键不是“背公式”，而是先判断：

1. 结果是否**等可能**；
2. 试验结果是**有序**还是**无序**；
3. 需要枚举的是**元素**还是**事件**。

### 典型提醒

- 掷骰两次通常记录有序对 \((i,j)\)，因此 \(|\Omega|=36\)；
- 不放回抽样要特别区分“先后顺序是否有意义”；
- 同一问题可以用枚举、对立事件、组合计数多种方式求解，但最终含义必须一致。

### 规范表达示例

:::example 书写模板
设随机试验的样本空间为 \(\Omega\)，若每个样本点等可能，则
$$
P(A)=\frac{|A|}{|\Omega|}.
$$
求解时先给出 \(|\Omega|\) 与 \(|A|\) 的定义，再代入数值。
:::
""",
                    },
                ),
                "homework_links": (
                    {"title_contains": "第一次作业", "sort_order": 0},
                ),
            },
        ),
    },
    {
        "title": "第二单元：条件概率、全概率公式与 Bayes 推断",
        "sort_order": 20,
        "children": (
            {
                "title": "2.1 条件概率与独立性辨析",
                "sort_order": 0,
                "materials": (
                    {
                        "title": "讲义：条件概率不是“把竖线看成分号”",
                        "sort_order": 0,
                        "content": r"""## 常见误区

学生最容易把 \(P(A\mid B)\) 和 \(P(B\mid A)\) 混淆。纠正方法不是机械记忆，而是每次都先把中文语义写完整：

- \(P(A\mid B)\)：**已知** \(B\) 发生，再看 \(A\) 发生的概率；
- \(P(B\mid A)\)：**已知** \(A\) 发生，再看 \(B\) 发生的概率。

### 可视化建议

1. 用两向表展示总体、条件与后验；
2. 用事件树标明“先验 \(\rightarrow\) 条件 \(\rightarrow\) 联合 \(\rightarrow\) 后验”；
3. 对同一道题，允许学生文字解释和公式推导并行出现。

:::warning 批改提醒
若学生写出了数值但没有说明事件方向，应判定为“结果可疑但思路未充分展开”，不宜直接视为满分答案。
:::

:::example 最稳的自检方式
把公式先翻译成中文句子：

- \(P(A\mid B)\)：在“已经知道 \(B\)”的前提下，看 \(A\)；
- \(P(B\mid A)\)：在“已经知道 \(A\)”的前提下，看 \(B\)。

若中文说不顺，公式多半也没有真正理解。
:::

:::danger 不建议的作答方式
- 直接抄 Bayes 模板但不写事件定义；
- 分母只写一个数字，不说明它对应的是哪一个整体事件；
- 把“条件概率”和“联合概率”混在一句话里。
:::
""",
                    },
                    {
                        "title": "课堂板书整理：全概率公式与 Bayes 公式的使用顺序",
                        "sort_order": 10,
                        "content": r"""## 使用顺序建议

1. 先明确“要求的后验”是什么；
2. 再确认是否需要先通过全概率公式计算分母；
3. 最后写 Bayes 公式并解释每一项的来源。

```text
先验 → 条件概率 → 联合概率 / 全概率 → 后验概率
```

### 统一记号模板

若 \(\{B_i\}\) 构成划分，则
$$
P(A)=\sum_i P(B_i)P(A\mid B_i),\qquad
P(B_j\mid A)=\frac{P(B_j)P(A\mid B_j)}{\sum_i P(B_i)P(A\mid B_i)}.
$$

### 课堂说明

- 允许学生用表格或树图辅助说明；
- 若只写结论不写中间推理，教师反馈里应提示“推导链条不完整”；
- 若推导链条合理但算术有小错，可在反馈中明确区分“方法正确”和“计算失误”。

:::pricing 教师讲评顺序
- 先对齐事件定义；
- 再回看事件树或表格；
- 最后检查 Bayes 公式中的分子与分母是否都能对应到图示。
:::
""",
                    },
                    {
                        "title": "阅读页样板：从先验、似然到后验的完整说明",
                        "sort_order": 20,
                        "content": _PROB_READER_SHOWCASE,
                    },
                ),
                "homework_links": (
                    {"title_contains": "第一次作业", "sort_order": 0},
                ),
            },
        ),
    },
    {
        "title": "第三单元：离散分布、随机变量与阶段总结",
        "sort_order": 30,
        "children": (
            {
                "title": "3.1 Bernoulli、Binomial 与 Poisson 的联系",
                "sort_order": 0,
                "materials": (
                    {
                        "title": "阅读单：三类离散分布的参数意义与适用场景",
                        "sort_order": 0,
                        "content": r"""## 观察角度

- **Bernoulli(\(p\))**：一次试验，两种结果；
- **Binomial(\(n,p\))**：\(n\) 次独立重复 Bernoulli 试验的成功次数；
- **Poisson(\(\lambda\))**：单位区间内低频事件的发生次数模型。

### 建议比较方式

| 分布 | 随机变量含义 | 关键参数 | 典型场景 |
| --- | --- | --- | --- |
| Bernoulli | 一次成功/失败 | \(p\) | 一题答对/答错 |
| Binomial | 多次试验中的成功次数 | \(n,p\) | 抽样中成功个数 |
| Poisson | 单位时间内事件次数 | \(\lambda\) | 呼叫量、到达量 |

:::note 写作建议
在作业与笔记里，不必把所有定义抄全，但应至少解释“随机变量代表什么”“参数控制什么”“为什么这个模型适合当前问题”。
:::

:::example 最小专业表述模板
- 随机变量：描述什么数量；
- 参数：决定什么特征；
- 场景：为什么这个分布适合这里；
- 限制：哪些前提不满足时不应生搬硬套。
:::

:::warning 建模边界
若事件并不稀有、发生率不稳定、或样本间并不近似独立，就不应轻率地说“可以用 Poisson 分布”。
:::
""",
                    },
                    {
                        "title": "专题阅读：离散随机变量建模时不要忽略的问题口径",
                        "sort_order": 10,
                        "content": r"""## 为什么“题会做”还不够

在课堂作业里，学生往往能写出 Bernoulli、Binomial 或 Poisson 的公式，但没有说明“随机变量到底在数什么”。真正专业的表达，必须先明确：

1. 一个试验单位是什么；
2. 观测窗口是什么；
3. 计数变量是否满足独立、同分布或稳定率等前提。

### 例 1：Bernoulli 与 Binomial 的自然衔接

若 \(X_i\) 表示第 \(i\) 次作答是否成功，则
\[
X_i \sim Bernoulli(p),\qquad
S_n=\sum_{i=1}^{n} X_i \sim Binomial(n,p)
\]
的前提不只是“会加起来”，还包括各次尝试之间近似独立、成功概率近似稳定。

:::example 最小建模模板
- 试验单位：一次抽样 / 一次答题 / 一位顾客到达
- 随机变量：成功次数 / 到达次数 / 阳性个数
- 参数解释：\(p\) 是成功率，\(n\) 是试验次数，\(\lambda\) 是平均到达率
:::

### 例 2：Poisson 为什么常被误用

Poisson 分布适合描述单位时间或单位区间内的计数，但并不是所有“次数问题”都能直接套用。若高峰期与低峰期混在一起、或者事件彼此强相关，直接写
\[
N \sim Poisson(\lambda)
\]
通常只是形式正确，而不具备解释力。

:::warning 口径检查
- 你数的是“每分钟请求数”还是“每天请求数”？
- 你用的 \(\lambda\) 是长期平均，还是某个局部时段平均？
- 若存在明显分时波动，是否更适合分段建模？
:::

:::danger 常见失误
- 把“平均每小时 6 次”直接搬到“平均每分钟概率”而不换口径；
- 忽略样本间强依赖，例如同一故障引发成批报警；
- 只写模型名，不说明它为什么适合当前问题。
:::
""",
                    },
                    {
                        "title": "阶段复盘：如何把公式推导写成规范作业",
                        "sort_order": 20,
                        "content": r"""## 阶段复盘清单

### 一份规范的概率论作业通常包含

1. 题意重述或符号约定；
2. 样本空间/事件定义；
3. 推导链条；
4. 数值结论；
5. 对结果的文字解释。

### 反馈导向

:::pricing 教师重点查看
- 公式是否对应了题目中的“已知”和“求解”；
- 是否能区分“思路错误”和“算术错误”；
- 是否能用简洁文字解释结果代表什么。
:::

:::tip 学生自查
- Bayes 题是否先写清楚后验目标？
- 是否说明了分母从哪里来？
- 如果用了事件树或表格，是否在文中解释了图的用途？
:::
""",
                    },
                    {
                        "title": "补充讲义：事件树、两向表与公式三种表达怎样分工",
                        "sort_order": 30,
                        "content": r"""## 三种表达不是互相替代，而是互相支撑

在概率论书写中，事件树、两向表和公式各自承担不同任务：

- **事件树**：适合表现“分支顺序”和条件展开；
- **两向表**：适合对照联合概率、边际概率与后验更新；
- **公式**：适合做规范化推导与最终表达。

### 一个教学上很实用的分工

:::example 事件树负责什么
把“先从哪一类总体抽样，再出现什么检测结果”表达清楚，让学生知道概率是沿路径相乘、沿同类路径相加。
:::

:::pricing 两向表负责什么
把“总体”“阳性”“阴性”“联合事件”“边际事件”放到同一张表里，帮助学生看清楚分母究竟代表哪一个整体。
:::

:::note 公式负责什么
在图示和表格已经解释清楚语义之后，公式提供的是**统一、可复核、可推广**的数学表达。
:::

### 为什么这三者一起用会更专业

仅有公式时，学生容易把条件方向写反；仅有图示时，又可能停留在直觉层面，缺少可复核的推导。把三者组合起来，既能保证解释性，也能保证规范性。

:::tip 实用建议
若篇幅有限，可保留事件树 + 核心公式；若是课堂讲评或样板讲义，则建议三者同时出现。
:::
""",
                    },
                ),
                "homework_links": (
                    {"title_contains": "第二次作业", "sort_order": 0},
                ),
            },
        ),
    },
)

_PROB_HOMEWORK_TWO_TITLE = "初等概率论第二次作业：离散分布建模与事件树表达"
_PROB_HOMEWORK_TWO_CONTENT = rf"""本次作业要求你在 **Markdown + LaTeX** 中完成更规范的概率建模表达，并结合事件树或表格展示推理过程。

---

### 题 1（Bernoulli / Binomial）

某在线判题系统中，一名学生独立完成一道二分类题目，每次尝试答对的概率为 \(p=0.6\)。

1. 将一次尝试写成一个 Bernoulli 随机变量 \(X\)；
2. 若连续尝试 5 次，写出“恰好答对 3 次”的概率表达式；
3. 用一句话解释 Binomial(\(n,p\)) 中两个参数各自表示什么。

### 题 2（事件树 + 条件概率）

某实验流程分为“样本抽取”和“检测判断”两步。设样本来自 A 类总体的概率为 \(0.3\)，来自 B 类总体的概率为 \(0.7\)。若样本来自 A 类，则检测为阳性的概率为 \(0.9\)；若来自 B 类，则检测为阳性的概率为 \(0.2\)。

1. 画出或文字描述一个两层事件树；
2. 求检测结果为阳性的概率；
3. 已知检测阳性，求样本来自 A 类的后验概率；
4. 说明事件树在这道题里解决了什么表达问题。

### 题 3（Poisson 建模直觉）

请用 4–8 句话解释：在什么条件下，某类“单位时间内发生次数”的问题可以尝试用 Poisson 分布建模？不要求严格证明，但要提到“稀有”“独立”“平均发生率”中的至少两个关键词。

---

**提交要求**

- 至少有一题展示中间推导，不要只写最终结论；
- 建议至少一题用事件树、表格或分层条目表达结构；
- 允许使用图片插入事件树截图，但请同时保留文字说明。

{_PROB_CARD_SHOWCASE}
"""

_PROB_HOMEWORK_TWO_RUBRIC_STUDENT = """满分 100。学生可见导向：是否正确区分 Bernoulli / Binomial / Poisson 的对象与参数；是否能通过事件树或等价结构表达条件概率链条；是否能对建模条件给出简洁、专业而自洽的说明。"""

_PROB_HOMEWORK_TWO_RUBRIC_STAFF_ONLY = r"""内部评分细则（总分 100）

1. Bernoulli / Binomial（30 分）：随机变量定义 10 分；二项分布表达式 15 分；参数解释 5 分。
2. 条件概率与事件树（45 分）：事件树或等价分层表达 10 分；阳性概率 15 分；后验概率 15 分；解释事件树作用 5 分。
3. Poisson 建模直觉（25 分）：提到“单位时间次数”5 分；提到“独立/近似独立”10 分；提到“平均发生率稳定”或“稀有事件”10 分。

对演示数据采取鼓励式评分：若结构清楚、术语大体正确，可保留较高分区；主要反馈应帮助学生提升书写规范而非机械扣分。
"""

_PROB_HOMEWORK_TWO_REFERENCE = r"""（教师侧核对）题1：令 \(X\sim Bernoulli(0.6)\)，则 \(P(X=1)=0.6\)。5 次尝试中恰好答对 3 次：
$$
P(Y=3)=\binom{5}{3}(0.6)^3(0.4)^2,\quad Y\sim Binomial(5,0.6).
$$
题2：先算
$$
P(+)=0.3\times0.9+0.7\times0.2=0.41,
$$
再用 Bayes 得
$$
P(A\mid +)=\frac{0.3\times0.9}{0.41}=\frac{27}{41}\approx0.659.
$$
题3：可提到“单位时间内计数”“事件相对稀有”“近似独立”“平均发生率稳定”等要点。"""

_PROB_HOMEWORK_TWO_PREFILL_STUDENT_NOS = ("stu1", "stu4")
_PROB_HOMEWORK_TWO_PREFILL_BODIES = (
    r"""# 第二次作业提交（stu1）

## 题1

记一次答题是否成功的随机变量为 \(X\)，若答对记作 1，答错记作 0，则
\[
P(X=1)=0.6,\qquad P(X=0)=0.4.
\]
连续 5 次尝试中恰好答对 3 次的概率应写成
\[
\binom{5}{3}(0.6)^3(0.4)^2.
\]

## 题2

我先写事件树：

- 第一步：来自 A 类（0.3）或 B 类（0.7）；
- 第二步：在各自分支下再判断阳性/阴性。

这样可以直接看出阳性总概率来自两条阳性路径之和，然后再做 Bayes 反推。

## 题3

Poisson 更适合描述单位时间内“次数”问题，而且这些事件通常比较稀有，平均发生率相对稳定。""",
    r"""# 第二次作业提交（stu4）

### 结构草稿

1. 先区分 Bernoulli 和 Binomial：一个是“一次试验结果”，一个是“多次试验成功次数”；
2. 用事件树组织条件概率；
3. 用文字解释 Poisson 的建模条件。

### 当前问题

我能写出公式，但对“为什么 Poisson 适合建模”解释得还不够自然，准备再补一段课堂例子。""",
)

_PROB_NOTE_IMAGE_MARKDOWN = (
    f"![概率课事件树示意图]({_DEMO_NOTE_IMAGE_PATH})"
)

_PROB_ELECTIVE_ENROLLED_STUDENT_NOS = ("stu1", "stu2", "stu4")
_PROB_PREFILL_STUDENT_NOS = ("stu1", "stu2")
_PROB_PREFILL_BODIES = (
    r"""### 解答草稿（stu1）

**题1** \(|\Omega|=36\)，和为 7 的有序对有 6 种，故概率 \(6/36=1/6\)。最大点数 \(\le 4\)：有利 \(4\times4=16\)，概率 \(16/36=4/9\)。

**题2** 设 \(A\) 第一次及格，\(B\) 第二次及格；先用全概率算 \(P(B)\)，再用 Bayes 得 \(P(A\mid B)=\dfrac{P(A)P(B\mid A)}{P(B)}\approx 0.832\)（中间步骤略）。

**题3** 独立意味着条件概率退化；不独立时需要用 \(P(AB)=P(A)P(B\mid A)\)。
""",
    r"""### 解答（stu2）

题1：两次掷骰有序，样本点总数 \(36\)。和为 \(7\)：\((1,6)\cdots(6,1)\) 共 \(6\) 种 \(\Rightarrow 1/6\)。

题2：写了事件定义并用 Bayes，数值与老师讲义例题略有不同但公式写得清楚。

题3：独立性即 \(P(A\cap B)=P(A)P(B)\)。
""",
)

_COURSE_TIMES = "2@7,8"
_COURSE_DESCRIPTION = (
    "数据挖掘入门与实践（演示课程）。涵盖 Python 数据分析基础、特征与可视化、"
    "简单预处理与经典数据集探索；平时作业与课堂表现结合考核。"
)

# Demo material outline: three chapter nodes (depth 3), idempotent by root title.
_DEMO_CHAPTER_ROOT = "【演示】第一单元：导论与数据概览"
_DEMO_CHAPTER_L2 = "【演示】第一节：Python 环境与常用库"
_DEMO_CHAPTER_L3 = "【演示】1.1 课程资料与拓展阅读"
_DEMO_REQUIRED_MATERIAL_TREE = (
    {
        "title": _DEMO_CHAPTER_ROOT,
        "sort_order": 10,
        "children": (
            {
                "title": _DEMO_CHAPTER_L2,
                "sort_order": 0,
                "children": (
                    {
                        "title": _DEMO_CHAPTER_L3,
                        "sort_order": 0,
                        "homework_links": (
                            {"title_contains": "第一次作业", "sort_order": 0},
                        ),
                        "materials": (
                            {
                                "title": "【演示】课程运行说明与第一次课检查清单",
                                "sort_order": 0,
                                "content": """## 课程运行说明

本课程已经进入第 3 周演示状态。资料区会持续补充课件、实验讲义、课堂问答整理和作业说明，学生可以把这里的章节树复制到自己的学习笔记中再做二次整理。

### 第一次课需要确认的事项

1. 已经能登录平台并进入“数据挖掘”课程。
2. 已经安装或可访问一个 Python 运行环境：Anaconda、Jupyter Notebook、VS Code、Google Colab、学校实验服务器均可。
3. 已经能导入 `numpy`、`pandas`、`matplotlib`，如果 `seaborn` 或 `sklearn` 暂时失败，需要在作业里写清楚错误信息和尝试过的解决方式。
4. 已阅读 Wine 数据集字段说明，理解本课程第一次作业重点不是建复杂模型，而是把数据读取、查看、统计、可视化和解释串起来。

### 教师提醒

- 提交内容可以是 Notebook、PDF、Markdown、截图组合或压缩包。
- 不要求所有同学使用完全一致的环境，关键是过程可复现、结论可解释。
- 后续资料会逐步补充到“数据清洗”“可视化报告”“模型入门”单元。""",
                            },
                            {
                                "title": "【演示】Wine 数据集字段速查表",
                                "sort_order": 10,
                                "content": """## Wine 数据集字段速查表

Wine 数据集来自经典机器学习示例，共 178 条样本、13 个连续型化学特征，以及 3 个类别标签。第一次作业只要求完成基础探索，不要求训练分类器。

| 字段 | 可解释含义 | 第一次作业建议观察点 |
| --- | --- | --- |
| `alcohol` | 酒精含量 | 数值范围较窄，可与类别均值一起观察 |
| `malic_acid` | 苹果酸 | 分布可能偏斜，适合画直方图 |
| `ash` | 灰分 | 可作为字段查看和描述统计示例 |
| `alcalinity_of_ash` | 灰分碱度 | 与若干类别差异有关 |
| `magnesium` | 镁含量 | 量纲与部分字段差异明显 |
| `color_intensity` | 颜色强度 | 常用于观察不同类别的分布差异 |
| `hue` | 色调 | 与 `color_intensity` 组合画散点图较直观 |
| `proline` | 脯氨酸 | 数值尺度明显大于大多数字段，适合讨论标准化 |

### 推荐最小分析路径

1. `load_wine()` 读取数据。
2. 转为 `DataFrame`，添加 `target` 和 `target_name`。
3. 使用 `head()`、`info()`、`describe()` 检查数据。
4. 使用 `groupby("target_name").mean()` 查看类别均值差异。
5. 对 `alcohol`、`color_intensity`、`proline` 至少画一种图或给出统计解释。""",
                            },
                        ),
                    },
                ),
            },
            {
                "title": "【演示】第二节：课堂纪要与常见问题",
                "sort_order": 10,
                "materials": (
                    {
                        "title": "【演示】第 1-2 周课堂 FAQ：环境、路径与包导入",
                        "sort_order": 0,
                        "content": """## 第 1-2 周课堂 FAQ

### Q1：`ModuleNotFoundError: No module named 'sklearn'` 怎么办？

通常是当前 Python 环境没有安装 `scikit-learn`，或者 Notebook 内核不是你安装包的那个环境。建议先在 Notebook 里运行：

```python
import sys
print(sys.executable)
```

确认当前解释器路径，再在对应环境中安装依赖。作业中如果仍未解决，可以截图或复制错误信息，并说明你已经尝试过哪些步骤。

### Q2：为什么 `info()` 的输出没有直接显示在提交里？

`DataFrame.info()` 默认写到标准输出，不直接返回字符串。可以在 Notebook 中截图，也可以先关注 `df.shape`、`df.columns`、`df.dtypes`、`df.isna().sum()` 这些更容易复制到报告里的结果。

### Q3：图表显示中文乱码会不会扣很多分？

第一次作业不以图表美观为重点。只要图表或统计结果能支持你的观察，中文字体问题不会作为主要扣分项。请在报告中写清楚图表含义。

### Q4：可以用在线环境吗？

可以。Colab、学校实验平台、Kaggle Notebook 都可以。请写明环境名称和主要库版本，便于教师判断问题来源。""",
                    },
                ),
            },
        ),
    },
    {
        "title": "【演示】第二单元：数据清洗与特征理解",
        "sort_order": 20,
        "children": (
            {
                "title": "【演示】2.1 缺失值、重复值与异常值检查",
                "sort_order": 0,
                "materials": (
                    {
                        "title": "【演示】实验讲义：从 DataFrame 质量检查开始",
                        "sort_order": 0,
                        "content": """## 实验目标

本讲义用于第二单元的数据质量检查练习。即使 Wine 数据集本身比较干净，也要养成先检查数据质量再分析的习惯。

### 建议代码片段

```python
from sklearn.datasets import load_wine
import pandas as pd

wine = load_wine(as_frame=True)
df = wine.frame.copy()
df["target_name"] = df["target"].map(dict(enumerate(wine.target_names)))

print(df.shape)
print(df.isna().sum().sort_values(ascending=False).head())
print(df.duplicated().sum())
print(df.describe().T[["mean", "std", "min", "max"]])
```

### 报告写作建议

- 如果没有缺失值，也要写“检查结果为无缺失”，不要省略检查过程。
- 对数值范围特别大的字段，例如 `proline`，说明它为什么会影响基于距离或梯度的模型。
- 不要只贴代码，至少写 2-3 句解释。""",
                    },
                ),
            },
            {
                "title": "【演示】2.2 标准化、归一化与尺度敏感模型",
                "sort_order": 10,
                "materials": (
                    {
                        "title": "【演示】标准化课堂板书整理",
                        "sort_order": 0,
                        "content": """## 标准化为什么重要

Wine 数据集中 `proline` 的数值通常远大于 `alcohol`、`hue` 等字段。如果直接把这些字段输入到 KNN、K-Means、SVM 等对距离或尺度敏感的模型中，数值范围大的字段可能占据过高权重。

### 常用公式

```python
def standardize(x):
    return (x - x.mean()) / x.std()
```

标准化后的数据通常具有均值接近 0、标准差接近 1 的特点。第一次作业不要求比较模型效果，但要求能解释标准化的直观意义。

### 常见误区

1. “标准化会让数据变得更准确”这个说法不严谨。标准化改变的是尺度，不是原始观测质量。
2. 不是所有模型都同样依赖标准化。树模型通常没有 KNN 那么敏感。
3. 标准化应只使用训练集统计量再应用到验证集或测试集。第一次作业可以先理解概念，后续建模单元会再展开。""",
                    },
                ),
            },
        ),
    },
    {
        "title": "【演示】第三单元：可视化、报告与课堂讨论",
        "sort_order": 30,
        "children": (
            {
                "title": "【演示】3.1 探索性数据分析报告模板",
                "sort_order": 0,
                "materials": (
                    {
                        "title": "【演示】EDA 小报告模板：从图表到结论",
                        "sort_order": 0,
                        "content": """## EDA 小报告建议结构

### 1. 数据来源与样本规模

说明使用了 `sklearn.datasets.load_wine`，包含多少行、多少个特征、多少个类别。不要只写“我加载了数据”，要让读者知道数据大致是什么。

### 2. 字段和质量检查

列出你重点观察的字段，例如 `alcohol`、`color_intensity`、`hue`、`proline`。说明是否存在缺失值、重复行，是否发现明显尺度差异。

### 3. 图表或统计结果

至少给出一种图表或一组按类别统计的表格。可选图表包括：

- 直方图：看单个字段分布；
- 箱线图：比较不同类别的字段范围；
- 散点图：观察两个字段是否能区分类别；
- 热力图：粗略观察特征相关性。

### 4. 观察结论

建议写成 2-4 条短结论，每条结论都对应一个统计结果或图表。例如：

> 类别 0 的 `proline` 均值高于另外两类，因此该字段可能对分类有帮助。

### 5. 遇到的问题

真实报告可以写问题。比如图表字体、依赖安装、Notebook 内核、截图不清晰等，只要说明处理方式即可。""",
                    },
                    {
                        "title": "【演示】第 3 周课堂讨论记录：哪些特征可能有用",
                        "sort_order": 10,
                        "content": """## 课堂讨论记录

本记录模拟课程运行一段时间后的资料沉淀，便于部署后检查资料树、材料详情和讨论入口。

### 讨论问题

如果只允许选择 3 个字段做一个很粗略的葡萄酒类别判断，你会先选哪些字段？

### 课堂归纳

多数同学优先选择了：

1. `proline`：数值范围大，按类别看均值差异较明显；
2. `color_intensity`：直方图和箱线图容易观察差异；
3. `hue` 或 `flavanoids`：与颜色、化学成分相关，散点图中可能有一定区分度。

### 教师补充

字段“看起来有差异”不等于模型一定表现好。后续课程会使用训练集、验证集和交叉验证来判断特征组合是否真正有效。第一次作业只需要把观察过程写清楚。""",
                    },
                ),
            },
        ),
    },
)


def _ensure_demo_llm_assistant_user(db: Session) -> User:
    sys_user = db.query(User).filter(User.username == _SYSTEM_LLM_ASSISTANT_USERNAME).first()
    if sys_user:
        sys_user.real_name = "智能助教"
        sys_user.role = UserRole.TEACHER.value
        sys_user.is_active = False
        return sys_user
    sys_user = User(
        username=_SYSTEM_LLM_ASSISTANT_USERNAME,
        hashed_password=get_password_hash("__demo_llm_assistant__"),
        real_name="智能助教",
        role=UserRole.TEACHER.value,
        is_active=False,
    )
    db.add(sys_user)
    db.flush()
    return sys_user


def _user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def _ensure_course_discussion_entry(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    subject_id: int,
    class_id: int,
    author_user_id: int,
    body: str,
    message_kind: str = "human",
    llm_invocation: bool = False,
    created_at: datetime | None = None,
) -> CourseDiscussionEntry:
    exists = (
        db.query(CourseDiscussionEntry)
        .filter(
            CourseDiscussionEntry.target_type == target_type,
            CourseDiscussionEntry.target_id == target_id,
            CourseDiscussionEntry.subject_id == subject_id,
            CourseDiscussionEntry.class_id == class_id,
            CourseDiscussionEntry.author_user_id == author_user_id,
            CourseDiscussionEntry.body == body,
        )
        .first()
    )
    if exists:
        return exists
    entry = CourseDiscussionEntry(
        target_type=target_type,
        target_id=target_id,
        subject_id=subject_id,
        class_id=class_id,
        author_user_id=author_user_id,
        body=body,
        body_format="markdown",
        linked_targets=[],
        message_kind=message_kind,
        llm_invocation=llm_invocation,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def _ensure_demo_discussion_job(
    db: Session,
    *,
    subject_id: int,
    class_id: int,
    target_type: str,
    target_id: int,
    requester: User,
    requester_student_id: int | None,
    user_entry: CourseDiscussionEntry,
    assistant_entry: CourseDiscussionEntry,
) -> None:
    exists = (
        db.query(DiscussionLLMJob)
        .filter(
            DiscussionLLMJob.user_entry_id == user_entry.id,
            DiscussionLLMJob.assistant_entry_id == assistant_entry.id,
        )
        .first()
    )
    if exists:
        exists.status = "success"
        exists.error_message = None
        exists.finished_at = assistant_entry.created_at
        return
    db.add(
        DiscussionLLMJob(
            subject_id=subject_id,
            class_id=class_id,
            target_type=target_type,
            target_id=target_id,
            requester_user_id=requester.id,
            requester_student_id=requester_student_id,
            user_entry_id=user_entry.id,
            assistant_entry_id=assistant_entry.id,
            status="success",
            error_message=None,
            created_at=user_entry.created_at,
            finished_at=assistant_entry.created_at,
        )
    )


def _ensure_learning_note(
    db: Session,
    *,
    owner: User,
    course: Subject,
    title: str,
    description: str,
    resource_title: str,
    resource_content: str,
    visibility: str = "course",
) -> LearningNote:
    note = (
        db.query(LearningNote)
        .filter(
            LearningNote.owner_user_id == owner.id,
            LearningNote.subject_id == course.id,
            LearningNote.title == title,
        )
        .first()
    )
    if not note:
        note = LearningNote(
            title=title,
            description=description,
            owner_user_id=owner.id,
            subject_id=course.id,
            visibility=visibility,
            source_subject_id=course.id,
            copied_materials=False,
        )
        db.add(note)
        db.flush()
    else:
        note.description = description
        note.visibility = visibility

    chapter = (
        db.query(LearningNoteChapter)
        .filter(LearningNoteChapter.note_id == note.id, LearningNoteChapter.parent_id.is_(None))
        .order_by(LearningNoteChapter.id.asc())
        .first()
    )
    if not chapter:
        chapter = LearningNoteChapter(note_id=note.id, title="课堂整理", sort_order=0)
        db.add(chapter)
        db.flush()

    res = (
        db.query(LearningNoteResource)
        .filter(LearningNoteResource.note_id == note.id, LearningNoteResource.title == resource_title)
        .first()
    )
    if not res:
        db.add(
            LearningNoteResource(
                note_id=note.id,
                chapter_id=chapter.id,
                title=resource_title,
                content=resource_content,
                content_format="markdown",
                sort_order=0,
            )
        )
    else:
        res.chapter_id = chapter.id
        res.content = resource_content
        res.content_format = "markdown"
    return note


def _ensure_learning_note_discussion_entry(
    db: Session,
    *,
    note_id: int,
    author_user_id: int,
    body: str,
    message_kind: str = "human",
    llm_invocation: bool = False,
    created_at: datetime | None = None,
) -> LearningNoteDiscussionEntry:
    exists = (
        db.query(LearningNoteDiscussionEntry)
        .filter(
            LearningNoteDiscussionEntry.note_id == note_id,
            LearningNoteDiscussionEntry.author_user_id == author_user_id,
            LearningNoteDiscussionEntry.body == body,
        )
        .first()
    )
    if exists:
        return exists
    entry = LearningNoteDiscussionEntry(
        note_id=note_id,
        author_user_id=author_user_id,
        body=body,
        body_format="markdown",
        linked_targets=[],
        message_kind=message_kind,
        llm_invocation=llm_invocation,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


_HOMEWORK_TITLE = "数据挖掘第一次作业：Python 环境、NumPy/Pandas 基础与 Wine 数据探索"

_HOMEWORK_CONTENT = """本次作业是数据挖掘课程的第一次实践作业，目标是帮助大家完成 Python 数据分析环境的基本准备，并初步熟悉 NumPy、Pandas、Matplotlib、Seaborn 和 sklearn 等常用工具。

本次作业不要求大家已经掌握复杂机器学习模型，重点是能够把 Python 数据分析流程跑通，并能够用自己的语言解释基本结果。

一、Python 环境与基础运行

请完成以下任务，并在提交内容中展示你的完成情况：

1. 说明你使用的 Python 环境，例如 Anaconda、Jupyter Notebook、VS Code、Google Colab、课程服务器或其他在线 Python 环境。
2. 成功运行一个简单的 Python 程序，例如输出 Hello Python。
3. 尝试导入以下常用库中的若干个：
   - numpy
   - pandas
   - matplotlib
   - seaborn
   - sklearn

如果你在环境配置过程中遇到问题，也可以把错误信息、解决过程或自己的理解写出来。第一次作业更重视尝试和过程，不要求所有同学的环境完全一致。

二、概念理解题

请用自己的话回答以下问题：

1. NumPy 在数据分析或数据挖掘中的作用是什么？
2. Pandas 在数据分析或数据挖掘中的作用是什么？
3. NumPy 数组和 Pandas DataFrame 分别适合处理什么类型的问题？
4. 请解释以下 Pandas 操作的大致含义：

   df.loc[0:10, ['age', 'score']]

   df[df['age'] > 20]

   df.groupby('gender')['score'].mean()

不要求回答非常理论化，只要能够体现你理解这些操作在做什么即可。

三、Wine 数据集基础操作

请使用 sklearn.datasets.load_wine 加载 Wine 数据集，并完成基础数据探索。

建议完成以下任务：

1. 加载 Wine 数据集。
2. 将数据转换为 Pandas DataFrame。
3. 添加 target 或 target_name 列，用于表示样本类别。
4. 查看数据前 5 行。
5. 查看数据的基本信息或描述性统计结果，例如 head()、info()、describe()。
6. 选取若干个你认为重要或感兴趣的特征进行分析。

推荐关注以下特征：

- alcohol
- malic_acid
- color_intensity
- hue
- proline

你可以分析全部推荐特征，也可以选择其中几个进行分析。

四、简单可视化与观察结论

请对 Wine 数据集进行简单可视化分析。

可选图表包括但不限于：

1. 直方图；
2. 箱线图；
3. 散点图；
4. 类别分布图；
5. pairplot；
6. 相关系数热力图。

至少完成一种可视化即可。如果由于环境问题无法正常显示图片，也可以使用统计表格和文字说明代替。

请根据统计结果或可视化结果，用自己的话写出至少 2 到 3 条观察结论。例如：

1. 不同类别葡萄酒在哪些特征上可能存在差异；
2. 哪些特征的数值范围较大；
3. 哪些特征可能有助于区分不同类别；
4. 是否发现某些特征存在明显分布差异。

五、NumPy 标准化练习

请尝试实现一个简单的标准化函数 standardize(x)。

函数目标是把一维数值数组转换为均值接近 0、标准差接近 1 的形式。

参考形式如下：

def standardize(x):
    '''
    输入：一维 numpy 数组 x
    输出：标准化后的数组
    '''
    return (x - x.mean()) / x.std()

请完成以下任务：

1. 从 Wine 数据集中选取一个数值特征，例如 alcohol。
2. 将该特征转换为 NumPy 数组。
3. 使用 standardize(x) 或其他等价方式进行标准化。
4. 查看标准化后的均值和标准差。
5. 用文字解释标准化的作用。

如果你使用 sklearn.preprocessing.StandardScaler 完成标准化，也可以接受，但建议尽量理解手写公式的含义。

六、思考题：特征尺度与建模

Wine 数据集中，不同化学成分的数值范围差异较大。例如 proline 的数值通常远大于 alcohol。

请回答：

1. 如果直接把这些原始特征输入到某些机器学习模型中，可能会出现什么问题？
2. 为什么很多机器学习模型需要进行标准化或归一化？
3. 请举出一个对特征尺度比较敏感的模型，并简单说明原因。

可以举的模型包括但不限于：

- KNN
- K-Means
- SVM
- 逻辑回归
- 神经网络

七、拓展练习，选做加分

以下拓展练习为选做内容，不做不扣分，完成后可以酌情加分。

选项 A：Iris 数据集分析

1. 使用 sklearn.datasets.load_iris 加载 Iris 数据集。
2. 构建 DataFrame，并添加 target_name 列。
3. 按类别计算各特征的平均值。
4. 画出至少一张图表，例如箱线图、散点图或 pairplot。
5. 简要说明哪些特征可能有助于区分不同类别。

选项 B：自选公开 CSV 数据集

1. 从 Kaggle、UCI 或其他公开来源选择一个小型 CSV 数据集。
2. 使用 pandas 读取数据。
3. 完成 head()、info()、describe() 等基础查看。
4. 至少绘制一张简单图表。
5. 用不超过 200 字写一段迷你 EDA 报告，说明数据集是什么、有哪些有意思的特征、适合做什么类型的数据挖掘任务。

提交建议：

本次作业推荐提交 Jupyter Notebook 文件（.ipynb）或 PDF 报告。

推荐提交形式：

1. .ipynb 文件：适合展示代码、运行结果、图表和文字说明；
2. PDF 报告：适合展示整理后的实验过程和结论；
3. 也可以同时提交 .ipynb 和 PDF。

如果暂时不熟悉 Notebook 或 PDF，也可以提交 .py 文件、Word 文档、Markdown 文档、截图或压缩包。只要提交内容能够清楚展示你的完成过程和结果即可。

推荐文件命名格式：

学号_姓名_数据挖掘第一次作业.ipynb

或：

学号_姓名_数据挖掘第一次作业.pdf

例如：

20260001_张三_数据挖掘第一次作业.ipynb
20260001_张三_数据挖掘第一次作业.pdf

文件命名不规范一般不会严重扣分，但建议大家尽量按照格式提交，方便教师整理和查看。"""

_RUBRIC_TEXT_STUDENT = """本次作业满分 100。学生可见的评分导向：是否完成 Python 环境与 Wine 数据集的基本探索流程，能否用自己的话解释 NumPy/Pandas 的常见用途与若干基础操作，是否能给出至少一种合理的可视化或描述性统计小结，并简述标准化或特征尺度的直观意义。详细分项分值与加分细则仅供教师与自动评分模型内部参照，勿要求学生背诵逐项配分表。"""

_RUBRIC_TEXT_STAFF_ONLY = """请根据以下标准评分，总分 100 分。评分时应以鼓励学生完成第一次数据挖掘实践为主，重点关注学生是否动手完成了基本流程，是否能够展示代码、结果和自己的理解。不要过度强调提交格式、图表美观程度或答案是否完全一致。

一、Python 环境与基础运行，20 分

1. 能说明自己使用的 Python 环境，6 分
   - 可以是 Anaconda、Jupyter Notebook、VS Code、Google Colab、课程服务器或其他在线 Python 环境。
   - 不要求所有学生使用完全相同的环境。

2. 能成功运行基础 Python 程序，4 分
   - 例如输出 Hello Python，或运行其他简单 Python 代码。

3. 能成功导入常用数据分析库中的大部分，5 分
   - 包括 numpy、pandas、matplotlib、seaborn、sklearn 等。
   - 不要求所有库都必须成功，只要能够体现学生进行了环境准备即可。

4. 能简单说明环境配置过程、使用方式或遇到的问题，5 分
   - 如果环境配置失败，但学生清楚记录了尝试过程、错误信息或解决思路，也可以酌情给分。

二、概念理解题，20 分

1. 能用自己的话说明 NumPy 的基本作用，5 分
   - 例如用于数组计算、矩阵运算、数值处理等。

2. 能用自己的话说明 Pandas 的基本作用，5 分
   - 例如用于表格数据处理、数据清洗、缺失值处理、字段选择、条件筛选、分组统计等。

3. 能大致区分 NumPy 数组和 Pandas DataFrame 的使用场景，5 分
   - 不要求表述严格，只要方向正确即可。

4. 能基本解释 loc、条件筛选、groupby 聚合等 Pandas 操作，5 分
   - df.loc[0:10, ['age', 'score']]：选择部分行和指定列；
   - df[df['age'] > 20]：筛选 age 大于 20 的行；
   - df.groupby('gender')['score'].mean()：按 gender 分组后计算 score 平均值。
   - 学生用自己的语言解释正确即可，不必逐字一致。

三、Wine 数据集基础操作，25 分

1. 能成功加载 Wine 数据集，或使用其他合理数据集完成类似分析，5 分。

2. 能将数据整理成表格形式，例如 Pandas DataFrame，5 分。

3. 能查看数据前几行、字段信息、类别信息或基本统计信息，5 分。

4. 能选取若干特征进行分析，5 分。
   - 推荐特征包括 alcohol、malic_acid、color_intensity、hue、proline。
   - 如果学生没有严格使用全部推荐特征，但完成了类似分析，也可酌情给分。

5. 能使用 describe()、value_counts()、groupby() 或其他方式进行基础统计分析，5 分。

四、简单可视化与观察结论，15 分

1. 能完成至少一种合理的数据可视化，6 分。
   - 可以是直方图、箱线图、散点图、类别分布图、pairplot、热力图等。
   - 如果图表显示不完整，但代码和思路基本正确，也可以酌情给分。

2. 能结合统计结果或图表写出至少 2 到 3 条观察结论，6 分。
   - 结论可以涉及类别差异、特征分布、特征尺度、可能有用的分类特征等。

3. 能将图表或统计结果与文字说明对应起来，3 分。
   - 不要求分析很深入，只要不是单纯贴代码即可。

五、NumPy 标准化练习，10 分

1. 能尝试实现 standardize(x) 函数，或使用等价方法完成标准化，4 分。
   - 手写函数、NumPy 运算或 StandardScaler 均可接受。

2. 能对某个数值特征进行标准化处理，2 分。

3. 能查看或说明标准化后均值接近 0、标准差接近 1，2 分。

4. 能用自己的话解释标准化的作用，2 分。
   - 例如减少不同量纲和数值范围对模型训练的影响。

六、特征尺度与建模思考题，10 分

1. 能说明不同特征数值范围差异可能带来的问题，4 分。
   - 例如数值范围大的特征可能在距离计算或优化过程中占据更大影响。

2. 能解释为什么需要标准化或归一化，3 分。

3. 能举出一个对特征尺度敏感的模型并简单说明原因，3 分。
   - 例如 KNN、K-Means、SVM、逻辑回归、神经网络等。

七、表达与完成度，5 分

1. 作业整体结构较清楚，2 分。

2. 代码、截图、文字说明或运行结果能够基本对应，2 分。

3. 提交内容能够让教师或自动评分系统判断学生完成情况，1 分。

八、拓展练习加分项，最多加 10 分

拓展练习为选做内容，不做不扣分。完成 Iris 数据集分析或自选公开 CSV 数据集分析的学生，可以根据完成情况加 1 到 10 分。

1. 完成一个额外数据集的读取和基本查看，加 3 分。
2. 完成描述性统计、分组统计或类似分析，加 2 分。
3. 完成至少一张额外图表，加 2 分。
4. 写出简短但合理的分析结论，加 3 分。

如果系统支持超过满分，可以允许最高 110 分。如果系统不支持超过满分，则加分项可以用于弥补前面的小失误，但最终成绩不超过 100 分。

宽松评分原则：

1. 本次作业是第一次实践作业，评分应以鼓励学生动手为主。
2. 推荐提交 .ipynb 或 PDF，但不强制限定提交形式。
3. 没有提交 .ipynb 不应直接大幅扣分，只要提交内容能够展示代码、结果或分析过程即可。
4. 图表数量不足时不应大幅扣分，只要有基本统计分析或文字解释即可酌情给分。
5. 代码存在小错误但整体思路清楚，可以少量扣分，不应直接给低分。
6. 文件命名不规范一般只提醒，不作为主要扣分项；严重无法识别身份时再酌情扣 1 到 2 分。
7. 学生如果使用了 Colab、在线平台、课程服务器或其他 Python 环境，也应视为有效完成。
8. 学生如果使用了其他合理数据集完成类似流程，也可以酌情给分。
9. 只有在几乎没有完成主要任务、内容明显与作业无关、完全无法判断完成情况，或存在明显大段抄袭时，才应给较低分。
10. 对于认真完成主要任务的学生，建议分数集中在 85 分以上。"""

_REFERENCE_OR_APPROACH = """（教师侧核对要点）典型思路示例：使用 sklearn.datasets.load_wine 载入数据；转换为 pandas.DataFrame 并查看 head()/info()/describe()；可按类别或特征做简单可视化（如箱线图、直方图）；标准化可用手写 (x−mean)/std 或 sklearn.preprocessing.StandardScaler。学生表述可与示例不完全一致，只要流程合理、结论与图表相符即可。"""


def _get_or_create_demo_chapter(
    db: Session,
    *,
    subject_id: int,
    parent_id: int | None,
    title: str,
    sort_order: int,
) -> CourseMaterialChapter:
    chapter = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == subject_id,
            CourseMaterialChapter.parent_id == parent_id,
            CourseMaterialChapter.title == title,
            CourseMaterialChapter.is_uncategorized.is_(False),
        )
        .first()
    )
    if chapter:
        if chapter.sort_order != sort_order:
            chapter.sort_order = sort_order
        return chapter
    chapter = CourseMaterialChapter(
        subject_id=subject_id,
        parent_id=parent_id,
        title=title,
        sort_order=sort_order,
        is_uncategorized=False,
    )
    db.add(chapter)
    db.flush()
    return chapter


def _ensure_demo_material(
    db: Session,
    *,
    subject: Subject,
    class_id: int,
    created_by: int,
    chapter_id: int,
    title: str,
    content: str,
    sort_order: int,
) -> None:
    material = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.subject_id == subject.id, CourseMaterial.title == title)
        .first()
    )
    if not material:
        material = CourseMaterial(
            title=title,
            content=content,
            content_format="markdown",
            class_id=class_id,
            subject_id=subject.id,
            created_by=created_by,
        )
        db.add(material)
        db.flush()
    else:
        material.content = content
        material.content_format = "markdown"
        material.class_id = class_id
        material.created_by = material.created_by or created_by

    exists_sec = (
        db.query(CourseMaterialSection)
        .filter(CourseMaterialSection.material_id == material.id, CourseMaterialSection.chapter_id == chapter_id)
        .first()
    )
    if not exists_sec:
        db.add(CourseMaterialSection(material_id=material.id, chapter_id=chapter_id, sort_order=sort_order))
    elif exists_sec.sort_order != sort_order:
        exists_sec.sort_order = sort_order


def _ensure_homework_link_for_title(
    db: Session,
    *,
    subject_id: int,
    chapter_id: int,
    homework_title_contains: str,
    sort_order: int,
) -> None:
    homework = (
        db.query(Homework)
        .filter(Homework.subject_id == subject_id, Homework.title.contains(homework_title_contains))
        .first()
    )
    _ensure_demo_homework_link(
        db,
        chapter_id=chapter_id,
        homework_id=homework.id if homework else None,
        sort_order=sort_order,
    )


def _ensure_demo_homework_link(
    db: Session,
    *,
    chapter_id: int,
    homework_id: int | None,
    sort_order: int,
) -> None:
    if homework_id is None:
        return
    exists = (
        db.query(CourseMaterialHomeworkLink)
        .filter(
            CourseMaterialHomeworkLink.chapter_id == chapter_id,
            CourseMaterialHomeworkLink.homework_id == homework_id,
        )
        .first()
    )
    if exists:
        exists.sort_order = sort_order
        return
    db.add(CourseMaterialHomeworkLink(chapter_id=chapter_id, homework_id=homework_id, sort_order=sort_order))


def _seed_course_material_tree(
    db: Session,
    *,
    course: Subject,
    class_id: int,
    teacher_id: int,
    tree: tuple[dict, ...],
) -> None:
    def walk(nodes: tuple[dict, ...], parent_id: int | None = None) -> None:
        for node in nodes:
            chapter = _get_or_create_demo_chapter(
                db,
                subject_id=course.id,
                parent_id=parent_id,
                title=str(node["title"]),
                sort_order=int(node.get("sort_order", 0)),
            )
            for material in node.get("materials", ()):
                _ensure_demo_material(
                    db,
                    subject=course,
                    class_id=class_id,
                    created_by=teacher_id,
                    chapter_id=chapter.id,
                    title=str(material["title"]),
                    content=str(material["content"]),
                    sort_order=int(material.get("sort_order", 0)),
                )
            for homework_link in node.get("homework_links", ()):
                _ensure_homework_link_for_title(
                    db,
                    subject_id=course.id,
                    chapter_id=chapter.id,
                    homework_title_contains=str(homework_link["title_contains"]),
                    sort_order=int(homework_link.get("sort_order", 0)),
                )
            walk(tuple(node.get("children", ())), chapter.id)

    walk(tuple(tree))


def _seed_demo_material_chapters(db: Session, *, course: Subject, class_id: int, teacher_id: int) -> None:
    """Richer multi-week outline and materials for the required demo course."""
    _seed_course_material_tree(
        db,
        course=course,
        class_id=class_id,
        teacher_id=teacher_id,
        tree=tuple(_DEMO_REQUIRED_MATERIAL_TREE),
    )


def _get_or_create_uncategorized_chapter(db: Session, *, subject_id: int) -> CourseMaterialChapter:
    unc = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == subject_id,
            CourseMaterialChapter.is_uncategorized.is_(True),
        )
        .first()
    )
    if unc:
        return unc
    unc = CourseMaterialChapter(
        subject_id=subject_id,
        parent_id=None,
        title="未分类",
        sort_order=0,
        is_uncategorized=True,
    )
    db.add(unc)
    db.flush()
    return unc


def _ensure_elective_enrollments_for_student_nos(
    db: Session,
    *,
    subject_id: int,
    class_id: int,
    student_nos: tuple[str, ...],
) -> None:
    """Idempotent: insert `CourseEnrollment` rows for named roster students (elective picks)."""
    roster = {row.student_no: row for row in db.query(Student).filter(Student.class_id == class_id).all() if row.student_no}
    for no in student_nos:
        st = roster.get(no)
        if not st:
            continue
        exists = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == st.id)
            .first()
        )
        if exists:
            continue
        db.add(
            CourseEnrollment(
                subject_id=subject_id,
                student_id=st.id,
                class_id=class_id,
                enrollment_type="elective",
                can_remove=True,
            )
        )
    db.flush()


def _seed_llm_elective_course(
    db: Session,
    *,
    teacher: User,
    klass: Class,
    semester: Semester | None,
) -> None:
    """Elective on the same demo class; students self-enroll (no roster-wide auto enrollment)."""
    course = (
        db.query(Subject)
        .filter(
            Subject.name == _LLM_COURSE_NAME,
            Subject.teacher_id == teacher.id,
            Subject.course_type == "elective",
        )
        .first()
    )
    if not course:
        course = Subject(
            name=_LLM_COURSE_NAME,
            teacher_id=teacher.id,
            class_id=None,
            semester_id=semester.id if semester else None,
            semester=semester.name if semester else None,
            course_type="elective",
            status="active",
            description=_LLM_COURSE_DESCRIPTION,
        )
        db.add(course)
        db.flush()
        print(f"Created demo elective course '{_LLM_COURSE_NAME}'.")
    else:
        course.course_type = "elective"
        course.class_id = None
        course.status = "active"
        course.description = _LLM_COURSE_DESCRIPTION
        print(f"Demo elective '{_LLM_COURSE_NAME}' already exists; refreshed fields.")
    _ensure_demo_course_time(
        course,
        weekly_schedule=_LLM_COURSE_TIMES,
        weeks=12,
    )

    _ensure_demo_subject_llm_binding(
        db,
        subject_id=course.id,
        teacher_id=teacher.id,
        enable_auto_grading=True,
    )

    _seed_demo_grade_weights(db, course=course)
    unc = _get_or_create_uncategorized_chapter(db, subject_id=course.id)
    _ensure_elective_enrollments_for_student_nos(
        db,
        subject_id=course.id,
        class_id=klass.id,
        student_nos=_LLM_ELECTIVE_ENROLLED_STUDENT_NOS,
    )

    mat = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.subject_id == course.id, CourseMaterial.title == _LLM_MATERIAL_TITLE)
        .first()
    )
    if not mat:
        mat = CourseMaterial(
            title=_LLM_MATERIAL_TITLE,
            content=_LLM_MATERIAL_CONTENT,
            class_id=klass.id,
            subject_id=course.id,
            created_by=teacher.id,
        )
        db.add(mat)
        db.flush()
        exists_sec = (
            db.query(CourseMaterialSection)
            .filter(CourseMaterialSection.material_id == mat.id, CourseMaterialSection.chapter_id == unc.id)
            .first()
        )
        if not exists_sec:
            db.add(CourseMaterialSection(material_id=mat.id, chapter_id=unc.id, sort_order=0))
        print("Created demo LLM course material.")
    else:
        mat.content = _LLM_MATERIAL_CONTENT

    due = datetime.now(timezone.utc) + timedelta(days=21)
    hw = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _LLM_HOMEWORK_TITLE)
        .first()
    )
    if not hw:
        db.add(
            Homework(
                title=_LLM_HOMEWORK_TITLE,
                content=_LLM_HOMEWORK_CONTENT,
                class_id=klass.id,
                subject_id=course.id,
                due_date=due,
                max_score=100,
                grade_precision="integer",
                auto_grading_enabled=True,
                rubric_text=_LLM_RUBRIC_TEXT,
                reference_answer=None,
                response_language="zh-CN",
                allow_late_submission=True,
                late_submission_affects_score=False,
                max_submissions=3,
                created_by=teacher.id,
            )
        )
        print("Created demo LLM homework.")
    else:
        hw.content = _LLM_HOMEWORK_CONTENT
        hw.rubric_text = _LLM_RUBRIC_TEXT
        hw.auto_grading_enabled = True
        hw.due_date = hw.due_date or due

    _ensure_demo_homework_link(
        db,
        chapter_id=unc.id,
        homework_id=hw.id if hw else None,
        sort_order=0,
    )

    hw_row = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _LLM_HOMEWORK_TITLE)
        .first()
    )
    _seed_prefilled_submissions_for_homework(
        db,
        homework_row=hw_row,
        klass=klass,
        student_nos=_LLM_PREFILL_STUDENT_NOS,
        bodies=_LLM_PREFILL_BODIES,
        log_label="demo LLM prefilled submissions (stu1, stu3)",
    )


def _seed_probability_elective_course(
    db: Session,
    *,
    teacher_pro: User,
    klass: Class,
    semester: Semester | None,
) -> None:
    """Elective probability theory demo: partial enrollments + Markdown/LaTeX-rich material and homework."""
    course = (
        db.query(Subject)
        .filter(
            Subject.name == _PROB_COURSE_NAME,
            Subject.teacher_id == teacher_pro.id,
            Subject.course_type == "elective",
        )
        .first()
    )
    if not course:
        course = Subject(
            name=_PROB_COURSE_NAME,
            teacher_id=teacher_pro.id,
            class_id=None,
            semester_id=semester.id if semester else None,
            semester=semester.name if semester else None,
            course_type="elective",
            status="active",
            description=_PROB_COURSE_DESCRIPTION,
        )
        db.add(course)
        db.flush()
        print(f"Created demo elective course '{_PROB_COURSE_NAME}'.")
    else:
        course.course_type = "elective"
        course.class_id = None
        course.status = "active"
        course.description = _PROB_COURSE_DESCRIPTION
        print(f"Demo elective '{_PROB_COURSE_NAME}' already exists; refreshed fields.")
    _ensure_demo_course_time(
        course,
        weekly_schedule=_PROB_COURSE_TIMES,
        weeks=13,
    )

    _ensure_demo_subject_llm_binding(
        db,
        subject_id=course.id,
        teacher_id=teacher_pro.id,
        enable_auto_grading=True,
    )

    _seed_demo_grade_weights(db, course=course)

    _ensure_elective_enrollments_for_student_nos(
        db,
        subject_id=course.id,
        class_id=klass.id,
        student_nos=_PROB_ELECTIVE_ENROLLED_STUDENT_NOS,
    )

    due = datetime.now(timezone.utc) + timedelta(days=18)
    hw = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _PROB_HOMEWORK_TITLE)
        .first()
    )
    if not hw:
        db.add(
            Homework(
                title=_PROB_HOMEWORK_TITLE,
                content=_PROB_HOMEWORK_CONTENT,
                content_format="markdown",
                class_id=klass.id,
                subject_id=course.id,
                due_date=due,
                max_score=100,
                grade_precision="integer",
                auto_grading_enabled=True,
                rubric_text=_PROB_RUBRIC_STUDENT,
                rubric_staff_only=_PROB_RUBRIC_STAFF_ONLY,
                reference_answer=_PROB_REFERENCE_OR_APPROACH,
                response_language="zh-CN",
                allow_late_submission=True,
                late_submission_affects_score=False,
                max_submissions=3,
                created_by=teacher_pro.id,
            )
        )
        print("Created demo probability homework.")
    else:
        hw.content = _PROB_HOMEWORK_CONTENT
        hw.content_format = "markdown"
        hw.rubric_text = _PROB_RUBRIC_STUDENT
        hw.rubric_staff_only = _PROB_RUBRIC_STAFF_ONLY
        hw.reference_answer = _PROB_REFERENCE_OR_APPROACH
        hw.auto_grading_enabled = True
        hw.due_date = hw.due_date or due

    hw_row = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _PROB_HOMEWORK_TITLE)
        .first()
    )
    hw2_due = datetime.now(timezone.utc) + timedelta(days=28)
    hw2 = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _PROB_HOMEWORK_TWO_TITLE)
        .first()
    )
    if not hw2:
        db.add(
            Homework(
                title=_PROB_HOMEWORK_TWO_TITLE,
                content=_PROB_HOMEWORK_TWO_CONTENT,
                content_format="markdown",
                class_id=klass.id,
                subject_id=course.id,
                due_date=hw2_due,
                max_score=100,
                grade_precision="integer",
                auto_grading_enabled=True,
                rubric_text=_PROB_HOMEWORK_TWO_RUBRIC_STUDENT,
                rubric_staff_only=_PROB_HOMEWORK_TWO_RUBRIC_STAFF_ONLY,
                reference_answer=_PROB_HOMEWORK_TWO_REFERENCE,
                response_language="zh-CN",
                allow_late_submission=True,
                late_submission_affects_score=False,
                max_submissions=4,
                created_by=teacher_pro.id,
            )
        )
        print("Created demo probability homework (second assignment).")
    else:
        hw2.content = _PROB_HOMEWORK_TWO_CONTENT
        hw2.content_format = "markdown"
        hw2.rubric_text = _PROB_HOMEWORK_TWO_RUBRIC_STUDENT
        hw2.rubric_staff_only = _PROB_HOMEWORK_TWO_RUBRIC_STAFF_ONLY
        hw2.reference_answer = _PROB_HOMEWORK_TWO_REFERENCE
        hw2.auto_grading_enabled = True
        hw2.due_date = hw2.due_date or hw2_due
        hw2.max_submissions = hw2.max_submissions if hw2.max_submissions is not None else 4

    _seed_course_material_tree(
        db,
        course=course,
        class_id=klass.id,
        teacher_id=teacher_pro.id,
        tree=tuple(_PROB_CHAPTER_TREE),
    )

    prob_unc = _get_or_create_uncategorized_chapter(db, subject_id=course.id)
    _ensure_demo_material(
        db,
        subject=course,
        class_id=klass.id,
        created_by=teacher_pro.id,
        chapter_id=prob_unc.id,
        title="未归档补充阅读：概率术语速查",
        content="## 未归档补充阅读\n\n这是一条故意留在未归档目录中的演示资料，用于验证学生阅读页里的未归档入口。",
        sort_order=90,
    )
    _ensure_demo_homework_link(
        db,
        chapter_id=prob_unc.id,
        homework_id=hw2.id if hw2 else None,
        sort_order=90,
    )

    hw2_row = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _PROB_HOMEWORK_TWO_TITLE)
        .first()
    )
    _seed_prefilled_submissions_for_homework(
        db,
        homework_row=hw_row,
        klass=klass,
        student_nos=_PROB_PREFILL_STUDENT_NOS,
        bodies=_PROB_PREFILL_BODIES,
        log_label="demo probability prefilled submissions (stu1–stu2)",
    )
    _seed_prefilled_submissions_for_homework(
        db,
        homework_row=hw2_row,
        klass=klass,
        student_nos=_PROB_HOMEWORK_TWO_PREFILL_STUDENT_NOS,
        bodies=_PROB_HOMEWORK_TWO_PREFILL_BODIES,
        log_label="demo probability second-homework submissions (stu1, stu4)",
    )

    stu1_first_attempt = _ensure_additional_homework_attempt(
        db,
        homework_row=hw_row,
        klass=klass,
        student_no="stu1",
        content=r"""### 修订稿（stu1）

这次我把题2的 Bayes 推导补完整了：

1. 先算 \(P(B)=0.7\times0.85+0.3\times0.4=0.715\)；
2. 再算
\[
P(A\mid B)=\frac{0.7\times0.85}{0.715}\approx 0.832.
\]

另外补了一张事件树草图，帮助区分“已知条件”和“反推目标”。""",
        days_ago=4,
        used_llm_assist=False,
    )
    _seed_teacher_review_for_attempt(
        db,
        attempt=stu1_first_attempt,
        homework_row=hw_row,
        score=88.0,
        comment=r"""### 教师反馈

- 样本空间与 Bayes 链条已经写清楚；
- 事件记号定义比第一次草稿规范得多；
- 建议再补一行对“为什么竖线右边是已知条件”的文字说明，让读者不只看到公式。

:::tip 下一步
如果继续修订，可以把事件树和公式逐项对应起来，形成更完整的推理闭环。
:::
""",
        teacher_user_id=teacher_pro.id,
    )
    _seed_feedback_followup_attempt(
        db,
        homework_row=hw_row,
        klass=klass,
        student_no="stu1",
        prior_attempt=stu1_first_attempt,
        content=r"""### 按反馈补充（stu1）

我根据老师意见补了一句解释：

> 在 \(P(A\mid B)\) 中，竖线右边的 \(B\) 表示“已经知道发生的条件”，因此分母需要先把“已知为 B 的整体”算出来。

同时把事件树和公式一一对应标在旁边，避免把 \(P(B\mid A)\) 写反。""",
        days_ago=2,
        used_llm_assist=False,
    )

    stu2 = _student_by_no(db, klass=klass, student_no="stu2")
    stu2_attempt = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == hw_row.id,
            HomeworkAttempt.student_id == stu2.id,
        )
        .order_by(HomeworkAttempt.submitted_at.desc(), HomeworkAttempt.id.desc())
        .first()
        if hw_row and stu2
        else None
    )
    _seed_teacher_review_for_attempt(
        db,
        attempt=stu2_attempt,
        homework_row=hw_row,
        score=76.0,
        comment="""### 反馈摘要

- 公式方向基本正确，但中间推导写得偏简略；
- 建议把全概率公式单独写成一步；
- 概念题可以再明确区分“独立”与“条件化后更新信息”的差别。""",
        teacher_user_id=teacher_pro.id,
    )

    stu4 = _student_by_no(db, klass=klass, student_no="stu4")
    stu4_second_attempt = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == hw2_row.id,
            HomeworkAttempt.student_id == stu4.id,
        )
        .order_by(HomeworkAttempt.submitted_at.desc(), HomeworkAttempt.id.desc())
        .first()
        if hw2_row and stu4
        else None
    )
    _seed_teacher_review_for_attempt(
        db,
        attempt=stu4_second_attempt,
        homework_row=hw2_row,
        score=91.0,
        comment=r"""### 评分意见

1. 对 Bernoulli / Binomial 的对象区分清楚；
2. 事件树说明了“先验 \(\rightarrow\) 条件 \(\rightarrow\) 后验”的推理顺序；
3. Poisson 的解释已经提到“次数、稀有、平均发生率稳定”，较为专业。

:::note 改进建议
若再修订，可加入一个更具体的应用场景，例如“单位小时到达请求数”。
:::
""",
        teacher_user_id=teacher_pro.id,
    )


_DEMO_PREFILL_STUDENT_NOS = ("stu1", "stu2", "stu3", "stu4", "stu5")
_DEMO_PREFILL_BODIES = (
    """# 数据挖掘第一次作业提交 - stu1

## 1. 环境说明

我使用 Anaconda + Jupyter Notebook 完成本次作业。Python 版本为 3.11，能够正常导入：

```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.datasets import load_wine
from sklearn.preprocessing import StandardScaler
```

环境配置中主要遇到的问题是 Notebook 内核一开始不是 base 环境，所以 `sklearn` 导入失败。我通过重新选择 kernel 解决，并在 Notebook 首页确认解释器路径后再运行代码。

## 2. NumPy 与 Pandas 理解

NumPy 更像是数值计算底座，适合处理数组、矩阵和批量数学运算；Pandas 更像是表格数据处理工具，适合字段筛选、缺失值检查、分组统计和数据清洗。

对示例代码的理解：

- `df.loc[0:10, ['age', 'score']]`：按照标签选择第 0 到 10 行，并只保留 `age` 和 `score` 两列。
- `df[df['age'] > 20]`：条件筛选，保留年龄大于 20 的记录。
- `df.groupby('gender')['score'].mean()`：先按 `gender` 分组，再计算每组的 `score` 平均值。

## 3. Wine 数据集探索

我使用 `load_wine(as_frame=True)` 读取数据，转成 DataFrame 后得到 178 行、14 列，其中 13 个化学特征和 1 个 `target` 类别列。我额外添加了 `target_name`，便于按类别查看。

我重点观察了 `alcohol`、`color_intensity`、`hue`、`proline` 四个字段：

- `proline` 的数值范围明显大，和 `alcohol`、`hue` 不在同一尺度；
- `color_intensity` 在不同类别之间的均值有差异，可能对类别区分有帮助；
- `hue` 的范围较窄，但按类别画箱线图时能看到一定差异；
- 数据集中没有发现缺失值，`df.isna().sum().sum()` 的结果为 0。

## 4. 可视化与观察

我画了两类图：

1. `proline` 按 `target_name` 分组的箱线图；
2. `color_intensity` 与 `hue` 的散点图，并用类别上色。

观察结论：

- `proline` 在类别之间的中位数差异比较明显，可能是一个重要特征；
- `color_intensity` 与 `hue` 组合后，不同类别在散点图上有一定分离；
- 单个字段不能完全区分类别，但多个特征组合后可能更有效。

## 5. 标准化练习

我先手写了标准化函数：

```python
def standardize(x):
    return (x - x.mean()) / x.std()
```

对 `proline` 标准化后，均值接近 0，标准差接近 1。我的理解是：标准化不是改变数据本身的真实含义，而是让不同量纲的字段在模型中更公平地参与计算。KNN、K-Means、SVM 等模型比较依赖距离或尺度，因此更需要标准化。

## 6. 小结

本次作业让我熟悉了从数据读取到基础 EDA 的完整流程。后续我想继续尝试相关系数热力图，并比较标准化前后 KNN 分类效果是否有明显差异。""",
    """# 数据挖掘第一次作业提交 - stu2

## 环境与导入

我使用 VS Code + 本地虚拟环境完成。最开始 `seaborn` 没有安装，运行时报错：

```text
ModuleNotFoundError: No module named 'seaborn'
```

后来通过 `python -m pip install seaborn` 解决。当前可以导入 `numpy`、`pandas`、`matplotlib`、`seaborn` 和 `sklearn`。

## 基础概念回答

NumPy 主要用于高效数值计算，例如数组运算、均值、标准差和矩阵计算。Pandas 主要用于处理表格数据，例如读取 CSV、筛选行列、分组统计、处理缺失值。

NumPy 数组更适合纯数值矩阵，Pandas DataFrame 更适合有字段名、有不同列含义的数据表。本次 Wine 数据集更适合先用 DataFrame 查看，再在标准化时转成 NumPy 数组。

## Wine 数据集完成情况

我完成了以下步骤：

1. 使用 `load_wine()` 加载数据；
2. 把 `data` 转成 DataFrame；
3. 添加 `target` 和 `target_name`；
4. 查看 `head()`、`shape`、`describe()`；
5. 用 `groupby("target_name").mean()` 查看不同类别的均值。

我重点看了 `alcohol`、`malic_acid`、`color_intensity`、`hue`、`proline`。其中 `proline` 的范围最大，`color_intensity` 在三类之间看起来差异比较明显。

## 可视化

我画了 `alcohol` 的直方图和 `proline` 的箱线图。箱线图显示 `proline` 在不同类别之间差异比 `alcohol` 更明显。由于本地中文字体没有配置好，图标题中的中文显示不完整，所以我在报告里用文字补充说明。

## 标准化理解

我使用 `StandardScaler` 对 `proline` 做了标准化，标准化后的均值非常接近 0。我理解标准化的作用是避免数值范围大的字段在模型里过度影响距离计算。例如 KNN 会计算样本之间的距离，如果不标准化，`proline` 可能比其他字段影响更大。

## 遗留问题

我还没有完成 pairplot，因为运行较慢且图比较大。后面我会尝试只选择 3-4 个字段来画 pairplot，避免一次性画全部字段导致图太复杂。""",
    """# 数据挖掘第一次作业提交 - stu3

## 本次完成内容

我使用 Google Colab 完成了主要部分。能够运行 Python，并成功导入：

```python
import numpy as np
import pandas as pd
from sklearn.datasets import load_wine
```

`matplotlib` 可以导入，但我对画图还不熟练，所以本次主要提交了数据查看和文字分析。

## 对工具的理解

NumPy 主要处理数组，例如一列数值的平均值、最大值、最小值和标准差。Pandas 可以把数据整理成表格，更方便按列名查看，比如 `df["alcohol"]`、`df.describe()`。

我理解：

- `loc` 可以按行和列选数据；
- 条件筛选可以找出符合条件的行；
- `groupby` 可以按类别统计平均值。

## Wine 数据集探索

我用 `load_wine()` 加载数据后，看到数据有 178 条。我查看了前 5 行和 `describe()`。我注意到 `proline` 的最大值比其他字段大很多，说明不同字段的数值尺度不一样。

按类别看均值时，我发现 `alcohol` 和 `color_intensity` 在不同类别之间有一些差异，但我还不能判断哪个字段最重要。

## 标准化练习

我尝试对 `alcohol` 做标准化：

```python
x = df["alcohol"].to_numpy()
z = (x - x.mean()) / x.std()
```

计算后 `z.mean()` 接近 0，`z.std()` 接近 1。我的理解是，标准化可以让不同单位或不同范围的数据更容易放在一起比较。

## 没有完全完成的部分

可视化部分我只尝试了直方图，还没有整理好截图。pairplot 和热力图暂时没有完成。后续我会补做 `color_intensity` 和 `hue` 的散点图。""",
    """# 数据挖掘第一次作业提交 - stu4

## 环境

我使用学校实验服务器的 JupyterLab。服务器已经安装了大部分包，`seaborn` 也可以正常导入。提交文件名为 `stu4_wine_eda_week3.ipynb`，这里粘贴主要结论。

## 数据质量检查

读取 Wine 数据后，我先做了以下检查：

```python
df.shape
df.dtypes
df.isna().sum()
df.duplicated().sum()
```

结果显示数据没有缺失值，也没有重复行。所有化学特征基本都是数值类型，适合做描述性统计和可视化。

## 分组统计发现

我使用：

```python
df.groupby("target_name")[["alcohol", "color_intensity", "hue", "proline"]].mean()
```

观察到：

1. `proline` 的类别均值差异较大；
2. `color_intensity` 在不同类别之间也有明显变化；
3. `hue` 的数值范围较小，但和 `color_intensity` 一起看时比较有用。

## 可视化

我完成了三个图：

- `proline` 的箱线图；
- `color_intensity` 的直方图；
- `color_intensity` vs `hue` 的散点图。

散点图中三类样本不是完全分开，但大致能看到某些区域的聚集现象。我认为这说明单靠两个字段不够，但它们可能是后续分类模型中的有效特征。

## 标准化与模型思考

我分别用手写函数和 `StandardScaler` 对 `proline` 做了标准化，结果基本一致。KNN、K-Means 这类模型需要计算距离，如果不标准化，`proline` 这样范围大的特征会让距离主要由它决定。

## 额外尝试

我还试着画了相关系数热力图，发现部分化学特征之间存在较强相关性。这个部分我还没有完全理解，只是作为扩展结果放在 Notebook 最后。""",
    """# 数据挖掘第一次作业提交 - stu5

## 说明

这次作业我完成得不够完整，但已经把能做的部分整理如下。我的电脑本地环境配置失败，所以最后使用在线 Notebook 完成。

## 已完成

1. 能运行基础 Python；
2. 成功导入 `numpy` 和 `pandas`；
3. `sklearn` 在在线 Notebook 中可以导入；
4. 已经加载 Wine 数据集并转成 DataFrame；
5. 查看了 `head()` 和 `describe()`。

## 概念回答

NumPy 用于数组和数值计算，Pandas 用于表格数据处理。NumPy 更像底层计算工具，Pandas 更方便看每一列是什么、筛选数据和分组统计。

`df[df['age'] > 20]` 这种写法是条件筛选。`groupby` 是按某一列分组后计算统计量。

## 数据观察

Wine 数据集中 `proline` 的数值比很多字段大。我认为如果直接把所有字段输入模型，数值大的字段可能影响更大，所以需要标准化。

我还看到 `color_intensity` 这个字段不同样本之间差异明显，但我没有完成按类别的图表比较。

## 未完成与后续计划

没有完成正式可视化截图，也没有完成 Iris 扩展练习。我计划下次先补上 `proline` 的箱线图，再补一个按类别分组的均值表。""",
)


def _seed_prefilled_submissions_for_homework(
    db: Session,
    *,
    homework_row: Homework | None,
    klass: Class,
    student_nos: tuple[str, ...],
    bodies: tuple[str, ...],
    log_label: str = "demo prefilled homework submissions",
) -> None:
    """幂等写入少量「已提交但未打分」记录，便于演示提交列表与教师批改界面。"""
    if not homework_row:
        return
    roster = {row.student_no: row for row in db.query(Student).filter(Student.class_id == klass.id).all() if row.student_no}
    touched = False
    for idx, uname in enumerate(student_nos):
        st = roster.get(uname)
        if not st:
            continue
        exists = (
            db.query(HomeworkSubmission)
            .filter(HomeworkSubmission.homework_id == homework_row.id, HomeworkSubmission.student_id == st.id)
            .first()
        )
        if exists:
            continue
        body = bodies[idx] if idx < len(bodies) else bodies[0]
        submitted_at = datetime.now(timezone.utc) - timedelta(days=2)
        summary = HomeworkSubmission(
            homework_id=homework_row.id,
            student_id=st.id,
            subject_id=homework_row.subject_id,
            class_id=homework_row.class_id,
            content=body,
            content_format="markdown",
            submitted_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(summary)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework_row.id,
            student_id=st.id,
            subject_id=homework_row.subject_id,
            class_id=homework_row.class_id,
            submission_summary_id=summary.id,
            content=body,
            content_format="markdown",
            is_late=False,
            counts_toward_final_score=True,
            submitted_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(attempt)
        db.flush()
        summary.latest_attempt_id = attempt.id
        refresh_submission_summary(db, summary)
        touched = True
    if touched:
        print(f"Inserted {log_label} without scores.")


def _best_teacher_candidate_for_attempt(db: Session, attempt_id: int) -> HomeworkScoreCandidate | None:
    return (
        db.query(HomeworkScoreCandidate)
        .filter(
            HomeworkScoreCandidate.attempt_id == attempt_id,
            HomeworkScoreCandidate.source == "teacher",
        )
        .order_by(HomeworkScoreCandidate.created_at.desc(), HomeworkScoreCandidate.id.desc())
        .first()
    )


def _seed_teacher_review_for_attempt(
    db: Session,
    *,
    attempt: HomeworkAttempt | None,
    homework_row: Homework | None,
    score: float,
    comment: str,
    teacher_user_id: int,
) -> HomeworkScoreCandidate | None:
    if not attempt or not homework_row:
        return None
    existing = _best_teacher_candidate_for_attempt(db, attempt.id)
    if existing:
        existing.score = score
        existing.comment = comment
        existing.created_by = teacher_user_id
        existing.source_metadata = {"seed_demo": True}
        return existing
    candidate = HomeworkScoreCandidate(
        attempt_id=attempt.id,
        homework_id=homework_row.id,
        student_id=attempt.student_id,
        source="teacher",
        score=score,
        comment=comment,
        created_by=teacher_user_id,
        source_metadata={"seed_demo": True},
        created_at=attempt.updated_at or attempt.submitted_at,
        updated_at=attempt.updated_at or attempt.submitted_at,
    )
    db.add(candidate)
    db.flush()
    summary = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.id == attempt.submission_summary_id)
        .first()
    )
    if summary:
        refresh_submission_summary(db, summary)
    return candidate


def _seed_feedback_followup_attempt(
    db: Session,
    *,
    homework_row: Homework | None,
    klass: Class,
    student_no: str,
    prior_attempt: HomeworkAttempt | None,
    content: str,
    days_ago: int,
    used_llm_assist: bool = False,
) -> HomeworkAttempt | None:
    if not homework_row or not prior_attempt:
        return None
    student = (
        db.query(Student)
        .filter(Student.class_id == klass.id, Student.student_no == student_no)
        .first()
    )
    if not student:
        return None
    summary = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.homework_id == homework_row.id, HomeworkSubmission.student_id == student.id)
        .first()
    )
    if not summary:
        return None
    existing = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == homework_row.id,
            HomeworkAttempt.student_id == student.id,
            HomeworkAttempt.submission_summary_id == summary.id,
            HomeworkAttempt.submission_mode == "feedback_followup",
            HomeworkAttempt.prior_attempt_id == prior_attempt.id,
            HomeworkAttempt.content == content,
        )
        .first()
    )
    if existing:
        return existing
    submitted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    attempt = HomeworkAttempt(
        homework_id=homework_row.id,
        student_id=student.id,
        subject_id=homework_row.subject_id,
        class_id=homework_row.class_id,
        submission_summary_id=summary.id,
        content=content,
        content_format="markdown",
        attachment_name=prior_attempt.attachment_name,
        attachment_url=prior_attempt.attachment_url,
        is_late=False,
        counts_toward_final_score=True,
        used_llm_assist=used_llm_assist,
        submission_mode="feedback_followup",
        prior_attempt_id=prior_attempt.id,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(attempt)
    db.flush()
    summary.latest_attempt_id = attempt.id
    summary.content = content
    summary.content_format = "markdown"
    summary.used_llm_assist = bool(summary.used_llm_assist or used_llm_assist)
    summary.submitted_at = submitted_at
    summary.updated_at = submitted_at
    refresh_submission_summary(db, summary)
    return attempt


def _student_by_no(db: Session, *, klass: Class, student_no: str) -> Student | None:
    return (
        db.query(Student)
        .filter(Student.class_id == klass.id, Student.student_no == student_no)
        .first()
    )


def _seed_demo_prefilled_homework_submissions(db: Session, *, homework_row: Homework | None, klass: Class) -> None:
    _seed_prefilled_submissions_for_homework(
        db,
        homework_row=homework_row,
        klass=klass,
        student_nos=_DEMO_PREFILL_STUDENT_NOS,
        bodies=_DEMO_PREFILL_BODIES,
        log_label="demo prefilled homework submissions (stu1-stu5)",
    )


def _ensure_additional_homework_attempt(
    db: Session,
    *,
    homework_row: Homework | None,
    klass: Class,
    student_no: str,
    content: str,
    days_ago: int,
    used_llm_assist: bool = False,
) -> HomeworkAttempt | None:
    if not homework_row:
        return None
    student = (
        db.query(Student)
        .filter(Student.class_id == klass.id, Student.student_no == student_no)
        .first()
    )
    if not student:
        return None
    summary = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.homework_id == homework_row.id, HomeworkSubmission.student_id == student.id)
        .first()
    )
    if not summary:
        submitted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        summary = HomeworkSubmission(
            homework_id=homework_row.id,
            student_id=student.id,
            subject_id=homework_row.subject_id,
            class_id=homework_row.class_id,
            content=content,
            content_format="markdown",
            used_llm_assist=used_llm_assist,
            submitted_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(summary)
        db.flush()

    existing = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == homework_row.id,
            HomeworkAttempt.student_id == student.id,
            HomeworkAttempt.content == content,
        )
        .first()
    )
    if existing:
        return existing

    prior = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == homework_row.id,
            HomeworkAttempt.student_id == student.id,
            HomeworkAttempt.submission_summary_id == summary.id,
        )
        .order_by(HomeworkAttempt.submitted_at.desc(), HomeworkAttempt.id.desc())
        .first()
    )
    submitted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    attempt = HomeworkAttempt(
        homework_id=homework_row.id,
        student_id=student.id,
        subject_id=homework_row.subject_id,
        class_id=homework_row.class_id,
        submission_summary_id=summary.id,
        content=content,
        content_format="markdown",
        is_late=False,
        counts_toward_final_score=True,
        used_llm_assist=used_llm_assist,
        submission_mode="revision" if prior else "full",
        prior_attempt_id=prior.id if prior else None,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(attempt)
    db.flush()
    summary.latest_attempt_id = attempt.id
    summary.content = content
    summary.content_format = "markdown"
    summary.used_llm_assist = bool(summary.used_llm_assist or used_llm_assist)
    summary.submitted_at = submitted_at
    summary.updated_at = submitted_at
    refresh_submission_summary(db, summary)
    return attempt


def _seed_homework_discussion_demo(
    db: Session,
    *,
    course: Subject | None,
    homework_row: Homework | None,
    klass: Class,
    teacher: User | None,
    student_user: User | None,
    student: Student | None,
    sys_user: User,
    student_question: str,
    assistant_reply: str,
    teacher_reply: str,
    offset_days: int,
) -> None:
    if not course or not homework_row or not teacher or not student_user or not student:
        return
    base = datetime.now(timezone.utc) - timedelta(days=offset_days)
    user_entry = _ensure_course_discussion_entry(
        db,
        target_type="homework",
        target_id=homework_row.id,
        subject_id=course.id,
        class_id=klass.id,
        author_user_id=student_user.id,
        body=student_question,
        llm_invocation=True,
        created_at=base,
    )
    assistant_entry = _ensure_course_discussion_entry(
        db,
        target_type="homework",
        target_id=homework_row.id,
        subject_id=course.id,
        class_id=klass.id,
        author_user_id=sys_user.id,
        body=assistant_reply,
        message_kind="llm_assistant",
        created_at=base + timedelta(minutes=2),
    )
    _ensure_demo_discussion_job(
        db,
        subject_id=course.id,
        class_id=klass.id,
        target_type="homework",
        target_id=homework_row.id,
        requester=student_user,
        requester_student_id=student.id,
        user_entry=user_entry,
        assistant_entry=assistant_entry,
    )
    _ensure_course_discussion_entry(
        db,
        target_type="homework",
        target_id=homework_row.id,
        subject_id=course.id,
        class_id=klass.id,
        author_user_id=teacher.id,
        body=teacher_reply,
        created_at=base + timedelta(hours=3),
    )


def _seed_demo_learning_notes(db: Session, *, klass: Class, sys_user: User) -> None:
    courses = {row.name: row for row in db.query(Subject).all()}
    users = {row.username: row for row in db.query(User).filter(User.username.in_(["stu1", "stu2", "stu3"])).all()}
    teacher = _user_by_username(db, "teacher")

    note1 = _ensure_learning_note(
        db,
        owner=users["stu1"],
        course=courses[_COURSE_NAME],
        title="Wine 数据集探索笔记",
        description="stu1 对数据挖掘第一次作业的课堂笔记，包含字段观察和后续问题。",
        resource_title="第1-3周整理：字段尺度和可视化",
        resource_content="""## 已整理

- `proline` 的数值尺度明显比其他字段大，后续建模前要考虑标准化。
- `color_intensity` 和 `hue` 可以组合画散点图，观察类别差异。
- 作业报告要写环境、代码、图表和文字解释，不能只贴截图。

## 待确认

- 还不确定相关性热力图是否适合放在第一次作业里，准备先用箱线图说明差异。
""",
    )
    note1_resource = (
        db.query(LearningNoteResource)
        .filter(
            LearningNoteResource.note_id == note1.id,
            LearningNoteResource.title == "第1-3周整理：字段尺度和可视化",
        )
        .first()
    )
    if note1_resource:
        note1_resource.content = f"""## 第1-3周整理：字段尺度、卡片分层与图文表达

:::example 报告结构建议
1. 先写数据来源与样本规模。
2. 再写字段观察、图表结果和自己的解释。
3. 如果某一步没跑通，也要把错误信息和处理过程写出来。
:::

:::pricing 优先关注的字段
- `proline`：尺度大，后续建模前要考虑标准化。
- `color_intensity`：按类别看差异通常比较明显。
- `hue`：适合和 `color_intensity` 一起做散点图观察。
:::

:::note 图文混排示例
下图使用系统当前支持的标准 Markdown 图片语法插入，图片源是内置 SVG data URL，可直接随默认种子一起渲染。

![课程卡片与插图示意图]({_DEMO_NOTE_IMAGE_PATH})
:::

:::tip 当前结论
- 作业报告要写环境、代码、图表和文字解释，不能只贴截图。
- 先完成最小可复现流程，再补充更复杂的图表。
:::

:::warning 待确认
- 相关性热力图是否适合放在第一次作业里还得再观察。
- 如果图太复杂，先用箱线图说明差异会更稳妥。
:::
"""
        note1_resource.content_format = "markdown"
    _ensure_learning_note_discussion_entry(
        db,
        note_id=note1.id,
        author_user_id=users["stu1"].id,
        body="@LLM 我想把这份笔记改成作业报告提纲，应该补哪几段？",
        llm_invocation=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=3, hours=2),
    )
    _ensure_learning_note_discussion_entry(
        db,
        note_id=note1.id,
        author_user_id=sys_user.id,
        body="【智能助教】建议补三段：数据来源与样本规模、至少一张图表对应的观察结论、遇到的问题与处理方式。当前笔记已经有字段尺度观察，可以把它扩展成“为什么要标准化”的解释。",
        message_kind="llm_assistant",
        created_at=datetime.now(timezone.utc) - timedelta(days=3, hours=1, minutes=55),
    )

    note2 = _ensure_learning_note(
        db,
        owner=users["stu3"],
        course=courses[_LLM_COURSE_NAME],
        title="提示工程模板收集",
        description="stu3 记录的大语言模型课程提示模板和风险清单。",
        resource_title="新闻摘要 Prompt 草稿",
        resource_content="""## 模板

角色：你是课程助教。
任务：把新闻整理成事实要点，不添加原文没有的信息。
输出：事实要点、涉及主体、不确定信息、一句话摘要。

## 风险

- 事实核对要回到原文；
- 时间、数字、人名容易被漏掉；
- 不能把模型当作唯一资料来源。""",
    )
    _ensure_learning_note_discussion_entry(
        db,
        note_id=note2.id,
        author_user_id=users["stu3"].id,
        body="我准备把输出格式固定成四段，这样是不是会让模型更稳定？",
        created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=4),
    )
    _ensure_learning_note_discussion_entry(
        db,
        note_id=note2.id,
        author_user_id=sys_user.id,
        body="【智能助教】通常会更稳定。固定结构能减少遗漏，但也要给模型保留“原文信息不足时说明不足”的出口，避免为了填满格式而编造。",
        message_kind="llm_assistant",
        created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=3, minutes=55),
    )

    if teacher:
        note3 = _ensure_learning_note(
            db,
            owner=users["stu2"],
            course=courses[_PROB_COURSE_NAME],
            title="Bayes 公式课堂笔记",
            description="stu2 对初等概率论第一次作业的公式整理。",
            resource_title="全概率与 Bayes 的区别",
            resource_content=rf"""## 事件记号

设 \(A\) 表示第一次测验及格，\(B\) 表示第二次测验及格。

## 解题顺序

1. 先用全概率公式算 \(P(B)\)；
2. 再用 Bayes 公式算 \(P(A\mid B)\)；
3. 最后解释“已知结果反推原因”的含义。

:::example 我现在的固定顺序
1. 先写中文语义；
2. 再画事件树或列两向表；
3. 最后把公式和图示对齐。
:::

:::note 容易写反的地方
- \(P(A\mid B)\)：已知第二次及格，第一次也及格；
- \(P(B\mid A)\)：已知第一次及格，第二次也及格。
:::

:::tip 给未来自己的提醒
如果分母是“已知为 B 的整体”，就先把所有导致 \(B\) 的路径加总出来。
:::

![概率课事件树示意图]({_DEMO_NOTE_IMAGE_PATH})
""",
        )
        _ensure_learning_note_discussion_entry(
            db,
            note_id=note3.id,
            author_user_id=teacher.id,
            body="这份笔记可以再补一行事件树或表格，避免把 P(B|A) 和 P(A|B) 写反。",
            created_at=datetime.now(timezone.utc) - timedelta(days=1, hours=5),
        )

    teacher_pro = _user_by_username(db, _TEACHER_PRO_USERNAME)
    if teacher_pro and users.get("stu2"):
        teacher_note = _ensure_learning_note(
            db,
            owner=teacher_pro,
            course=courses[_PROB_COURSE_NAME],
            title="概率论课备课札记：Bayes 单元组织",
            description="teacher_pro 的授课笔记，记录课堂节奏、板书层级和反馈重点。",
            resource_title="第4周备课：事件树、表格与后验解释",
            resource_content=rf"""## 本周授课目标

:::example 板书顺序
1. 先写事件记号；
2. 再画事件树或两向表；
3. 最后把 Bayes 公式放到图示之后，强调“后验 = 先验 × 似然 / 证据”。
:::

:::note 课堂提醒
- 学生常把 \(P(A\mid B)\) 与 \(P(B\mid A)\) 写反；
- 需要反复强调“竖线右边是已知条件”；
- 讲评时要区分“思路对但步骤略简”和“事件方向根本错位”。
:::

:::tip 作业讲评安排
- 先展示一份结构清楚但计算略粗糙的答案；
- 再展示一份公式完整、解释也完整的高质量样例；
- 最后给出统一修订建议。
:::

{_PROB_NOTE_IMAGE_MARKDOWN}
""",
            visibility="course",
        )
        _ensure_learning_note_discussion_entry(
            db,
            note_id=teacher_note.id,
            author_user_id=teacher_pro.id,
            body="下次讲 Bayes 时，先让学生用中文写出“已知什么、要求什么”，再写公式，效果会更稳定。",
            created_at=datetime.now(timezone.utc) - timedelta(days=1, hours=12),
        )
        _ensure_learning_note_discussion_entry(
            db,
            note_id=teacher_note.id,
            author_user_id=users["stu2"].id,
            body="老师这份备课提示里“先图后式”的顺序很有帮助，我准备把自己的笔记也改成这个结构。",
            created_at=datetime.now(timezone.utc) - timedelta(days=1, hours=10),
        )


def _seed_demo_runtime_activity(
    db: Session,
    *,
    klass: Class,
    required_course: Subject | None,
    required_homework: Homework | None,
) -> None:
    sys_user = _ensure_demo_llm_assistant_user(db)
    teacher = _user_by_username(db, "teacher")
    teacher_pro = _user_by_username(db, _TEACHER_PRO_USERNAME)
    students = {
        row.student_no: row
        for row in db.query(Student).filter(Student.class_id == klass.id).all()
        if row.student_no
    }
    users = {
        row.username: row
        for row in db.query(User).filter(User.username.in_(["stu1", "stu2", "stu3", "stu5"])).all()
    }

    revision = """# 数据挖掘第一次作业提交 - stu1（二次修订）

根据讨论区的提醒，我补充了 `proline` 的尺度问题和一张按类别比较的文字说明。

## 新增观察

`proline` 的数值范围明显更大，如果后续使用 KNN 或 K-Means，距离计算会被它主导，所以需要标准化。

我还把 `color_intensity` 按类别做了均值比较，类别之间有差异，但不能只凭一个字段下结论。

## 本次修订

- 增加字段尺度解释；
- 补充按类别均值观察；
- 把“没有完成可视化”的说明改成后续计划。"""
    _ensure_additional_homework_attempt(
        db,
        homework_row=required_homework,
        klass=klass,
        student_no="stu1",
        content=revision,
        days_ago=1,
        used_llm_assist=True,
    )

    _seed_homework_discussion_demo(
        db,
        course=required_course,
        homework_row=required_homework,
        klass=klass,
        teacher=teacher,
        student_user=users.get("stu1"),
        student=students.get("stu1"),
        sys_user=sys_user,
        student_question="@LLM 我已经写了 Wine 数据集的 `describe()`，但不知道怎么把图表和结论连起来。",
        assistant_reply="【智能助教】可以按“图表观察 -> 可能解释 -> 作业结论”的顺序写。比如先说明 `proline` 的范围更大，再解释它可能影响距离类模型，最后说明后续建模前要标准化。",
        teacher_reply="这条建议可以采纳。请大家注意：第一次作业不要求模型准确率，重点是把观察过程写清楚。",
        offset_days=4,
    )

    llm_course = db.query(Subject).filter(Subject.name == _LLM_COURSE_NAME).first()
    llm_hw = (
        db.query(Homework)
        .filter(Homework.subject_id == llm_course.id, Homework.title == _LLM_HOMEWORK_TITLE)
        .first()
        if llm_course
        else None
    )
    _seed_homework_discussion_demo(
        db,
        course=llm_course,
        homework_row=llm_hw,
        klass=klass,
        teacher=teacher,
        student_user=users.get("stu3"),
        student=students.get("stu3"),
        sys_user=sys_user,
        student_question="@LLM 我写新闻摘要 Prompt 时，是否应该要求模型输出“未知信息”？",
        assistant_reply="【智能助教】建议保留“未知信息”或“需要查证”一栏。这样能提醒读者哪些结论来自原文，哪些需要进一步核对，减少模型为了完整输出而补充不存在信息的风险。",
        teacher_reply="本周课堂会专门看几份 Prompt 模板。请把输出格式写得可检查，不要只写“请总结”。",
        offset_days=3,
    )

    prob_course = db.query(Subject).filter(Subject.name == _PROB_COURSE_NAME).first()
    prob_hw = (
        db.query(Homework)
        .filter(Homework.subject_id == prob_course.id, Homework.title == _PROB_HOMEWORK_TITLE)
        .first()
        if prob_course
        else None
    )
    _seed_homework_discussion_demo(
        db,
        course=prob_course,
        homework_row=prob_hw,
        klass=klass,
        teacher=teacher_pro or teacher,
        student_user=users.get("stu2"),
        student=students.get("stu2"),
        sys_user=sys_user,
        student_question="@LLM Bayes 题里我经常把 P(A|B) 和 P(B|A) 写反，有没有检查方法？",
        assistant_reply="【智能助教】先用中文写清楚条件：竖线右边是“已知”。例如 P(A|B) 是“已知第二次及格，第一次也及格的概率”。写完后再代公式，可以减少方向写反。",
        teacher_reply="建议大家先画事件树，再写公式。事件树能帮助确认条件概率方向。",
        offset_days=2,
    )

    prob_hw2 = (
        db.query(Homework)
        .filter(Homework.subject_id == prob_course.id, Homework.title == _PROB_HOMEWORK_TWO_TITLE)
        .first()
        if prob_course
        else None
    )
    _seed_homework_discussion_demo(
        db,
        course=prob_course,
        homework_row=prob_hw2,
        klass=klass,
        teacher=teacher_pro or teacher,
        student_user=users.get("stu1"),
        student=students.get("stu1"),
        sys_user=sys_user,
        student_question="""@LLM 我在第二次作业里打算同时用事件树和表格，会不会显得太重复？

:::tip 我的目标
- 一眼看清先验分支；
- 再把后验计算写得更规范；
- 最后用一句话解释事件树的作用。
:::
""",
        assistant_reply=r"""【智能助教】不会重复，关键是分工清楚：

:::example 建议搭配
- 事件树负责呈现“分支顺序”；
- 表格负责呈现“联合概率/条件概率”的对照；
- 正文负责解释为什么最后要用 Bayes 反推。
:::

若篇幅受限，保留事件树并在旁边列出关键概率即可。""",
        teacher_reply="可以保留两种表达，但请明确它们各自服务什么目的，不要把同一段推导机械抄两遍。",
        offset_days=1,
    )

    if prob_course and teacher_pro and users.get("stu1") and users.get("stu2") and users.get("stu3"):
        base = datetime.now(timezone.utc) - timedelta(days=2, hours=6)
        _ensure_course_discussion_entry(
            db,
            target_type="course",
            target_id=prob_course.id,
            subject_id=prob_course.id,
            class_id=klass.id,
            author_user_id=teacher_pro.id,
            body=r"""### 第4周讨论主题：Bayes 公式应该先背还是先理解？

请同学们围绕下面三个角度各写 2–4 句：

1. 你觉得最容易写反的是哪一个条件概率；
2. 事件树、两向表、公式三者里，哪一种最能帮助你理解；
3. 如果要向没学过概率论的同学解释“后验概率”，你会怎么说。
""",
            created_at=base,
        )
        _ensure_course_discussion_entry(
            db,
            target_type="course",
            target_id=prob_course.id,
            subject_id=prob_course.id,
            class_id=klass.id,
            author_user_id=users["stu1"].id,
            body=r"""我觉得最容易写反的是 \(P(A\mid B)\) 和 \(P(B\mid A)\)。现在我会先把中文句子写全，比如“已知阳性，来自 A 类的概率”，这样代回公式时方向会更稳。""",
            created_at=base + timedelta(minutes=20),
        )
        _ensure_course_discussion_entry(
            db,
            target_type="course",
            target_id=prob_course.id,
            subject_id=prob_course.id,
            class_id=klass.id,
            author_user_id=users["stu2"].id,
            body=r"""对我来说事件树最有帮助，因为它把“先验分支”和“条件分支”拆开了。公式写在树图后面，会更容易理解分母为什么是所有阳性路径之和。""",
            created_at=base + timedelta(minutes=45),
        )
        _ensure_course_discussion_entry(
            db,
            target_type="course",
            target_id=prob_course.id,
            subject_id=prob_course.id,
            class_id=klass.id,
            author_user_id=users["stu3"].id,
            body=r"""如果要给没学过概率论的同学解释后验概率，我会说：先有一个原来的判断，再拿到新证据之后，把这个判断“更新”一下。Bayes 像是在做一次有依据的修正。""",
            created_at=base + timedelta(hours=1, minutes=10),
        )
        _ensure_course_discussion_entry(
            db,
            target_type="course",
            target_id=prob_course.id,
            subject_id=prob_course.id,
            class_id=klass.id,
            author_user_id=teacher_pro.id,
            body=r"""教师总结：

:::tip 推荐顺序
先写中文语义，再写事件树，最后代入公式。
:::

这样做的好处是：即使算术有小错，老师也能看出你的思路是否正确；而如果一开始就只写公式，往往很难判断你究竟是没理解，还是只是抄漏了一步。""",
            created_at=base + timedelta(hours=3),
        )

    _seed_demo_learning_notes(db, klass=klass, sys_user=sys_user)


def seed_demo_course_bundle(db: Session) -> None:
    """
    Idempotent seed: teacher `teacher`, teacher `teacher_pro`, class 人工智能1班, students stu1–stu5,
    必修课「数据挖掘」+ 选修课「大语言模型」+ 选修课「初等概率论」。

    Passwords:

    - students and teacher `teacher`: demo password defined by module constant `_DEMO_PASSWORD` (six repeated ``1`` digits).
    - teacher `teacher_pro`: password equals username (`teacher_pro`), via `_TEACHER_PRO_PASSWORD`.
    """
    roster_context = ensure_demo_roster_context(db)
    teacher = roster_context.teacher
    teacher_pro = roster_context.teacher_pro
    klass = roster_context.klass

    semester = (
        db.query(Semester)
        .filter(Semester.name == "2026春季")
        .first()
        or db.query(Semester).order_by(Semester.year.desc(), Semester.id.desc()).first()
    )

    course = ensure_required_demo_course(
        db,
        teacher=teacher,
        klass=klass,
        semester=semester,
        name=_COURSE_NAME,
        description=_COURSE_DESCRIPTION,
        weekly_schedule=_COURSE_TIMES,
        weeks=16,
    )

    hw = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _HOMEWORK_TITLE)
        .first()
    )
    due = datetime.now(timezone.utc) + timedelta(days=14)
    if not hw:
        db.add(
            Homework(
                title=_HOMEWORK_TITLE,
                content=_HOMEWORK_CONTENT,
                class_id=klass.id,
                subject_id=course.id,
                due_date=due,
                max_score=100,
                grade_precision="integer",
                auto_grading_enabled=True,
                rubric_text=_RUBRIC_TEXT_STUDENT,
                rubric_staff_only=_RUBRIC_TEXT_STAFF_ONLY,
                reference_answer=_REFERENCE_OR_APPROACH,
                response_language="zh-CN",
                allow_late_submission=True,
                late_submission_affects_score=False,
                max_submissions=3,
                created_by=teacher.id,
            )
        )
        db.flush()
        print("Created demo homework (first assignment).")
    else:
        hw.content = _HOMEWORK_CONTENT
        hw.max_score = 100
        hw.grade_precision = "integer"
        hw.auto_grading_enabled = True
        hw.rubric_text = _RUBRIC_TEXT_STUDENT
        hw.rubric_staff_only = _RUBRIC_TEXT_STAFF_ONLY
        hw.reference_answer = _REFERENCE_OR_APPROACH
        hw.response_language = "zh-CN"
        hw.due_date = hw.due_date or due
        hw.max_submissions = hw.max_submissions if hw.max_submissions is not None else 3
        print("Demo homework already exists; refreshed text fields.")

    hw = (
        db.query(Homework)
        .filter(Homework.subject_id == course.id, Homework.title == _HOMEWORK_TITLE)
        .first()
    )
    _seed_demo_material_chapters(db, course=course, class_id=klass.id, teacher_id=teacher.id)
    _seed_demo_prefilled_homework_submissions(db, homework_row=hw, klass=klass)

    _seed_llm_elective_course(db, teacher=teacher, klass=klass, semester=semester)

    _seed_probability_elective_course(db, teacher_pro=teacher_pro, klass=klass, semester=semester)

    _seed_demo_runtime_activity(db, klass=klass, required_course=course, required_homework=hw)

    reconcile_student_users_and_roster(db)
    db.commit()
    print("Demo course bundle seed completed.")
