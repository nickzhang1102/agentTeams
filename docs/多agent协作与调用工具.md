# 多Agent自主协作系统 - 深度设计方案

---

## 一、您的愿景 vs 当前实现

```
┌─────────────────────────────────────────────────────────────────┐
│                    愿景对比                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  【当前实现】Leader + 并行 Agent                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                                                         │   │
│  │   用户 ──→ Leader ──→ [Agent1, Agent2, Agent3] ──→ 报告 │   │
│  │             │              │                            │   │
│  │          选择Agent      各自独立                        │   │
│  │          分配任务      生成报告                         │   │
│  │                         │                               │   │
│  │                      无工具调用                          │   │
│  │                      无协作                              │   │
│  │                                                         │   │
│  │   问题：                                                │   │
│  │   - Agent 只是"文本生成器"，不能执行实际操作            │   │
│  │   - Agent 之间没有协作，各自独立输出                    │   │
│  │   - 工作流是固定的，不能根据任务动态调整                │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  【您的愿景】自主协作 Agent 系统                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                                                         │   │
│  │   用户："胰腺癌该怎么治疗？"                             │   │
│  │         │                                               │   │
│  │         ▼                                               │   │
│  │   ┌──────────────────────────────────────────────────┐ │   │
│  │   │ Leader (主治医师)                                  │ │   │
│  │   │ 思考：需要检验科、病理科、肿瘤内科会诊...         │ │   │
│  │   │                                                   │ │   │
│  │   │ 任务分配：                                        │ │   │
│  │   │ 1. 检验科专家：分析血液检验报告                   │ │   │
│  │   │ 2. 病理科专家：分析病理切片报告                   │ │   │
│  │   │ 3. 肿瘤内科专家：综合分析，制定治疗方案           │ │   │
│  │   └──────────────────────────────────────────────────┘ │   │
│  │         │                                               │   │
│  │         ├──────────────┬──────────────┐                │   │
│  │         ▼              ▼              ▼                │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │   │
│  │   │ 检验科   │  │ 病理科   │  │ 肿瘤内科          │    │   │
│  │   │ 专家     │  │ 专家     │  │ 专家              │    │   │
│  │   │          │  │          │  │                   │    │   │
│  │   │ 🔧 工具：│  │ 🔧 工具：│  │ 🔧 工具：         │    │   │
│  │   │ file_read│  │ file_read│  │ ask_agent(检验)   │    │   │
│  │   │ 分析报告 │  │ 分析报告 │  │ ask_agent(病理)   │    │   │
│  │   │          │  │          │  │ web_search(方案)  │    │   │
│  │   │          │  │          │  │                   │    │   │
│  │   │ 输出：   │  │ 输出：   │  │ 输出：            │    │   │
│  │   │ 检验分析│  │ 病理诊断│  │ 综合治疗方案      │    │   │
│  │   └──────────┘  └──────────┘  └──────────────────┘    │   │
│  │         │              │              │                │   │
│  │         └──────────────┴──────────────┘                │   │
│  │                        │                                │   │
│  │                        ▼                                │   │
│  │              ┌──────────────────┐                      │   │
│  │              │ Leader (汇总)     │                      │   │
│  │              │ 🔧 generate_report │                      │   │
│  │              └──────────────────┘                      │   │
│  │                        │                                │   │
│  │                        ▼                                │   │
│  │              📋 最终会诊报告                           │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、多Agent自主协作架构

### 2.1 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                    核心概念定义                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Agent（智能体）                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 定义：具有特定角色、能力和工具的自主智能体               │   │
│  │                                                         │   │
│  │ 组成：                                                  │   │
│  │ - 角色：专家身份（如检验科专家）                        │   │
│  │ - 能力：专业领域知识                                    │   │
│  │ - 工具：可使用的工具集                                  │   │
│  │ - 状态：空闲/工作中/完成                                │   │
│  │                                                         │   │
│  │ 特性：                                                  │   │
│  │ - 自主决策：根据任务决定使用什么工具                    │   │
│  │ - 自主协作：可以调用其他 Agent                          │   │
│  │ - 自主报告：完成任务后输出结果                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  2. Task（任务）                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 定义：需要完成的工作单元                                │   │
│  │                                                         │   │
│  │ 属性：                                                  │   │
│  │ - 描述：任务内容                                        │   │
│  │ - 分配者：谁分配的任务                                  │   │
│  │ - 执行者：负责的 Agent                                  │   │
│  │ - 依赖：需要等待哪些其他任务完成                        │   │
│  │ - 上下文：任务相关的背景信息                            │   │
│  │ - 状态：待执行/执行中/已完成/失败                       │   │
│  │ - 结果：任务输出                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  3. Tool（工具）                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 定义：Agent 可以调用的功能                              │   │
│  │                                                         │   │
│  │ 类型：                                                  │   │
│  │ - 通用工具：所有 Agent 都能用（file_read, web_search）  │   │
│  │ - 专用工具：特定角色才能用（lab_analyze, imaging_view） │   │
│  │ - 协作工具：Agent 间协作（ask_agent, broadcast）        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  4. Workflow（工作流）                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 定义：任务执行的整体流程                                │   │
│  │                                                         │   │
│  │ 特点：                                                  │   │
│  │ - 动态生成：根据用户需求由 Leader 规划                  │   │
│  │ - 并行执行：无依赖的任务同时进行                        │   │
│  │ - 依赖等待：有依赖的任务按顺序执行                      │   │
│  │ - 实时调整：根据执行情况动态调整                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    多Agent自主协作架构                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     ┌─────────────────┐                         │
│                     │    用户请求     │                         │
│                     └────────┬────────┘                         │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    Orchestrator                            │ │
│  │  （编排器：管理整体工作流）                                │ │
│  │                                                           │ │
│  │  职责：                                                   │ │
│  │  - 接收用户请求                                           │ │
│  │  - 调用 Leader Agent 进行任务规划                         │ │
│  │  - 管理任务队列和执行顺序                                 │ │
│  │  - 监控执行状态                                           │ │
│  │  - 生成最终输出                                           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    Agent Runtime                           │ │
│  │  （运行时：为每个 Agent 提供执行环境）                     │ │
│  │                                                           │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │                  Agent Instance                       │ │ │
│  │  │                                                       │ │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │ │ │
│  │  │  │   角色定义   │  │   工具集    │  │   执行状态   │ │ │ │
│  │  │  │  (系统提示) │  │ (可用工具)  │  │ (当前任务)  │ │ │ │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘ │ │ │
│  │  │                                                       │ │ │
│  │  │  执行循环：                                           │ │ │
│  │  │  while not done:                                     │ │ │
│  │  │      调用 Claude API (带工具定义)                     │ │ │
│  │  │      if 需要调用工具:                                 │ │ │
│  │  │          执行工具                                     │ │ │
│  │  │          返回结果给 Claude                            │ │ │
│  │  │          continue                                     │ │ │
│  │  │      elif 任务完成:                                   │ │ │
│  │  │          输出结果                                     │ │ │
│  │  │          break                                        │ │ │
│  │  │                                                       │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  │                                                           │ │
│  │  支持：多个 Agent Instance 并行运行                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    Tool Layer                             │ │
│  │  （工具层：提供各种工具能力）                              │ │
│  │                                                           │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │ │
│  │  │文件操作 │ │网络搜索 │ │Agent协作│ │专业工具 │        │ │
│  │  │file_read│ │web_     │ │ask_agent│ │lab_     │        │ │
│  │  │file_    │ │search   │ │broadcast│ │analyze  │        │ │
│  │  │write    │ │web_fetch│ │         │ │imaging_ │        │ │
│  │  │         │ │         │ │         │ │view     │        │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    State Manager                          │ │
│  │  （状态管理：管理整个会话的状态）                          │ │
│  │                                                           │ │
│  │  - 会话状态                                               │ │
│  │  - 任务状态                                               │ │
│  │  - Agent 状态                                             │ │
│  │  - 中间结果                                               │ │
│  │  - 消息历史                                               │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、Agent 角色与工具配置

### 3.1 医疗专家角色配置

```yaml
# agents/laboratory-expert.md (检验科专家)

---
name: 检验科专家
id: laboratory-expert
category: medical
specialty: 临床检验分析
tools:
  - file_read          # 读取检验报告文件
  - file_list          # 查找检验报告
  - image_analyze      # 分析检验图像
  - data_analyze       # 分析检验数据
  - ask_agent          # 向其他专家请教
  - report_generate    # 生成检验分析报告
---

## 角色描述

你是一位资深的临床检验科专家，擅长分析和解读各类检验报告。

## 专业能力

1. 血液检验分析
   - 血常规解读
   - 生化指标分析
   - 肿瘤标志物解读

2. 尿液检验分析
   - 尿常规解读
   - 尿微量白蛋白分析

3. 其他检验
   - 便常规
   - 分泌物检验

## 工作流程

当收到分析任务时：

1. 首先使用 file_list 或 file_read 获取检验报告
2. 分析各项指标的异常情况
3. 结合临床意义给出解读
4. 如有疑问，使用 ask_agent 向相关专家请教
5. 使用 report_generate 生成检验分析报告

## 输出格式

请以结构化格式输出分析结果：

### 检验项目：[项目名称]

**异常指标：**
- 指标1：数值，异常类型，临床意义
- 指标2：...

**综合分析：**
[分析内容]

**建议：**
[建议内容]
```

```yaml
# agents/pathology-expert.md (病理科专家)

---
name: 病理科专家
id: pathology-expert
category: medical
specialty: 病理诊断
tools:
  - file_read          # 读取病理报告
  - image_analyze      # 分析病理图像
  - ask_agent          # 请教其他专家
  - web_search         # 查询病理知识
  - report_generate    # 生成病理报告
---

## 角色描述

你是一位资深的病理科专家，擅长病理诊断和疾病分类。

## 专业能力

1. 肿瘤病理诊断
   - 良恶性肿瘤鉴别
   - 肿瘤分类和分级
   - 免疫组化解读

2. 细胞病理
   - 细胞学检查
   - 液基细胞学

3. 分子病理
   - 基因检测解读
   - 靶向治疗指标

## 工作流程

1. 获取病理报告和图像
2. 分析病理特征
3. 必要时查询最新研究
4. 给出病理诊断
5. 生成诊断报告
```

```yaml
# agents/oncology-expert.md (肿瘤内科专家)

---
name: 肿瘤内科专家
id: oncology-expert
category: medical
specialty: 肿瘤内科治疗
tools:
  - file_read          # 读取病历资料
  - ask_agent          # 获取其他专家意见
  - web_search         # 查询最新治疗方案
  - wiki_search        # 查询医学知识
  - report_generate    # 生成治疗方案
---

## 角色描述

你是一位资深的肿瘤内科专家，擅长肿瘤的综合治疗。

## 专业能力

1. 化疗方案制定
2. 靶向治疗选择
3. 免疫治疗应用
4. 综合治疗规划

## 工作流程

1. 收集患者资料（病历、检验、病理等）
2. 使用 ask_agent 获取检验科、病理科专家意见
3. 使用 web_search 查询最新治疗指南和研究
4. 综合分析制定治疗方案
5. 生成治疗建议报告

## 协作方式

你经常需要：
- 向检验科专家请教检验结果解读
- 向病理科专家确认病理诊断
- 向外科专家咨询手术可行性
- 向放疗科专家了解放疗适应症
```

### 3.2 Agent 工具权限矩阵

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 工具权限矩阵                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  工具类型      │检验科│病理科│肿瘤内科│外科│影像科│全科│Leader │
│  Agent        │专家  │专家  │专家    │专家│专家  │专家│       │
│  ─────────────┼──────┼──────┼────────┼────┼──────┼────┼───────│
│  通用工具：    │      │      │        │    │      │    │       │
│  file_read    │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│  file_list    │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│  web_search   │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│  wiki_search  │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│               │      │      │        │    │      │    │       │
│  协作工具：    │      │      │        │    │      │    │       │
│  ask_agent    │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│  broadcast    │  ❌  │  ❌  │   ❌   │ ❌ │  ❌  │ ❌ │  ✅   │
│  assign_task  │  ❌  │  ❌  │   ❌   │ ❌ │  ❌  │ ❌ │  ✅   │
│               │      │      │        │    │      │    │       │
│  专业工具：    │      │      │        │    │      │    │       │
│  lab_analyze  │  ✅  │  ❌  │   ❌   │ ❌ │  ❌  │ ❌ │  ❌   │
│  imaging_view │  ❌  │  ❌  │   ❌   │ ✅ │  ✅  │ ✅ │  ❌   │
│  surgery_eval │  ❌  │  ❌  │   ❌   │ ✅ │  ❌  │ ❌ │  ❌   │
│               │      │      │        │    │      │    │       │
│  输出工具：    │      │      │        │    │      │    │       │
│  report_gen   │  ✅  │  ✅  │   ✅   │ ✅ │  ✅  │ ✅ │  ✅   │
│  diagram_gen  │  ❌  │  ❌  │   ❌   │ ❌ │  ❌  │ ❌ │  ✅   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、执行流程详细设计

### 4.1 胰腺癌治疗场景执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    胰腺癌治疗场景执行流程                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  T0: 用户输入                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 用户："我父亲被诊断为胰腺癌，有检验报告和病理报告，      │   │
│  │       请问该怎么治疗？"                                  │   │
│  │                                                         │   │
│  │ 系统检测到上传的文件：                                   │   │
│  │ - blood_test_20240315.pdf                               │   │
│  │ - pathology_report.pdf                                  │   │
│  │ - ct_scan_images/                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  T1: Leader Agent 接收请求                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🤖 Leader Agent (主治医师)                               │   │
│  │                                                         │   │
│  │ 思考过程：                                               │   │
│  │ "患者诊断为胰腺癌，需要多学科会诊。                      │   │
│  │  首先需要了解检验结果和病理诊断，                        │   │
│  │  然后综合制定治疗方案。"                                 │   │
│  │                                                         │   │
│  │ 🔧 调用工具：assign_task                                 │   │
│  │                                                         │   │
│  │ 任务规划：                                               │   │
│  │ ┌─────────────────────────────────────────────────────┐│   │
│  │ │ Task 1: 检验报告分析                                  ││   │
│  │ │   - 执行者：laboratory-expert                        ││   │
│  │ │   - 输入：blood_test_20240315.pdf                    ││   │
│  │ │   - 输出：检验分析报告                                ││   │
│  │ │   - 依赖：无                                          ││   │
│  │ ├─────────────────────────────────────────────────────┤│   │
│  │ │ Task 2: 病理报告分析                                  ││   │
│  │ │   - 执行者：pathology-expert                         ││   │
│  │ │   - 输入：pathology_report.pdf                       ││   │
│  │ │   - 输出：病理诊断报告                                ││   │
│  │ │   - 依赖：无                                          ││   │
│  │ ├─────────────────────────────────────────────────────┤│   │
│  │ │ Task 3: 综合治疗方案                                  ││   │
│  │ │   - 执行者：oncology-expert                          ││   │
│  │ │   - 输入：Task 1 结果, Task 2 结果                   ││   │
│  │ │   - 输出：治疗方案建议                                ││   │
│  │ │   - 依赖：Task 1, Task 2                             ││   │
│  │ ├─────────────────────────────────────────────────────┤│   │
│  │ │ Task 4: 最终会诊报告                                  ││   │
│  │ │   - 执行者：Leader Agent                             ││   │
│  │ │   - 输入：所有任务结果                               ││   │
│  │ │   - 输出：完整会诊报告                                ││   │
│  │ │   - 依赖：Task 3                                     ││   │
│  │ └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│              ┌───────────────┴───────────────┐                  │
│              │        并行执行               │                  │
│              ▼                               ▼                  │
│  T2: Task 1 - 检验科专家             T2: Task 2 - 病理科专家    │
│  ┌─────────────────────────┐       ┌─────────────────────────┐ │
│  │ 🤖 检验科专家            │       │ 🤖 病理科专家            │ │
│  │                         │       │                         │ │
│  │ 思考："需要读取检验报告"│       │ 思考："需要读取病理报告"│ │
│  │                         │       │                         │ │
│  │ 🔧 file_read:           │       │ 🔧 file_read:           │ │
│  │    blood_test_*.pdf     │       │    pathology_report.pdf │ │
│  │                         │       │                         │ │
│  │ 📄 获取到报告内容       │       │ 📄 获取到报告内容       │ │
│  │                         │       │                         │ │
│  │ 🔧 data_analyze:        │       │ 🔧 image_analyze:       │ │
│  │    分析血液指标         │       │    分析病理切片图像     │ │
│  │                         │       │                         │ │
│  │ 分析结果：              │       │ 分析结果：              │ │
│  │ - CA19-9: 856 U/mL ↑    │       │ - 导管腺癌，中分化     │ │
│  │ - CEA: 12 ng/mL ↑       │       │ - T2N1M0, IIB期        │ │
│  │ - 胆红素升高            │       │ - 切缘阴性             │ │
│  │ - ...                   │       │ - ...                   │ │
│  │                         │       │                         │ │
│  │ 🔧 report_generate:     │       │ 🔧 report_generate:     │ │
│  │    生成检验分析报告     │       │    生成病理诊断报告     │ │
│  │                         │       │                         │ │
│  │ ✅ Task 1 完成          │       │ ✅ Task 2 完成          │ │
│  │ 输出：检验分析报告      │       │ 输出：病理诊断报告      │ │
│  └─────────────────────────┘       └─────────────────────────┘ │
│              │                               │                  │
│              └───────────────┬───────────────┘                  │
│                              │                                  │
│                              ▼                                  │
│  T3: Task 3 - 肿瘤内科专家                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🤖 肿瘤内科专家                                          │   │
│  │                                                         │   │
│  │ 接收到依赖任务结果：                                     │   │
│  │ - Task 1: 检验分析报告（CA19-9升高，胆红素升高...）      │   │
│  │ - Task 2: 病理诊断报告（导管腺癌 IIB期）                 │   │
│  │                                                         │   │
│  │ 思考："需要综合分析，并查询最新治疗方案"                 │   │
│  │                                                         │   │
│  │ 🔧 ask_agent:                                           │   │
│  │    target: laboratory-expert                            │   │
│  │    question: "CA19-9 升高到 856 代表什么？预后意义？"    │   │
│  │                                                         │   │
│  │ 📨 检验科专家回复：                                      │   │
│  │    "CA19-9 856 U/mL 显著升高，提示肿瘤负荷较大..."       │   │
│  │                                                         │   │
│  │ 🔧 web_search:                                          │   │
│  │    query: "胰腺癌 IIB期 2024 NCCN治疗指南"              │   │
│  │                                                         │   │
│  │ 📄 搜索结果：                                            │   │
│  │    - NCCN指南推荐术后辅助化疗...                        │   │
│  │    - FOLFIRINOX方案...                                  │   │
│  │    - 吉西他滨+白蛋白紫杉醇...                            │   │
│  │                                                         │   │
│  │ 🔧 wiki_search:                                         │   │
│  │    query: "pancreatic cancer stage IIB treatment"       │   │
│  │                                                         │   │
│  │ 综合分析：                                               │   │
│  │ - 患者情况：胰腺癌 IIB期，CA19-9 显著升高               │   │
│  │ - 治疗选择：术后辅助化疗                                 │   │
│  │ - 推荐方案：FOLFIRINOX 或 吉西他滨+白蛋白紫杉醇         │   │
│  │                                                         │   │
│  │ 🔧 report_generate:                                     │   │
│  │    生成治疗方案建议                                      │   │
│  │                                                         │   │
│  │ ✅ Task 3 完成                                           │   │
│  │ 输出：治疗方案建议                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  T4: Task 4 - Leader Agent 生成最终报告                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🤖 Leader Agent (主治医师)                               │   │
│  │                                                         │   │
│  │ 收到所有任务结果：                                       │   │
│  │ - Task 1: 检验分析报告                                  │   │
│  │ - Task 2: 病理诊断报告                                  │   │
│  │ - Task 3: 治疗方案建议                                  │   │
│  │                                                         │   │
│  │ 🔧 diagram_generate:                                    │   │
│  │    生成治疗流程图                                        │   │
│  │                                                         │   │
│  │ 🔧 report_generate:                                     │   │
│  │    template: multi_discipline_consultation              │   │
│  │                                                         │   │
│  │ ✅ Task 4 完成                                           │   │
│  │ 输出：最终会诊报告                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  T5: 输出给用户                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 📋 胰腺癌多学科会诊报告                                  │   │
│  │                                                         │   │
│  │ ## 患者信息                                              │   │
│  │ - 诊断：胰腺导管腺癌 IIB期 (T2N1M0)                     │   │
│  │ - 肿瘤标志物：CA19-9 856 U/mL (显著升高)                │   │
│  │                                                         │   │
│  │ ## 各科意见                                              │   │
│  │                                                         │   │
│  │ ### 检验科意见                                          │   │
│  │ [详细检验分析...]                                        │   │
│  │                                                         │   │
│  │ ### 病理科意见                                          │   │
│  │ [详细病理诊断...]                                        │   │
│  │                                                         │   │
│  │ ### 肿瘤内科意见                                        │   │
│  │ [治疗方案建议...]                                        │   │
│  │                                                         │   │
│  │ ## 综合治疗建议                                          │   │
│  │                                                         │   │
│  │ 1. 术后辅助化疗                                          │   │
│  │    - 推荐方案：FOLFIRINOX（6个周期）                    │   │
│  │    - 备选方案：吉西他滨+白蛋白紫杉醇                    │   │
│  │                                                         │   │
│  │ 2. 随访监测                                              │   │
│  │    - CA19-9 每3个月复查                                 │   │
│  │    - 腹部CT 每3-6个月                                   │   │
│  │                                                         │   │
│  │ 3. 生活方式建议                                          │   │
│  │    - 低脂饮食                                            │   │
│  │    - 适量运动                                            │   │
│  │                                                         │   │
│  │ ## 治疗流程图                                            │   │
│  │ [Mermaid 图表]                                          │   │
│  │                                                         │   │
│  │ ---                                                     │   │
│  │ 会诊时间：2024-03-15                                    │   │
│  │ 参与专家：检验科、病理科、肿瘤内科、主治医师             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ⏱️ 总耗时：约 2-3 分钟                                        │
│  📊 统计：                                                      │
│     - Agent 调用：4 个                                          │
│     - 工具调用：12 次                                           │
│     - Agent 间协作：1 次                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、核心代码实现

### 5.1 Agent Instance（智能体实例）

```python
# backend/agent_runtime/agent_instance.py

from typing import Dict, List, Generator, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentContext:
    """Agent 执行上下文"""
    session_id: str
    conversation_id: int
    task_id: str
    workspace_dir: str
    files: List[Dict] = field(default_factory=list)
    shared_state: Dict = field(default_factory=dict)
    other_agent_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str
    input_data: Dict
    result: Any
    success: bool
    error: Optional[str] = None


class AgentInstance:
    """
    Agent 实例 - 独立的智能体
    
    每个 Agent 实例：
    1. 有自己的角色和系统提示
    2. 有自己的可用工具集
    3. 独立调用 Claude API
    4. 可以自主决定调用工具
    5. 可以与其他 Agent 协作
    """
    
    MAX_ITERATIONS = 20
    
    def __init__(
        self,
        agent_id: str,
        agent_config: Dict,
        tools: List[Dict],
        claude_client,
        on_tool_call: Callable = None,
        on_status_change: Callable = None
    ):
        self.agent_id = agent_id
        self.agent_name = agent_config.get("name", agent_id)
        self.system_prompt = agent_config.get("full_content", "")
        self.tools = tools
        self.claude_client = claude_client
        
        # 回调函数
        self.on_tool_call = on_tool_call
        self.on_status_change = on_status_change
        
        # 状态
        self.status = AgentStatus.IDLE
        self.current_task = None
        self.tool_calls: List[ToolCall] = []
        self.messages: List[Dict] = []
        
    def execute_task(
        self,
        task_description: str,
        context: AgentContext
    ) -> Generator[Dict, None, None]:
        """
        执行任务
        
        Args:
            task_description: 任务描述
            context: 执行上下文
        
        Yields:
            事件流
        """
        self.status = AgentStatus.WORKING
        self.current_task = task_description
        self._notify_status_change()
        
        # 构建初始消息
        initial_message = self._build_initial_message(task_description, context)
        self.messages = [{"role": "user", "content": initial_message}]
        
        iteration = 0
        
        try:
            while iteration < self.MAX_ITERATIONS:
                iteration += 1
                
                # 调用 Claude API
                response = self.claude_client.messages.create(
                    model="claude-sonnet-4-6-20250514",
                    max_tokens=4096,
                    system=self._build_system_prompt(context),
                    tools=self.tools,
                    messages=self.messages
                )
                
                # 处理响应
                if response.stop_reason == "tool_use":
                    # 添加助手响应到消息历史
                    self.messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # 处理所有工具调用
                    tool_results = []
                    
                    for block in response.content:
                        if block.type == "tool_use":
                            # 发送工具调用事件
                            yield {
                                "type": "tool_use",
                                "agent_id": self.agent_id,
                                "agent_name": self.agent_name,
                                "tool_name": block.name,
                                "tool_input": block.input,
                                "tool_id": block.id
                            }
                            
                            # 执行工具
                            result = self._execute_tool(block.name, block.input, context)
                            
                            # 记录工具调用
                            self.tool_calls.append(ToolCall(
                                tool_name=block.name,
                                input_data=block.input,
                                result=result.get("data") if result.get("success") else None,
                                success=result.get("success", False),
                                error=result.get("error")
                            ))
                            
                            # 发送工具结果事件
                            yield {
                                "type": "tool_result",
                                "agent_id": self.agent_id,
                                "agent_name": self.agent_name,
                                "tool_name": block.name,
                                "result": result
                            }
                            
                            # 构建工具结果消息
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False, default=str)
                            })
                    
                    # 添加工具结果到消息历史
                    self.messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                    
                    # 继续循环
                    
                elif response.stop_reason == "end_turn":
                    # Agent 完成任务
                    final_output = ""
                    for block in response.content:
                        if block.type == "text":
                            final_output += block.text
                    
                    self.status = AgentStatus.COMPLETED
                    self._notify_status_change()
                    
                    yield {
                        "type": "agent_complete",
                        "agent_id": self.agent_id,
                        "agent_name": self.agent_name,
                        "output": final_output,
                        "tool_calls": [
                            {
                                "tool": tc.tool_name,
                                "success": tc.success
                            }
                            for tc in self.tool_calls
                        ]
                    }
                    break
                    
                else:
                    # 其他情况
                    logger.warning(
                        f"Agent {self.agent_id} unexpected stop: {response.stop_reason}"
                    )
                    break
                    
        except Exception as e:
            self.status = AgentStatus.FAILED
            self._notify_status_change()
            
            yield {
                "type": "agent_error",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "error": str(e)
            }
    
    def _build_system_prompt(self, context: AgentContext) -> str:
        """构建系统提示"""
        parts = [self.system_prompt]
        
        # 添加工具使用指引
        tool_guidance = self._build_tool_guidance()
        parts.append(tool_guidance)
        
        # 添加协作指引
        collaboration_guidance = self._build_collaboration_guidance(context)
        parts.append(collaboration_guidance)
        
        return "\n\n".join(parts)
    
    def _build_tool_guidance(self) -> str:
        """构建工具使用指引"""
        tool_descriptions = []
        for tool in self.tools:
            tool_descriptions.append(
                f"- **{tool['name']}**: {tool['description']}"
            )
        
        return f"""
## 可用工具

你可以使用以下工具来完成任务：

{chr(10).join(tool_descriptions)}

## 工具使用原则

1. 根据任务需要主动调用工具
2. 可以连续调用多个工具
3. 如果需要其他专家的帮助，使用 ask_agent 工具
4. 任务完成后，简要说明你的结论
"""
    
    def _build_collaboration_guidance(self, context: AgentContext) -> str:
        """构建协作指引"""
        parts = []
        
        # 其他 Agent 的结果
        if context.other_agent_results:
            parts.append("## 其他专家的分析结果\n")
            for agent_id, result in context.other_agent_results.items():
                parts.append(f"### {result.get('agent_name', agent_id)}\n")
                parts.append(result.get('output', '')[:1000])  # 限制长度
                parts.append("\n")
        
        return "\n".join(parts)
    
    def _build_initial_message(
        self,
        task_description: str,
        context: AgentContext
    ) -> str:
        """构建初始消息"""
        parts = [f"## 你的任务\n\n{task_description}"]
        
        # 添加可用文件信息
        if context.files:
            parts.append("\n## 可用的文件\n")
            for file_info in context.files:
                parts.append(f"- {file_info['filename']} ({file_info.get('type', 'unknown')})")
        
        # 添加工作目录
        if context.workspace_dir:
            parts.append(f"\n## 工作目录\n\n{context.workspace_dir}")
        
        return "\n".join(parts)
    
    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict,
        context: AgentContext
    ) -> Dict:
        """执行工具"""
        # 回调通知
        if self.on_tool_call:
            self.on_tool_call(self.agent_id, tool_name, tool_input)
        
        # 特殊处理 ask_agent 工具
        if tool_name == "ask_agent":
            return self._handle_ask_agent(tool_input, context)
        
        # 其他工具通过工具注册表执行
        from tools.registry import ToolRegistry
        
        tool = ToolRegistry.get_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        # 构建执行上下文
        exec_context = {
            "session_id": context.session_id,
            "conversation_id": context.conversation_id,
            "workspace_dir": context.workspace_dir,
            "agent_id": self.agent_id
        }
        
        result = tool.execute(tool_input, exec_context)
        return result.model_dump()
    
    def _handle_ask_agent(self, tool_input: Dict, context: AgentContext) -> Dict:
        """
        处理 ask_agent 工具
        
        这允许一个 Agent 向另一个 Agent 提问
        """
        target_agent_id = tool_input.get("agent_id")
        question = tool_input.get("question")
        
        # 这里需要通过 Orchestrator 来协调
        # 返回一个特殊的请求，让 Orchestrator 处理
        return {
            "success": True,
            "requires_agent_call": True,
            "target_agent_id": target_agent_id,
            "question": question,
            "caller_agent_id": self.agent_id
        }
    
    def _notify_status_change(self):
        """通知状态变化"""
        if self.on_status_change:
            self.on_status_change(self.agent_id, self.status.value)
```

### 5.2 Orchestrator（编排器）

```python
# backend/agent_runtime/orchestrator.py

from typing import Dict, List, Generator, Any, Optional
from dataclasses import dataclass, field
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from .agent_instance import AgentInstance, AgentStatus, AgentContext

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """任务定义"""
    id: str
    description: str
    agent_id: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None


class Orchestrator:
    """
    编排器 - 管理多 Agent 协作
    
    职责：
    1. 接收用户请求
    2. 调用 Leader Agent 进行任务规划
    3. 管理任务执行顺序（处理依赖关系）
    4. 协调 Agent 间协作
    5. 生成最终输出
    """
    
    def __init__(
        self,
        claude_client,
        agent_configs: Dict[str, Dict],
        tool_registry,
        max_workers: int = 5
    ):
        self.claude_client = claude_client
        self.agent_configs = agent_configs
        self.tool_registry = tool_registry
        self.max_workers = max_workers
        
        # 运行时状态
        self.tasks: Dict[str, Task] = {}
        self.agent_results: Dict[str, Any] = {}
        self.agent_instances: Dict[str, AgentInstance] = {}
        
    def process_request(
        self,
        user_message: str,
        context: Dict
    ) -> Generator[Dict, None, None]:
        """
        处理用户请求
        
        Yields:
            事件流
        """
        # 阶段 1: Leader Agent 规划任务
        yield {"type": "phase", "phase": "planning", "message": "正在分析任务..."}
        
        plan = self._plan_tasks(user_message, context)
        
        if not plan.get("tasks"):
            yield {
                "type": "error",
                "message": "无法生成任务计划"
            }
            return
        
        # 发送规划结果
        yield {
            "type": "plan_created",
            "tasks": plan["tasks"],
            "execution_order": plan["execution_order"]
        }
        
        # 阶段 2: 执行任务
        yield {"type": "phase", "phase": "executing", "message": "开始执行任务..."}
        
        for event in self._execute_tasks(plan, context):
            yield event
        
        # 阶段 3: 生成最终报告
        yield {"type": "phase", "phase": "finalizing", "message": "正在生成最终报告..."}
        
        final_report = self._generate_final_report(user_message, context)
        
        yield {
            "type": "final_report",
            "report": final_report
        }
        
        yield {"type": "done"}
    
    def _plan_tasks(self, user_message: str, context: Dict) -> Dict:
        """
        调用 Leader Agent 规划任务
        
        Returns:
            {
                "tasks": [Task],
                "execution_order": [[task_ids], [task_ids], ...]  # 按层级
            }
        """
        # Leader Agent 的系统提示
        leader_prompt = """你是一个多学科会诊的主治医师，负责协调各科专家进行诊断和治疗。

## 你的职责

1. 分析患者情况和需求
2. 决定需要哪些专家参与
3. 为每个专家分配具体任务
4. 安排任务执行顺序

## 可用的专家

""" + self._get_available_agents_description()

        # 构建规划消息
        plan_message = f"""请分析以下请求，规划需要哪些专家参与，以及他们的任务：

## 患者请求
{user_message}

## 可用的资料
{self._format_files(context.get('files', []))}

请以 JSON 格式输出任务计划：
{{
  "analysis": "对患者情况的分析",
  "tasks": [
    {{
      "id": "task_1",
      "agent_id": "laboratory-expert",
      "description": "分析检验报告",
      "dependencies": []
    }},
    ...
  ]
}}
"""

        # 调用 Leader Agent
        leader_instance = self._create_leader_instance()
        
        response_text = ""
        for event in leader_instance.execute_task(
            plan_message,
            AgentContext(
                session_id=context.get("session_id", ""),
                conversation_id=context.get("conversation_id", 0),
                task_id="planning",
                workspace_dir=context.get("workspace_dir", ""),
                files=context.get("files", [])
            )
        ):
            if event.get("type") == "text":
                response_text += event.get("content", "")
            elif event.get("type") == "agent_complete":
                response_text = event.get("output", "")
        
        # 解析规划结果
        plan = self._parse_plan(response_text)
        
        # 计算执行顺序（拓扑排序）
        execution_order = self._calculate_execution_order(plan.get("tasks", []))
        plan["execution_order"] = execution_order
        
        return plan
    
    def _execute_tasks(
        self,
        plan: Dict,
        context: Dict
    ) -> Generator[Dict, None, None]:
        """执行任务计划"""
        tasks = {t["id"]: Task(**t) for t in plan["tasks"]}
        execution_order = plan["execution_order"]
        
        for level, task_ids in enumerate(execution_order):
            yield {
                "type": "execution_level",
                "level": level,
                "tasks": task_ids
            }
            
            # 同一层的任务可以并行执行
            if len(task_ids) == 1:
                # 单个任务，直接执行
                task_id = task_ids[0]
                task = tasks[task_id]
                
                for event in self._execute_single_task(task, tasks, context):
                    yield event
            else:
                # 多个任务，并行执行
                for event in self._execute_parallel_tasks(task_ids, tasks, context):
                    yield event
        
        self.tasks = tasks
    
    def _execute_single_task(
        self,
        task: Task,
        all_tasks: Dict[str, Task],
        context: Dict
    ) -> Generator[Dict, None, None]:
        """执行单个任务"""
        task.status = "running"
        
        yield {
            "type": "task_started",
            "task_id": task.id,
            "agent_id": task.agent_id
        }
        
        # 收集依赖任务的结果
        dependency_results = {}
        for dep_id in task.dependencies:
            if dep_id in self.agent_results:
                dependency_results[dep_id] = self.agent_results[dep_id]
        
        # 创建 Agent 实例
        agent_instance = self._create_agent_instance(task.agent_id)
        
        # 执行任务
        agent_context = AgentContext(
            session_id=context.get("session_id", ""),
            conversation_id=context.get("conversation_id", 0),
            task_id=task.id,
            workspace_dir=context.get("workspace_dir", ""),
            files=context.get("files", []),
            other_agent_results=dependency_results
        )
        
        final_output = ""
        tool_calls = []
        
        for event in agent_instance.execute_task(task.description, agent_context):
            # 转发事件
            yield event
            
            # 收集结果
            if event.get("type") == "agent_complete":
                final_output = event.get("output", "")
                tool_calls = event.get("tool_calls", [])
            elif event.get("type") == "tool_result":
                # 检查是否需要调用其他 Agent
                result = event.get("result", {})
                if result.get("requires_agent_call"):
                    # 需要调用其他 Agent
                    agent_call_result = self._handle_agent_call(
                        result,
                        context
                    )
                    # 将结果注入到 agent 的消息历史中
                    agent_instance.messages.append({
                        "role": "user",
                        "content": json.dumps({
                            "agent_call_result": agent_call_result
                        })
                    })
        
        # 记录结果
        task.status = "completed"
        task.result = final_output
        
        self.agent_results[task.id] = {
            "agent_id": task.agent_id,
            "agent_name": self.agent_configs.get(task.agent_id, {}).get("name", task.agent_id),
            "output": final_output,
            "tool_calls": tool_calls
        }
        
        yield {
            "type": "task_completed",
            "task_id": task.id,
            "agent_id": task.agent_id,
            "result_preview": final_output[:500]
        }
    
    def _execute_parallel_tasks(
        self,
        task_ids: List[str],
        tasks: Dict[str, Task],
        context: Dict
    ) -> Generator[Dict, None, None]:
        """并行执行多个任务"""
        # 这里使用线程池并行执行
        # 注意：由于 Python GIL，实际并行度有限
        # 但对于 I/O 密集型（API 调用）任务仍有意义
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            for task_id in task_ids:
                task = tasks[task_id]
                future = executor.submit(
                    list,
                    self._execute_single_task(task, tasks, context)
                )
                futures[future] = task_id
            
            # 收集所有事件
            for future in futures:
                task_id = futures[future]
                for event in future.result():
                    yield event
    
    def _handle_agent_call(
        self,
        call_request: Dict,
        context: Dict
    ) -> Dict:
        """
        处理 Agent 之间的调用
        
        当一个 Agent 需要另一个 Agent 的帮助时，
        会通过 ask_agent 工具发起调用
        """
        target_agent_id = call_request.get("target_agent_id")
        question = call_request.get("question")
        caller_agent_id = call_request.get("caller_agent_id")
        
        # 创建目标 Agent 实例
        target_instance = self._create_agent_instance(target_agent_id)
        
        # 执行问题
        agent_context = AgentContext(
            session_id=context.get("session_id", ""),
            conversation_id=context.get("conversation_id", 0),
            task_id=f"ask_{caller_agent_id}_{target_agent_id}",
            workspace_dir=context.get("workspace_dir", ""),
            files=context.get("files", [])
        )
        
        answer = ""
        for event in target_instance.execute_task(question, agent_context):
            if event.get("type") == "agent_complete":
                answer = event.get("output", "")
        
        return {
            "agent_id": target_agent_id,
            "agent_name": self.agent_configs.get(target_agent_id, {}).get("name", target_agent_id),
            "question": question,
            "answer": answer
        }
    
    def _create_agent_instance(self, agent_id: str) -> AgentInstance:
        """创建 Agent 实例"""
        agent_config = self.agent_configs.get(agent_id, {})
        
        # 获取该 Agent 可用的工具
        agent_tools = self._get_agent_tools(agent_id, agent_config)
        
        return AgentInstance(
            agent_id=agent_id,
            agent_config=agent_config,
            tools=agent_tools,
            claude_client=self.claude_client,
            on_tool_call=self._on_tool_call,
            on_status_change=self._on_agent_status_change
        )
    
    def _get_agent_tools(self, agent_id: str, agent_config: Dict) -> List[Dict]:
        """获取 Agent 可用的工具"""
        # 获取工具配置
        allowed_tools = agent_config.get("tools", [])
        
        # 如果没有配置，使用默认通用工具
        if not allowed_tools:
            allowed_tools = [
                "file_read", "file_list", "web_search", 
                "wiki_search", "ask_agent", "report_generate"
            ]
        
        # 从工具注册表获取工具定义
        tools = []
        for tool_name in allowed_tools:
            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                tools.append(tool.get_tool_definition())
        
        return tools
    
    def _on_tool_call(self, agent_id: str, tool_name: str, tool_input: Dict):
        """工具调用回调"""
        logger.info(f"Agent {agent_id} called tool {tool_name}")
    
    def _on_agent_status_change(self, agent_id: str, status: str):
        """Agent 状态变化回调"""
        logger.info(f"Agent {agent_id} status changed to {status}")
    
    def _get_available_agents_description(self) -> str:
        """获取可用 Agent 描述"""
        lines = []
        for agent_id, config in self.agent_configs.items():
            lines.append(f"- **{config.get('name', agent_id)}** ({agent_id})")
            if config.get('description'):
                lines.append(f"  {config['description']}")
        return "\n".join(lines)
    
    def _format_files(self, files: List[Dict]) -> str:
        """格式化文件列表"""
        if not files:
            return "无"
        return "\n".join([f"- {f['filename']}" for f in files])
    
    def _parse_plan(self, response_text: str) -> Dict:
        """解析规划结果"""
        import re
        import json
        
        # 尝试提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass
        
        # 尝试直接解析
        try:
            return json.loads(response_text)
        except:
            pass
        
        return {"tasks": []}
    
    def _calculate_execution_order(self, tasks: List[Dict]) -> List[List[str]]:
        """
        计算任务执行顺序（拓扑排序）
        
        Returns:
            [[task_ids], [task_ids], ...]  # 按层级
        """
        if not tasks:
            return []
        
        # 构建依赖图
        task_deps = {t["id"]: set(t.get("dependencies", [])) for t in tasks}
        task_ids = set(task_deps.keys())
        
        # 验证依赖
        for task_id, deps in task_deps.items():
            invalid_deps = deps - task_ids
            if invalid_deps:
                logger.warning(f"Task {task_id} has invalid dependencies: {invalid_deps}")
                task_deps[task_id] = deps - invalid_deps
        
        # 拓扑排序（Kahn 算法）
        result = []
        remaining = dict(task_deps)
        
        while remaining:
            # 找到没有依赖的任务
            ready = [tid for tid, deps in remaining.items() if not deps]
            
            if not ready:
                # 存在循环依赖
                logger.error("Circular dependency detected in tasks")
                break
            
            result.append(ready)
            
            # 移除已完成的任务，更新依赖
            for tid in ready:
                del remaining[tid]
                for other_deps in remaining.values():
                    other_deps.discard(tid)
        
        return result
    
    def _create_leader_instance(self) -> AgentInstance:
        """创建 Leader Agent 实例"""
        leader_config = {
            "name": "主治医师",
            "full_content": """你是一位资深的主治医师，负责组织和协调多学科会诊。

## 你的职责

1. 分析患者的病情和需求
2. 决定需要哪些专科专家参与会诊
3. 为每个专家分配具体的分析任务
4. 确保信息流通，协调专家之间的协作
5. 综合各方意见，形成最终诊断和治疗建议

## 规划原则

1. **合理分工**：根据专家专长分配任务
2. **信息流动**：确保后序专家能获得前序专家的分析结果
3. **并行优化**：无依赖的任务应并行执行
4. **资源节约**：避免不必要的专家调用

## 输出格式

请以 JSON 格式输出任务规划。

"""
        }
        
        return self._create_agent_instance("leader")
    
    def _generate_final_report(self, user_message: str, context: Dict) -> str:
        """生成最终报告"""
        # 使用 Leader Agent 汇总所有结果
        leader_instance = self._create_leader_instance()
        
        # 构建汇总消息
        summary_message = f"""请根据以下专家的分析结果，生成最终的综合会诊报告：

## 患者原始请求
{user_message}

## 各专家分析结果

"""
        for task_id, result in self.agent_results.items():
            summary_message += f"### {result['agent_name']}\n\n"
            summary_message += result['output'][:2000]  # 限制长度
            summary_message += "\n\n"
        
        summary_message += """
请生成一份完整的、结构化的会诊报告，包括：
1. 患者情况概述
2. 各科专家意见摘要
3. 综合诊断结论
4. 治疗建议
5. 后续随访计划
"""
        
        agent_context = AgentContext(
            session_id=context.get("session_id", ""),
            conversation_id=context.get("conversation_id", 0),
            task_id="final_report",
            workspace_dir=context.get("workspace_dir", ""),
            files=context.get("files", []),
            other_agent_results=self.agent_results
        )
        
        final_report = ""
        for event in leader_instance.execute_task(summary_message, agent_context):
            if event.get("type") == "agent_complete":
                final_report = event.get("output", "")
        
        return final_report
```

---

## 六、前端实时展示

```vue
<!-- frontend/src/components/MultiAgentExecution.vue -->
<template>
  <div class="multi-agent-execution">
    <!-- 整体进度 -->
    <div class="execution-header">
      <div class="phase-indicator">
        <span :class="{ active: currentPhase === 'planning' }">📋 规划中</span>
        <span :class="{ active: currentPhase === 'executing' }">⚙️ 执行中</span>
        <span :class="{ active: currentPhase === 'finalizing' }">📝 生成报告</span>
      </div>
    </div>

    <!-- Agent 卡片网格 -->
    <div class="agents-grid">
      <div
        v-for="agent in agents"
        :key="agent.id"
        :class="['agent-card', agent.status]"
      >
        <div class="agent-header">
          <span class="agent-icon">{{ getAgentIcon(agent.id) }}</span>
          <span class="agent-name">{{ agent.name }}</span>
          <span class="agent-status">{{ getStatusText(agent.status) }}</span>
        </div>
        
        <!-- Agent 任务描述 -->
        <div v-if="agent.task" class="agent-task">
          {{ agent.task }}
        </div>
        
        <!-- Agent 工具调用 -->
        <div v-if="agent.toolCalls.length" class="tool-calls">
          <div
            v-for="(call, idx) in agent.toolCalls"
            :key="idx"
            class="tool-call-item"
          >
            <span class="tool-icon">🔧</span>
            <span class="tool-name">{{ call.name }}</span>
            <span :class="['call-status', call.success ? 'success' : 'failed']">
              {{ call.success ? '✓' : '✗' }}
            </span>
          </div>
        </div>
        
        <!-- Agent 输出预览 -->
        <div v-if="agent.output" class="agent-output">
          <MarkdownRenderer :content="agent.output.slice(0, 300) + '...'" />
        </div>
      </div>
    </div>

    <!-- 实时日志 -->
    <div class="execution-log">
      <div class="log-header">
        <span>📜 执行日志</span>
        <el-button size="small" @click="toggleLog">
          {{ showLog ? '收起' : '展开' }}
        </el-button>
      </div>
      <div v-show="showLog" class="log-content">
        <div
          v-for="(log, idx) in logs"
          :key="idx"
          :class="['log-item', log.type]"
        >
          <span class="log-time">{{ log.time }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  sessionId: String
})

// 状态
const currentPhase = ref('planning')
const agents = reactive({})
const logs = ref([])
const showLog = ref(true)

// 方法
function getAgentIcon(agentId) {
  const icons = {
    'laboratory-expert': '🔬',
    'pathology-expert': '🧬',
    'oncology-expert': '💊',
    'radiology-expert': '📷',
    'surgery-expert': '🔪',
    'leader': '👨‍⚕️'
  }
  return icons[agentId] || '🤖'
}

function getStatusText(status) {
  const statusMap = {
    'idle': '等待中',
    'working': '工作中...',
    'completed': '已完成',
    'failed': '失败'
  }
  return statusMap[status] || status
}

function handleSSEEvent(event) {
  switch (event.type) {
    case 'phase':
      currentPhase.value = event.phase
      addLog(event.message)
      break
      
    case 'plan_created':
      // 初始化 Agent 卡片
      event.tasks.forEach(task => {
        agents[task.id] = {
          id: task.agent_id,
          name: getAgentName(task.agent_id),
          task: task.description,
          status: 'idle',
          toolCalls: [],
          output: ''
        }
      })
      break
      
    case 'task_started':
      if (agents[event.task_id]) {
        agents[event.task_id].status = 'working'
      }
      addLog(`开始执行: ${getAgentName(event.agent_id)}`)
      break
      
    case 'tool_use':
      if (agents[event.task_id]) {
        agents[event.task_id].toolCalls.push({
          name: event.tool_name,
          success: null
        })
      }
      addLog(`${getAgentName(event.agent_id)} 调用工具: ${event.tool_name}`)
      break
      
    case 'tool_result':
      // 更新工具调用状态
      break
      
    case 'agent_complete':
      if (agents[event.task_id]) {
        agents[event.task_id].status = 'completed'
        agents[event.task_id].output = event.output
      }
      addLog(`${event.agent_name} 完成任务`)
      break
      
    case 'final_report':
      // 显示最终报告
      break
  }
}

function addLog(message) {
  logs.value.push({
    time: new Date().toLocaleTimeString(),
    message,
    type: currentPhase.value
  })
}

function getAgentName(agentId) {
  const names = {
    'laboratory-expert': '检验科专家',
    'pathology-expert': '病理科专家',
    'oncology-expert': '肿瘤内科专家',
    'radiology-expert': '影像科专家',
    'surgery-expert': '外科专家',
    'leader': '主治医师'
  }
  return names[agentId] || agentId
}

function toggleLog() {
  showLog.value = !showLog.value
}
</script>
```

---

## 七、总结

这个设计方案实现了您的愿景：

1. **每个 Agent 都是独立的智能体**
   - 有自己的角色、工具、系统提示
   - 独立调用 Claude API
   - 自主决定使用什么工具

2. **Agent 之间可以协作**
   - 通过 `ask_agent` 工具互相请教
   - 依赖任务自动传递结果
   - Leader 协调整体流程

3. **工作流是动态生成的**
   - Leader 根据任务规划分工
   - 自动处理任务依赖关系
   - 无依赖任务并行执行

4. **最终报告由工具生成**
   - Leader 汇总所有结果
   - 可以调用 `report_generate` 工具
   - 输出结构化报告

如果这个方案符合您的期望，请 **toggle to Act mode**，我可以开始实现基础框架。