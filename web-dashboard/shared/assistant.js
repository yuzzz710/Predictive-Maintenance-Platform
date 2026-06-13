/* ══════════════════════════════════════════════════════════════════════
   Judge Explanation Assistant — Siri-orb + floating panel + speech library
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════════════════
     Speech Library — inline, JSON-migratable. Keyed by page + section.
     ═══════════════════════════════════════════════════════════════════ */
  const SPEECH_LIBRARY = {

    /* ── home.html / device-grid.html ── */
    "home.html": {
      "__default__": {
        title: "设备健康状态总览",
        summary: "10×10矩阵实时展示100台CNC机床健康状态，绿色到红色代表从健康到危急的梯度变化",
        speech: {
          what: "设备健康状态总览是整个系统的首页仪表盘。它通过一个10×10的彩色矩阵，实时展示100台CNC数控机床的健康评分——每个格子代表一台设备，颜色从绿色（健康）渐变到红色（危急），让运维人员一眼就能发现哪些设备需要关注。",
          why: "对于工厂来说，一台关键机床的非计划停机可能导致整条产线停摆，每小时损失高达数千美元。这个模块的价值在于：把复杂的传感器数据转化为直观的视觉信号，让不擅长数据分析的运维工程师也能秒级感知全局健康状态。",
          effect: "当前系统监控100台设备，其中健康率约92%，约3台处于危急状态。系统已经自动为这些高危设备生成了维护工单，包含故障根因、所需备件、推荐技师和预估成本——从发现问题到生成可执行方案，全程自动化。",
          relation: "这是整个预测性维护系统的'入口页面'——所有AI分析、策略决策、工单执行最终都反馈到这个矩阵。评委可以看到，我们不是在做一个单纯的数据看板，而是一套从数据采集→异常检测→根因诊断→维护决策→工单执行的完整闭环方案。"
        },
        keywords: ["健康", "矩阵", "设备", "总览", "首页", "CNC", "状态", "颜色", "停机", "健康率"]
      },
      "device-health-grid": {
        title: "设备健康矩阵",
        summary: "10×10网格，每格一台CNC，颜色映射健康评分0-100",
        speech: {
          what: "这是10×10设备健康矩阵——100台CNC机床的可视化健康快照。每个小格子代表一台设备，颜色从翠绿色（健康评分>80）到红色（<30危急），通过颜色梯度一目了然。点击任意格子可以看到该设备的详细传感器参数和AI诊断结果。",
          why: "传统工厂的维护方式是'坏了再修'或'定期保养'——前者造成意外停机，后者浪费大量人力。这套系统把维护模式升级为'基于状态预测的维护'（Predictive Maintenance），核心价值在于：在设备真正出故障之前就发现问题，把维修从'被动响应'变成'主动预防'。",
          effect: "通过逐设备Z-Score基线分析（非全局阈值），系统能捕捉到61%-73%由设备个体差异导致的异常——这是纯全局阈值无法做到的。配置了三种维护策略（成本优先/生产优先/质量优先），可根据工厂当前需求灵活切换。",
          relation: "这个矩阵是系统所有算法的'最终输出端'——从数据预处理、统计推断、ML密度估计到多信号融合决策，五层分析管线的结果最终映射到这个矩阵的颜色上。"
        },
        keywords: ["矩阵", "网格", "格子", "颜色", "健康评分", "CNC"]
      },
      "stats-cards": {
        title: "KPI统计卡片",
        summary: "健康率、危急设备数、维护准确率、待处理工单数四维关键指标",
        speech: {
          what: "这四张KPI卡片分别显示：当前健康设备占比、处于危急状态的设备数量、AI诊断准确率、以及待处理的工单数量。",
          why: "对于管理层来说，不需要看每个设备的细节，这四个数字就能快速判断当前工厂设备健康状况和AI系统运行质量。",
          effect: "数字实时更新，直接读取后端分析CSV数据。准确率在80%-91%之间波动，这是基于30步时序回测验证的真实数据，不是模拟值。",
          relation: "这四张卡片是给管理层看的'摘要视图'——如果需要深入细节，可以点击进入设备矩阵或工单看板。"
        },
        keywords: ["KPI", "统计", "卡片", "健康率", "危急", "准确率", "工单", "指标"]
      },
      "detail-panel": {
        title: "设备详情面板",
        summary: "单台设备的完整诊断报告：传感器趋势、故障根因、维护建议",
        speech: {
          what: "点击矩阵中的任意设备，右侧会滑出这个详情面板。它集成了一台设备的完整诊断信息：四个传感器（电压/电流/温度/转速）的趋势图、Z-Score异常值、ML密度估计、故障根因分析、推荐维护方案、预估成本和所需备件。",
          why: "运维工程师接到告警后，最需要的是'这台设备具体什么问题？严重吗？怎么修？要花多少钱？'——这个面板用一页展示全部关键信息，不需要工程师在多个系统间切换。",
          effect: "面板内的SHAP可解释性图表能将每个告警追溯到具体的传感器参数——比如'CNC_042的告警主要由温度异常贡献（贡献度67%），其次是电压波动（23%）'。这解决了AI黑箱信任问题。",
          relation: "详情面板是系统可解释性能力的集中体现。评委如果问'AI判断准不准？为什么信它？'——用SHAP归因来回答最有说服力。"
        },
        keywords: ["详情", "面板", "SHAP", "传感器", "趋势", "根因", "设备", "诊断"]
      },
      "shap-modal": {
        title: "SHAP可解释性",
        summary: "每个告警可追溯到具体传感器参数和工业根因",
        speech: {
          what: "SHAP（SHapley Additive exPlanations）是一种基于博弈论的机器学习解释方法，它能量化每个传感器参数对最终预测结果的贡献度。在我们的系统中，每个设备的告警都会附带SHAP归因——显示哪个传感器的异常是主要原因。",
          why: "工业场景不同于消费互联网——运维工程师不会信任一个'黑箱AI'的判断。如果系统说'CNC_042需要立刻停机'，工程师一定会问'为什么？'。SHAP可解释性就是这个'为什么'的答案，是赢得用户信任的关键。",
          effect: "系统内置四阶段SHAP管线：RiskDecomposer分解风险信号→StatLayerSHAP计算统计贡献→MLExplainer解释密度估计→LocalExplainer生成自然语言解释。最终呈现给用户的是'温度贡献67%，电压贡献23%，电流贡献10%'这样明确的归因。",
          relation: "SHAP可解释性是项目的核心竞争力之一。评审中如果有人质疑'AI凭什么判断？'——直接打开SHAP弹窗，用数据说话。"
        },
        keywords: ["SHAP", "可解释", "归因", "贡献", "博弈论", "传感器", "黑箱", "信任"]
      },
      "strategy-selector": {
        title: "维护策略选择器",
        summary: "三种维护策略（成本效率/生产效率/质量优先），生成不同数量和成本的工单",
        speech: {
          what: "系统支持三种维护策略：成本效率模式（15张工单，总成本最低）、生产效率模式（20张工单，成本与覆盖平衡，默认推荐）、质量优先模式（30张工单，最高覆盖率）。切换策略后，后端会自动重新计算所有工单、技师排班、备件采购和停机计划。",
          why: "不同时期的工厂需求不同：预算紧张时选择成本效率、正常运营选生产效率、客户审核或质量关键期选质量优先。一套系统适配多种业务场景，避免'一刀切'的僵硬决策。",
          effect: "策略切换在后端执行完整的DAG流水线——从信号列表构建→工业计划生成→备件规划→技师排班→停机调度→策略对比分析，整个过程约3-5秒，前端无刷新更新全部数据。",
          relation: "策略选择是系统'从数据到决策'闭环的关键环节。它能回答管理者最关心的问题：'怎么修最省钱？'和'怎么修最保险？'。"
        },
        keywords: ["策略", "选择", "成本", "生产效率", "质量", "工单", "切换"]
      }
    },

    /* ── index.html (Dashboard 8 tabs) ── */
    "index.html": {
      "__default__": {
        title: "工业智能运维仪表盘",
        summary: "8个Tab完整展示：健康总览→策略对比→技师调度→库存→停机→ML→成本→传感器升级",
        speech: {
          what: "这是完整的工业智能运维仪表盘，包含8个分析Tab页，覆盖从设备健康到成本效益的全维度分析。每个Tab对应运维决策的一个环节，形成一个完整的'感知→分析→决策→执行'链条。",
          why: "单一的设备监控不够——运维管理需要通盘考虑：哪些设备该修、修什么、谁来修、用什么零件、什么时候停机、花多少钱、值不值得升级传感器。这8个Tab恰好覆盖这8个核心问题。",
          effect: "所有数据来自同一批CSV分析结果，前端展示与后端AI Copilot数据完全一致。支持导出CSV、图表交互缩放、策略实时切换。",
          relation: "仪表盘是面向管理者和开发者的'决策中枢'，与首页的设备健康矩阵（面向运维工程师）形成互补。两个页面通过导航栏无缝切换。"
        },
        keywords: ["仪表盘", "仪表", "大盘", "Tab", "分析", "8个"]
      },
      "sec0-overview": {
        title: "全局概览",
        summary: "三策略KPI对比：工单数、成本、覆盖率、技师工时",
        speech: {
          what: "这个Tab展示三种维护策略的全局KPI对比——工单数量、总成本、设备覆盖率、技师总工时。用雷达图和柱状图直观呈现不同策略的取舍关系。",
          why: "管理者做决策时最需要一个'一页看清'的对比视图。这个Tab用4个维度的并行对比，让'选成本还是选质量'的取舍变得可视化。",
          effect: "数据来自后端工业维护计划引擎实时计算。三种策略不是简单的参数调整——每种策略会触发完全不同的设备优先级排序和资源分配逻辑。",
          relation: "这是仪表盘的'总览页'——如果要深入了解某个策略的具体工单，可以跳转到工单看板；要了解成本构成，去成本分析Tab。"
        },
        keywords: ["全局", "概览", "总览", "KPI", "对比", "雷达图"]
      },
      "sec1-health": {
        title: "健康评分与感知升级",
        summary: "设备健康分布直方图、边缘设备列表、传感器升级ROI分析",
        speech: {
          what: "这里展示100台设备的健康评分分布（0-100分）和传感器升级的投资回报分析。健康分是基于8个维度加权计算的综合指标；升级ROI基于三阶段传感器路线图（振动→电流谱→红外热成像）的工程估算。",
          why: "健康评分告诉管理者'当前有多健康'，传感器升级告诉管理者'花多少钱能变得多健康'。两者结合，就是完整的运维投资决策依据。",
          effect: "当前10台设备健康分<40（危险），88台处于劣化状态。传感器方案B（振动+电流谱，投资$639k）预计5年ROI达1136%，是性价比最高的方案。",
          relation: "这个Tab连接'现状评估'和'未来投资'两个决策维度，是整个仪表盘中最面向管理层汇报的页面。"
        },
        keywords: ["健康", "评分", "分布", "传感器", "升级", "ROI", "投资"]
      },
      "sec2-strategy": {
        title: "策略对比分析",
        summary: "三种策略的详细工单对比：单台设备的紧急度、成本、技术员分配",
        speech: {
          what: "这个Tab展示三种策略下的详细工单对比矩阵——每台设备在不同策略下的紧急度评分、预估成本、推荐技术员类型、备件清单。支持按优先级筛选和排序。",
          why: "策略不是抽象概念——它直接决定'CNC_042要不要修？修的话怎么修？派谁修？'。这个Tab让策略的影响变得具体可追踪。",
          effect: "多信号融合决策引擎综合了统计异常（40%）、ML密度（25%）、成本风险（25%）、趋势信号（10%）四个维度，比纯阈值规则更全面。",
          relation: "这是从管理层'策略概念'到执行层'具体工单'的桥梁。策略选择器的后端计算过程，可以通过这个Tab查看最终结果。"
        },
        keywords: ["策略", "对比", "工单", "优先级", "紧急", "排序"]
      },
      "sec3-technician": {
        title: "技师调度",
        summary: "技师负载均衡、技能匹配、排班甘特图",
        speech: {
          what: "展示技师调度方案——按故障模式自动匹配技师类型（电气专家/热力专家/高级技师/初级技师），甘特图显示排班时间线和负载分布。支持成本感知降级（当高级技师超负荷时自动降级到标准技师）。",
          why: "技师是企业最宝贵的运维资源。派错了人（让电气专家去修热力故障）既浪费技能又可能修不好。系统根据故障模式自动匹配技师技能，同时考虑负载均衡，避免某些技师过劳而其他人空闲。",
          effect: "成本感知降级机制可降低技师人工成本15%-25%——非关键设备的维护由标准技师执行即可，只有在ALARM级别且特定故障模式时才分配专家。",
          relation: "技师调度与工单分配、备件库存、停机窗口四者联动——一个环节的变更会自动触发其他环节的重新计算。"
        },
        keywords: ["技师", "调度", "排班", "甘特图", "负载", "技能", "匹配"]
      },
      "sec4-inventory": {
        title: "库存策略",
        summary: "(s,S)最优库存策略、17种备件管理、采购建议",
        speech: {
          what: "展示17种备件的(s,S)库存策略——当库存低于s（补货点）时，自动建议补货到S（目标库存）。包含当前库存量、需求量、缺口量、建议采购数量、供应商信息和预估到货日期。",
          why: "备件库存管理是运维成本控制的关键——库存太多占用资金（轴承单价$450，存100个就是$45,000），库存太少则维修时缺件导致设备停等。(s,S)策略在库存持有成本和缺货风险之间找到数学最优解。",
          effect: "系统实时对比当前库存与维护工单需求，自动计算每种备件的缺口。缺零件时可以一键生成采购申请单，包含供应商、数量、金额和预计到货日期。",
          relation: "库存数据与工单计划直接关联——策略切换导致工单数变化时，备件需求也会自动重新计算。属于'决策→执行'闭环中的物资保障环节。"
        },
        keywords: ["库存", "备件", "s,S", "采购", "零件", "供应商"]
      },
      "sec5-downtime": {
        title: "停机调度",
        summary: "停机窗口规划、生产影响评估、紧急度排序",
        speech: {
          what: "停机调度模块规划每台待维修设备的停机窗口——综合考虑生产排期、设备紧急度、技师可用时间和备件到位时间，给出最优停机时间建议，并评估每次停机对生产的经济影响。",
          why: "维修必然要停机，但何时停机影响巨大——在生产旺季停一台关键设备可能导致订单违约。系统通过紧急度评分量化'不修的代价'，通过生产影响评估量化'修的成本'，两者权衡得出最优停机时间。",
          effect: "停机调度算法优先考虑：①紧急度评分（不修会坏吗？）②生产影响（停机会损失多少钱？）③资源可用性（技师和备件到位了吗？）。三因素加权排序。",
          relation: "停机窗口确定后，技师排班和备件到货时间都必须与窗口对齐——它是整个维护执行计划的'时间锚点'。"
        },
        keywords: ["停机", "调度", "停机窗口", "生产影响", "紧急度"]
      },
      "sec6-ml": {
        title: "ML异常检测详情",
        summary: "多信号融合检测结果、故障模式识别、局部密度估计",
        speech: {
          what: "这个Tab展示机器学习层的检测结果——包括KDE局部密度估计（LOF替代方案）、故障模式聚类、多信号融合决策权重。每个检测结果都有置信度评分。",
          why: "纯统计方法（Z-Score）擅长发现已知模式的异常，但对复杂的多传感器耦合故障不够敏感。ML层通过无监督密度估计补充统计方法的盲区——两者互补，形成一个更完整的异常检测体系。",
          effect: "ML密度估计的决策权重为25%（低于统计的40%，高于趋势的10%）——这个权重不是拍脑门定的，而是基于2999行真实训练数据上的算法对比实验确定的。",
          relation: "ML层是系统'多信号融合'架构的三大支柱之一（统计+ML+成本风险）。它可以作为独立模块运行，也支持在降级场景下被关闭（退回到纯统计模式）。"
        },
        keywords: ["ML", "机器学习", "异常检测", "KDE", "LOF", "聚类", "密度"]
      },
      "sec7-cost": {
        title: "成本与ROI分析",
        summary: "维护成本拆解、节约预估、策略ROI对比",
        speech: {
          what: "成本分析模块提供维护成本的全维度拆解——维修费、备件费、人工费、停机损失、预期节约。支持按设备、按策略、按时间周期汇总和分析。",
          why: "运维决策的终极标准是ROI。这个Tab回答核心问题：'花了多少钱？省了多少钱？值不值得？'——用数字而不是直觉来做运维投资决策。",
          effect: "系统预估生产效率策略下年节省约$1.2M（对比纯被动维修模式）。节省来自三个方面：减少非计划停机（60-80%）、优化备件库存（降低15-25%持有成本）、精准技师调度（减少15-25%人工浪费）。",
          relation: "成本分析是'决策→结果'的反馈环节。每次策略切换后，成本数据会重新计算，形成持续改进的闭环。"
        },
        keywords: ["成本", "ROI", "钱", "节约", "节省", "费用", "分析", "投资回报"]
      }
    },

    /* ── chat.html ── */
    "chat.html": {
      "__default__": {
        title: "AI Copilot 智能助手",
        summary: "基于DeepSeek + MCP Tool Calling的工业AI对话系统",
        speech: {
          what: "AI Copilot是整个系统的智能交互入口。它不是普通的聊天机器人——它集成了23个MCP（Model Context Protocol）工具，可以直接查询设备状态、执行根因分析、生成维护报告、触发策略切换、管理工单流程。相当于为运维团队配备了一个24小时在线的工业AI专家。",
          why: "传统工业软件的问题在于'功能强大但难用'——要找某个设备的状态需要点5-10次菜单。AI Copilot让用户用自然语言直接提问：'CNC_042为什么风险高？'——系统自动调用工具链，3-5秒内给出诊断报告。这大大降低了系统的使用门槛。",
          effect: "AI Copilot支持23种工具调用、RAG知识检索（BGE向量检索+ChromaDB）、SSE流式对话、Markdown富文本渲染、ECharts图表内联、报告一键生成。响应时间中位数约1.5秒（含工具调用）。",
          relation: "AI Copilot是整个系统的'统一入口'——所有数据查询、分析、决策、执行功能都可以通过对话完成。它是连接用户和底层分析能力的桥梁。"
        },
        keywords: ["Copilot", "AI", "对话", "助手", "智能", "聊天", "DeepSeek"]
      },
      "rag-system": {
        title: "RAG知识检索系统",
        summary: "三层知识库（系统文档/运维知识/故障案例）+ BGE向量检索",
        speech: {
          what: "RAG（Retrieval-Augmented Generation）系统在AI回答用户问题前，先从三层知识库中检索最相关的文档内容，注入到AI的上下文中。这确保AI的回答基于真实的系统文档和故障案例，而不是'幻觉'或训练数据的模糊记忆。",
          why: "通用AI不了解我们项目的具体架构、算法细节、故障处理流程。RAG相当于给AI配了一个'项目专属知识库'——回答'健康分怎么算？'时，AI能从系统设计文档中找到准确的8维度加权公式，而不是编造一个。",
          effect: "三层知识库：①系统文档（sys_docs）——项目架构、算法原理、功能说明；②运维知识（maint_kb）——设备维护步骤、安全规范；③故障案例（fault_cases）——历史故障及修复记录。支持BGE-small-zh-v1.5本地嵌入（~15ms）和DeepSeek API嵌入（~300ms）双层回退。",
          relation: "RAG是AI Copilot'专业性'的保障。没有RAG，AI只是一个通用助手；有了RAG，AI才是真正懂这个项目的'专属顾问'。"
        },
        keywords: ["RAG", "检索", "知识库", "BGE", "向量", "ChromaDB", "embedding"]
      },
      "agent-log": {
        title: "Agent决策日志",
        summary: "每次AI对话的工具调用链、耗时、成功/失败状态",
        speech: {
          what: "Agent决策日志展示AI在回答每个问题时调用了哪些工具、每个工具的执行时间、是否成功。这是一个透明的'AI工作流水账'。",
          why: "对于开发者和管理者来说，AI的决策过程需要可审计——Agent日志让每一次工具调用都有迹可循，符合工业级可追溯性要求。",
          effect: "日志显示每轮工具调用的耗时、成功/失败状态、以及RAG检索的命中情况。可以用这些数据持续优化AI的工具选择策略。",
          relation: "Agent日志是系统'可观测性'的组成部分——配合前端的降级状态指示器、健康检查接口和工单状态机审计轨迹，构成完整的运维可追溯体系。"
        },
        keywords: ["日志", "Agent", "工具调用", "决策", "可追溯", "审计"]
      }
    },

    /* ── technical-overview.html ── */
    "technical-overview.html": {
      "__default__": {
        title: "技术架构总览",
        summary: "五层分析管线 + DAG流水线 + 四级降级 + 三角色权限",
        speech: {
          what: "技术架构总览页面向评委展示系统的完整技术骨架——从数据预处理到最终决策的五层分析管线、DAG并行调度引擎、四级降级保障体系、角色分版的CSS过滤机制、以及数据天花板（Youden's J）的可视化演示。",
          why: "对于技术评委来说，最有说服力的不是'我们做了什么'，而是'我们怎么做的以及为什么这样做是对的'。这个页面用公式、图表、代码片段和交互式演示，完整呈现项目的技术深度。",
          effect: "核心数据指标：4参数Youden's J≤0.075（纯ML不可行）→多信号融合后J升至~0.90、设备间方差占61-73%（必须逐设备基线）、四级降级保障任何条件下产出可执行方案、SHAP归因可追溯到具体参数。",
          relation: "这个页面是项目的'技术说明书'——其他页面展示'能力'，这个页面展示'为什么有这个能力'。答辩时如果有评委问'你们的创新点在哪'，引导他们看这个页面。"
        },
        keywords: ["技术", "架构", "架构图", "管线", "DAG", "降级", "角色", "权限"]
      },
      "sec-architecture": {
        title: "五层分析管线架构",
        summary: "数据准备→统计推断→ML推断→诊断→决策，每层独立可降级",
        speech: {
          what: "系统采用五层分析管线架构：①数据预处理（质量检查+基线建立）→②统计推断（逐设备Z-Score+T²检验）→③ML推断（KDE密度估计）→④诊断（SHAP归因+风险分解）→⑤决策（多信号融合+策略选择+工单生成）。每层独立运行，支持按需降级。",
          why: "工业系统的核心要求是'韧性'——任何一层出问题都不能让整个系统瘫痪。五层架构的独立性保证了：即使ML层不可用，系统可以降级到统计+规则模式，仍然能产出可执行的维护方案。这是'工业级'和'实验室级'的本质区别。",
          effect: "DAG调度引擎通过ThreadPool并行执行无依赖的Skill节点，完整流水线耗时约9秒（统计模式）到15秒（全模式含ML+诊断）。每层有独立的输出目录和版本号，支持断点续跑。",
          relation: "这个架构是项目技术方案的核心创新——将学术界独立的统计方法、ML方法和运筹学方法整合为工业场景可用的工程系统。"
        },
        keywords: ["五层", "管线", "流水线", "架构", "层次", "独立", "DAG"]
      },
      "youden-j-demo": {
        title: "Youden's J 数据天花板",
        summary: "4参数J≤0.075（纯ML上限≈0.537），多信号融合补偿后J→0.90",
        speech: {
          what: "Youden's J是衡量传感器区分故障能力的标准指标（=灵敏度+特异度-1，范围-1到1）。系统现有的4个传感器参数（电压/电流/温度/转速）的Youden's J最高仅0.075——这意味着单靠传感器数据，96-98%的故障无法被区分。",
          why: "这是项目最重要的技术洞察：不是我们的算法不够好，而是4个基础传感器提供的信息量本身就有限。认识到这个'数据天花板'后，系统设计了多信号融合补偿策略（统计+ML+成本+趋势），将实际决策能力从J=0.075提升到约0.90。",
          effect: "页面上有交互式KDE分布演示——评委可以拖拽滑块对比'纯传感器'和'融合后'的故障区分能力。三阶段传感器升级路线（振动→电流谱→红外）展示从J=0.075到J=0.90的升级路径。",
          relation: "Youden's J分析是项目'知其所以然'的体现——不是盲目堆算法，而是从数据特性出发设计解决方案。这是技术答辩中最有力的论据。"
        },
        keywords: ["Youden", "天花板", "数据", "极限", "J", "KDE", "区分", "传感器局限"]
      },
      "sec-decision": {
        title: "多信号融合决策引擎",
        summary: "统计40% + ML 25% + 成本25% + 趋势10% → 综合决策",
        speech: {
          what: "决策引擎将四个独立信号源（统计异常、ML密度、成本风险、趋势预警）按权重融合为综合决策。权重不是主观设定的——通过benchmark_algorithms.py在2999行真实数据上训练验证，确保每个权重的合理性。",
          why: "单一信号源各有盲区：统计方法对渐进式退化敏感但噪声多、ML对复杂模式敏感但需要大量数据、成本分析直接但只关注经济影响。四个信号融合后，盲区互相覆盖，决策质量远高于任何单一方法。",
          effect: "融合后的AUC从纯ML的0.537提升到约0.90（基于真实数据回测）。30步expanding window时序回测验证了方法的统计有效性——不是一次性的好运气，而是稳定的性能提升。",
          relation: "决策引擎是五层管线的'最终汇聚点'——上游所有分析的结果在这里被融合为可执行方案。它直接产出工单、技师分配、备件计划和停机窗口。"
        },
        keywords: ["融合", "决策", "引擎", "权重", "信号", "统计", "ML", "成本"]
      },
      "sec-degradation": {
        title: "四级降级保障体系",
        summary: "FULL→STAT_ONLY→RULE_ONLY→EMERGENCY，任何条件都能产出可执行方案",
        speech: {
          what: "四级降级保障是系统的'韧性'设计：①FULL（全功能，ML+诊断完整）→②STAT_ONLY（仅统计，ML和诊断关闭）→③RULE_ONLY（纯规则，仅用预定义阈值）→④EMERGENCY（应急模式，仅工单执行+库存保障）。降级由系统自动检测触发，也可手动切换。",
          why: "工业场景的底线是'绝对不能停'——AI服务挂了、数据源断了、模型加载失败了，系统仍然要能指导维护工作。四级降级保证了从'最佳状态'到'最差状态'的平滑过渡，任何条件下都能产出可执行的维护方案。",
          effect: "降级状态在前端有实时指示器（导航栏底部），用户随时能看到当前系统运行级别。降级事件会被记录到数据库，用于事后分析和系统优化。",
          relation: "降级保障是区分'学术演示系统'和'工业可部署系统'的关键特征——学术系统默认一切正常，工业系统默认一切都会出问题。"
        },
        keywords: ["降级", "保障", "四级", "韧性", "应急", "FULL", "STAT", "RULE", "EMERGENCY"]
      }
    },

    /* ── device-grid.html (share with home) ── */
    "device-grid.html": {
      "__default__": {
        title: "设备健康矩阵",
        summary: "独立10×10设备健康矩阵视图",
        speech: {
          what: "这是独立的设备健康矩阵页面，展示10×10格子的100台CNC机床健康状态。每个格子代表一台设备，颜色从绿到红对应健康评分从高到低。点击格子可以查看该设备的详细诊断信息。",
          why: "这个视图专注于设备监控——去掉管理层的KPI卡片和策略选择器，给运维工程师一个纯粹、高效的设备状态总览。适合投在大屏上做实时监控。",
          effect: "支持缩放、排序、筛选。健康评分每5分钟自动刷新（基于最近数据），告警设备自动置顶高亮。",
          relation: "与首页的矩阵共享同一套数据和渲染逻辑（device-grid-component.js），但界面更简洁、加载更快。"
        },
        keywords: ["矩阵", "网格", "设备", "健康", "大屏", "监控"]
      }
    }
  };

  /* ═══════════════════════════════════════════════════════════════════
     Context Extractor
     ═══════════════════════════════════════════════════════════════════ */
  function extractContext() {
    const path = window.location.pathname;
    const page = path.split('/').pop() || 'home.html';
    const ctx = { page, sections: [], viewportHeading: null, hashTarget: null };

    // 1. URL hash
    const hash = window.location.hash;
    if (hash) {
      ctx.hashTarget = hash.replace('#', '');
      const el = document.getElementById(ctx.hashTarget);
      if (el) {
        const h = el.querySelector('h1, h2, h3, h4');
        ctx.viewportHeading = h ? h.textContent.trim().slice(0, 60) : null;
      }
    }

    // 2. Visible data-speech attributes
    const speechEls = document.querySelectorAll('[data-speech]');
    for (const el of speechEls) {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        ctx.sections.push({
          key: el.getAttribute('data-speech'),
          title: el.getAttribute('data-speech-title') || '',
          visible: true,
          distanceFromTop: rect.top
        });
      }
    }

    // 3. Visible headings (fallback)
    if (!ctx.viewportHeading && ctx.sections.length === 0) {
      const headings = document.querySelectorAll('h2, h3, .glass-card h4, .section-title');
      for (const h of headings) {
        const rect = h.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.6 && rect.top > -50) {
          ctx.viewportHeading = h.textContent.trim().slice(0, 60);
          break;
        }
      }
    }

    // Sort sections by distance from top (nearest first)
    ctx.sections.sort((a, b) => a.distanceFromTop - b.distanceFromTop);

    return ctx;
  }

  /* ═══════════════════════════════════════════════════════════════════
     Speech Matcher
     ═══════════════════════════════════════════════════════════════════ */
  function matchSpeech(context, userQuestion) {
    const page = context.page;
    const lib = SPEECH_LIBRARY[page] || SPEECH_LIBRARY['home.html'];

    // Priority order:
    // 1. Exact match from data-speech attribute
    // 2. Hash target match
    // 3. Viewport heading keyword match
    // 4. User question keyword match
    // 5. Page default

    // 1. data-speech exact match
    const dataSpeechKey = context.sections[0]?.key;
    if (dataSpeechKey && lib[dataSpeechKey]) {
      return { ...lib[dataSpeechKey], matchType: 'exact', matchKey: dataSpeechKey };
    }

    // 2. Hash target match
    if (context.hashTarget && lib[context.hashTarget]) {
      return { ...lib[context.hashTarget], matchType: 'hash', matchKey: context.hashTarget };
    }

    // 3. Viewport heading keyword match
    if (context.viewportHeading) {
      const headingLower = context.viewportHeading.toLowerCase();
      let bestScore = 0;
      let bestMatch = null;
      for (const [key, entry] of Object.entries(lib)) {
        if (key === '__default__') continue;
        const score = (entry.keywords || []).filter(kw => headingLower.includes(kw.toLowerCase())).length;
        if (score > bestScore) { bestScore = score; bestMatch = { ...entry, matchKey: key }; }
      }
      if (bestScore >= 2) return { ...bestMatch, matchType: 'heading' };
    }

    // 4. User question keyword match
    if (userQuestion) {
      const qLower = userQuestion.toLowerCase();
      let bestScore = 0;
      let bestMatch = null;
      for (const [key, entry] of Object.entries(lib)) {
        if (key === '__default__') continue;
        const score = (entry.keywords || []).filter(kw => qLower.includes(kw.toLowerCase())).length;
        if (score > bestScore) { bestScore = score; bestMatch = { ...entry, matchKey: key }; }
      }
      if (bestScore >= 1) return { ...bestMatch, matchType: 'question' };
    }

    // 5. Page default
    if (lib.__default__) {
      return { ...lib.__default__, matchType: 'default', matchKey: '__default__' };
    }

    return null;
  }

  /* ═══════════════════════════════════════════════════════════════════
     Assistant Panel
     ═══════════════════════════════════════════════════════════════════ */
  class AssistantPanel {
    constructor() {
      this.isOpen = false;
      this.currentSpeech = null;
      this.currentContext = null;
      this.aiTextBuffer = '';
      this._dragging = false;
      this._dragStartX = 0;
      this._dragStartY = 0;
      this._dragOrigLeft = 0;
      this._dragOrigTop = 0;
      this._buildDOM();
      this._restorePosition();
      this._bindEvents();
    }

    /* ── Build DOM ── */
    _buildDOM() {
      // Overlay
      this.overlay = document.createElement('div');
      this.overlay.className = 'assistant-overlay';
      this.overlay.addEventListener('click', () => this.close());
      document.body.appendChild(this.overlay);

      // Orb
      const container = document.createElement('div');
      container.className = 'assistant-orb-container';
      container.innerHTML = `
        <button class="assistant-orb" title="评委讲解助手（可拖拽移动）" aria-label="打开评委讲解助手">
          💬
          <span class="assistant-orb-pulse"></span>
          <span class="assistant-orb-pulse"></span>
          <span class="assistant-orb-pulse"></span>
        </button>
      `;
      this.orbContainer = container;
      this.orbBtn = container.querySelector('.assistant-orb');
      this.orbBtn.addEventListener('click', (e) => {
        // Don't open if the mouse moved between mousedown and mouseup (was a drag)
        if (Math.abs(e.clientX - this._dragStartX) > 4 ||
            Math.abs(e.clientY - this._dragStartY) > 4) return;
        this.open();
      });
      document.body.appendChild(container);

      // Panel
      const panel = document.createElement('div');
      panel.className = 'assistant-panel';
      panel.innerHTML = `
        <div class="assistant-panel-header">
          <div class="assistant-panel-title">
            <span>💬</span>
            <span class="assistant-panel-context">评委讲解</span>
          </div>
          <button class="assistant-panel-close" aria-label="关闭">✕</button>
        </div>
        <div class="assistant-panel-body"></div>
        <div class="assistant-panel-footer" style="display:none"></div>
      `;
      this.panel = panel;
      this.headerTitle = panel.querySelector('.assistant-panel-context');
      this.body = panel.querySelector('.assistant-panel-body');
      this.footer = panel.querySelector('.assistant-panel-footer');
      this.closeBtn = panel.querySelector('.assistant-panel-close');
      document.body.appendChild(panel);
    }

    /* ── Bind events ── */
    _bindEvents() {
      this.closeBtn.addEventListener('click', () => this.close());

      // ESC key
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.isOpen) {
          this.close();
          this.orbBtn.focus();
        }
      });

      // ── Drag: mouse (attach on mousedown, remove on mouseup) ──
      this._onMouseMove = (e) => this._onDragMove(e.clientX, e.clientY);
      this._onMouseUp = () => this._onDragEnd();
      this._onTouchMove = (e) => {
        if (!this._dragging) return;
        e.preventDefault();
        const t = e.touches[0];
        this._onDragMove(t.clientX, t.clientY);
      };
      this._onTouchEnd = () => this._onDragEnd();

      this.orbBtn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        this._onDragStart(e.clientX, e.clientY);
        window.addEventListener('mousemove', this._onMouseMove);
        window.addEventListener('mouseup', this._onMouseUp);
      });

      this.orbBtn.addEventListener('touchstart', (e) => {
        const t = e.touches[0];
        this._onDragStart(t.clientX, t.clientY);
        window.addEventListener('touchmove', this._onTouchMove, { passive: false });
        window.addEventListener('touchend', this._onTouchEnd);
      }, { passive: false });
    }

    /* ── Drag handlers ── */
    _onDragStart(clientX, clientY) {
      this._dragStartX = clientX;
      this._dragStartY = clientY;
      this._dragOrigLeft = this.orbContainer.offsetLeft;
      this._dragOrigTop = this.orbContainer.offsetTop;
    }

    _onDragMove(clientX, clientY) {
      const dx = clientX - this._dragStartX;
      const dy = clientY - this._dragStartY;
      // Only start dragging after 4px threshold (distinguishes click from drag)
      if (!this._dragging && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      if (!this._dragging) {
        this._dragging = true;
        this.orbBtn.classList.add('dragging');
      }
      let newLeft = this._dragOrigLeft + dx;
      let newTop = this._dragOrigTop + dy;
      // Clamp to viewport
      const size = 56;
      newLeft = Math.max(8, Math.min(window.innerWidth - size - 8, newLeft));
      newTop = Math.max(8, Math.min(window.innerHeight - size - 8, newTop));
      this.orbContainer.style.left = newLeft + 'px';
      this.orbContainer.style.top = newTop + 'px';
      // Move panel too if open
      if (this.isOpen) this._positionPanel();
    }

    _onDragEnd() {
      window.removeEventListener('mousemove', this._onMouseMove);
      window.removeEventListener('mouseup', this._onMouseUp);
      window.removeEventListener('touchmove', this._onTouchMove);
      window.removeEventListener('touchend', this._onTouchEnd);
      if (this._dragging) {
        this._dragging = false;
        this.orbBtn.classList.remove('dragging');
        this._savePosition();
      }
    }

    /* ── Position panel relative to orb ── */
    _positionPanel() {
      const orbRect = this.orbContainer.getBoundingClientRect();
      const panelW = this.panel.offsetWidth || 400;
      const panelH = this.panel.scrollHeight || 300;
      const gap = 14;
      // Prefer panel above orb
      let top = orbRect.top - panelH - gap;
      if (top < 12) {
        // Not enough room above → place below orb
        top = orbRect.bottom + gap;
        if (top + panelH > window.innerHeight - 12) {
          top = window.innerHeight - panelH - 12;
        }
      }
      // Right-align panel to orb
      let left = orbRect.right - panelW;
      if (left < 12) left = 12;
      if (left + panelW > window.innerWidth - 12) left = window.innerWidth - panelW - 12;
      this.panel.style.left = left + 'px';
      this.panel.style.top = top + 'px';
    }

    /* ── Save / restore orb position ── */
    _savePosition() {
      try {
        localStorage.setItem('assistant-orb-left', this.orbContainer.style.left);
        localStorage.setItem('assistant-orb-top', this.orbContainer.style.top);
      } catch (e) { /* quota exceeded, ignore */ }
    }

    _restorePosition() {
      try {
        const left = localStorage.getItem('assistant-orb-left');
        const top = localStorage.getItem('assistant-orb-top');
        if (left) this.orbContainer.style.left = left;
        if (top) this.orbContainer.style.top = top;
      } catch (e) { /* ignore */ }
    }

    /* ── Open ── */
    async open(question) {
      if (this.isOpen) return;
      this.isOpen = true;

      // Extract context
      this.currentContext = extractContext();

      // Match speech
      this.currentSpeech = matchSpeech(this.currentContext, question);

      // Update UI
      this.orbBtn.classList.add('active');
      this.overlay.classList.add('active');
      this._positionPanel();
      this.panel.classList.add('open');

      const ctxTitle = this.currentSpeech?.title || this.currentContext.viewportHeading || '评委讲解';
      this.headerTitle.textContent = ctxTitle;
      this._updatePanelTitle();

      // Render
      if (question && (!this.currentSpeech || this.currentSpeech.matchType === 'default')) {
        // User asked a question with no direct match → AI fallback
        await this._renderAIFallback(question);
      } else if (this.currentSpeech) {
        this._renderSpeech(this.currentSpeech);
      } else {
        this._renderEmpty();
      }
    }

    /* ── Close ── */
    close() {
      if (!this.isOpen) return;
      this.isOpen = false;
      this.currentSpeech = null;
      this.currentContext = null;
      this.aiTextBuffer = '';
      this.orbBtn.classList.remove('active');
      this.overlay.classList.remove('active');
      this.panel.classList.remove('open');
    }

    /* ── Toggle ── */
    toggle() {
      if (this.isOpen) this.close();
      else this.open();
    }

    /* ── Update panel title ── */
    _updatePanelTitle() {
      const pageName = this._pageName();
      const sectionName = this.currentSpeech?.title || '';
      this.headerTitle.textContent = pageName + (sectionName ? ' · ' + sectionName : '');
    }

    _pageName() {
      const page = this.currentContext?.page || '';
      const map = {
        'home.html': '设备健康总览',
        'index.html': '仪表盘',
        'chat.html': 'AI Copilot',
        'technical-overview.html': '技术架构',
        'device-grid.html': '设备矩阵'
      };
      return map[page] || page || '当前页面';
    }

    /* ── Render matched speech ── */
    _renderSpeech(speech) {
      const sections = [
        { label: '📌 这个模块做什么？', key: 'what' },
        { label: '🎯 为什么重要？', key: 'why' },
        { label: '📊 效果如何？', key: 'effect' },
        { label: '🔗 和项目整体关系？', key: 'relation' }
      ];

      let html = '';
      if (speech.matchType && speech.matchType !== 'default') {
        html += `<div style="font-size:11px;color:#8e8e93;margin-bottom:12px;">
          已匹配话术：<span style="color:#0d7d6e;">${this._escapeHtml(speech.title)}</span>
          ${speech.matchType === 'exact' ? '(精确定位)' : speech.matchType === 'heading' ? '(标题匹配)' : '(关键词匹配)'}
        </div>`;
      }

      for (const sec of sections) {
        const text = speech.speech?.[sec.key];
        if (text) {
          html += `<div class="assistant-speech-section">
            <div class="assistant-speech-label">${sec.label}</div>
            <div class="assistant-speech-text">${text}</div>
          </div>`;
        }
      }

      this.body.innerHTML = html;
      this.body.scrollTop = 0;
      this._showFooter('matched');
    }

    /* ── Render AI fallback ── */
    async _renderAIFallback(question) {
      this._showLoading();

      try {
        const context = {
          page: this.currentContext?.page || '',
          section: this.currentSpeech?.title || this.currentContext?.viewportHeading || '',
          title: this.currentSpeech?.title || ''
        };

        const response = await fetch('/api/assistant/explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context, question, mode: 'explain' })
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }

        this.aiTextBuffer = '';
        this.body.innerHTML = '<div class="assistant-ai-text"><span class="cursor-blink"></span></div>';
        const textEl = this.body.querySelector('.assistant-ai-text');

        // SSE streaming
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'text_delta') {
                this.aiTextBuffer += event.text;
                textEl.innerHTML = this._formatAI(this.aiTextBuffer) + '<span class="cursor-blink"></span>';
                this.body.scrollTop = this.body.scrollHeight;
              } else if (event.type === 'error') {
                textEl.innerHTML = `<div class="assistant-error-text">${this._escapeHtml(event.message)}</div>`;
              } else if (event.type === 'done') {
                textEl.innerHTML = this._formatAI(this.aiTextBuffer);
              }
            } catch (e) { /* skip malformed lines */ }
          }
        }

        textEl.innerHTML = this._formatAI(this.aiTextBuffer);
        this._showFooter('ai');
      } catch (e) {
        this.body.innerHTML = `<div class="assistant-error">
          <div class="assistant-error-icon">⚠️</div>
          <div class="assistant-error-text">AI生成失败</div>
          <div style="font-size:11px;color:#8e8e93;margin-top:8px;">
            请到 <a href="/chat" style="color:#0d7d6e;">AI Copilot</a> 页面深入交流
          </div>
        </div>`;
        this._showFooter('error');
      }
    }

    /* ── Render empty state ── */
    _renderEmpty() {
      this.body.innerHTML = `<div class="assistant-empty">
        <div class="assistant-empty-icon">📭</div>
        <div class="assistant-empty-text">暂未找到匹配的讲解话术</div>
        <div style="font-size:11px;color:#8e8e93;margin-top:6px;">试试输入"解释这个模块"</div>
      </div>`;
      this._showFooter('empty');
    }

    /* ── Show loading ── */
    _showLoading() {
      this.body.innerHTML = `<div class="assistant-loading">
        <div class="assistant-loading-dots"><span></span><span></span><span></span></div>
        <div class="assistant-loading-text">AI正在生成讲解...</div>
      </div>`;
      this.footer.style.display = 'none';
    }

    /* ── Show footer with quick actions ── */
    _showFooter(state) {
      this.footer.style.display = 'flex';
      this.footer.innerHTML = '';

      if (state === 'matched' || state === 'ai') {
        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'assistant-action-btn primary';
        copyBtn.textContent = '📋 复制';
        copyBtn.addEventListener('click', () => this._copyContent());
        this.footer.appendChild(copyBtn);

        // Simplify button
        const simplifyBtn = document.createElement('button');
        simplifyBtn.className = 'assistant-action-btn';
        simplifyBtn.textContent = '🔄 简化一点';
        simplifyBtn.addEventListener('click', () => this._refine('simplify'));
        this.footer.appendChild(simplifyBtn);

        // Expand button
        const expandBtn = document.createElement('button');
        expandBtn.className = 'assistant-action-btn';
        expandBtn.textContent = '📝 展开讲细';
        expandBtn.addEventListener('click', () => this._refine('expand'));
        this.footer.appendChild(expandBtn);

        // Ask follow-up button
        const askBtn = document.createElement('button');
        askBtn.className = 'assistant-action-btn';
        askBtn.textContent = '💬 追问';
        askBtn.addEventListener('click', () => this._openAskInput());
        this.footer.appendChild(askBtn);
      } else if (state === 'empty') {
        const askBtn = document.createElement('button');
        askBtn.className = 'assistant-action-btn primary';
        askBtn.textContent = '💬 手动提问';
        askBtn.addEventListener('click', () => this._openAskInput());
        this.footer.appendChild(askBtn);
      } else if (state === 'error') {
        const retryBtn = document.createElement('button');
        retryBtn.className = 'assistant-action-btn primary';
        retryBtn.textContent = '🔄 重试';
        retryBtn.addEventListener('click', () => this._retry());
        this.footer.appendChild(retryBtn);
      }

      // Close button (always present)
      const closeFtn = document.createElement('button');
      closeFtn.className = 'assistant-action-btn';
      closeFtn.textContent = '✕ 关闭';
      closeFtn.addEventListener('click', () => this.close());
      this.footer.appendChild(closeFtn);
    }

    /* ── Copy content ── */
    async _copyContent() {
      const text = this.body.textContent || '';
      try {
        await navigator.clipboard.writeText(text.trim());
        const btn = this.footer.querySelector('.assistant-action-btn.primary');
        if (btn) {
          const orig = btn.textContent;
          btn.textContent = '✅ 已复制';
          setTimeout(() => { btn.textContent = orig; }, 1500);
        }
      } catch (e) {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text.trim();
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
    }

    /* ── Refine (simplify/expand) ── */
    async _refine(mode) {
      const label = mode === 'simplify' ? '简化' : '展开';
      this._showLoading();

      let question = '';
      if (mode === 'simplify') {
        question = '请把上面的讲解简化，用更短更通俗的话说，保留最核心的3-4句话';
      } else {
        question = '请把上面的讲解展开讲细一点，增加更多技术细节和量化数据';
      }

      // Reuse AI fallback with refine prompt
      this.aiTextBuffer = '';
      this.body.innerHTML = '<div class="assistant-ai-text"><span class="cursor-blink"></span></div>';
      const textEl = this.body.querySelector('.assistant-ai-text');

      try {
        const response = await fetch('/api/assistant/explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            context: {
              page: this.currentContext?.page || '',
              section: this.currentSpeech?.title || '',
              title: this.currentSpeech?.title || ''
            },
            question,
            mode,
            previous_text: this.currentSpeech ? this._speechToText(this.currentSpeech.speech) : this.body.textContent.slice(0, 1500)
          })
        });

        if (!response.ok) throw new Error(`API error: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'text_delta') {
                this.aiTextBuffer += event.text;
                textEl.innerHTML = this._formatAI(this.aiTextBuffer) + '<span class="cursor-blink"></span>';
                this.body.scrollTop = this.body.scrollHeight;
              } else if (event.type === 'done') {
                textEl.innerHTML = this._formatAI(this.aiTextBuffer);
              }
            } catch (e) { /* skip */ }
          }
        }
        textEl.innerHTML = this._formatAI(this.aiTextBuffer);
        this._showFooter('ai');
      } catch (e) {
        this.body.innerHTML = `<div class="assistant-error">
          <div class="assistant-error-icon">⚠️</div>
          <div class="assistant-error-text">${label}生成失败，请重试</div>
        </div>`;
        this._showFooter('error');
      }
    }

    /* ── Open ask input ── */
    _openAskInput() {
      this.body.innerHTML = `<div style="display:flex;flex-direction:column;gap:10px;">
        <div style="font-size:12px;color:#636366;">输入你想了解的问题：</div>
        <textarea id="assistant-ask-input" placeholder="例如：解释这个模块的设计思路..."
          style="width:100%;min-height:60px;background:rgba(0,0,0,0.03);border:1px solid rgba(0,0,0,0.10);border-radius:10px;color:#1c1c1e;padding:10px;font-size:13px;font-family:var(--font-sans);resize:vertical;outline:none;"
          rows="2"></textarea>
        <div style="display:flex;gap:8px;">
          <button id="assistant-ask-submit" class="assistant-action-btn primary" style="font-size:12px;">发送</button>
          <button id="assistant-ask-cancel" class="assistant-action-btn" style="font-size:12px;">取消</button>
        </div>
      </div>`;
      this.footer.style.display = 'none';

      const input = document.getElementById('assistant-ask-input');
      const submit = document.getElementById('assistant-ask-submit');
      const cancel = document.getElementById('assistant-ask-cancel');

      cancel.addEventListener('click', () => {
        if (this.currentSpeech) this._renderSpeech(this.currentSpeech);
        else this._renderEmpty();
      });

      submit.addEventListener('click', async () => {
        const q = input.value.trim();
        if (!q) return;
        this.currentSpeech = matchSpeech(this.currentContext, q);
        if (this.currentSpeech && this.currentSpeech.matchType !== 'default') {
          this._renderSpeech(this.currentSpeech);
          this._showFooter('matched');
        } else {
          await this._renderAIFallback(q);
        }
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          submit.click();
        }
      });

      input.focus();
    }

    /* ── Retry ── */
    async _retry() {
      const q = '请解释当前页面模块';
      this.currentSpeech = matchSpeech(this.currentContext, q);
      if (this.currentSpeech && this.currentSpeech.matchType !== 'default') {
        this._renderSpeech(this.currentSpeech);
        this._showFooter('matched');
      } else {
        await this._renderAIFallback(q);
      }
    }

    /* ── Helpers ── */
    _escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    _formatAI(text) {
      text = text || '';
      // Bold markers
      text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      // Line breaks
      text = text.replace(/\n/g, '<br>');
      return text;
    }

    _speechToText(speech) {
      if (!speech) return '';
      return [speech.what, speech.why, speech.effect, speech.relation].filter(Boolean).join('\n\n');
    }
  }

  /* ═══════════════════════════════════════════════════════════════════
     Quick Ask — respond to "解释这个模块" type prompts in Copilot
     ═══════════════════════════════════════════════════════════════════ */
  function handleQuickAsk(text) {
    if (!window._assistantPanel) return false;
    const triggers = ['解释', '讲解', '介绍', '讲清楚', '说明', '这是什么', '这个模块', '这块', '这个页面', '评委', '答辩'];
    const lower = text.toLowerCase().replace(/\s+/g, '');
    const matchCount = triggers.filter(t => lower.includes(t)).length;

    if (matchCount >= 2 || /^解释|^讲解|^介绍/.test(text.trim())) {
      window._assistantPanel.open(text.trim());
      return true;
    }
    return false;
  }

  /* ═══════════════════════════════════════════════════════════════════
     Initialize
     ═══════════════════════════════════════════════════════════════════ */
  function init() {
    // Don't init on role-gate page
    if (window.location.pathname.includes('role-gate')) return;

    // Don't init if running inside an iframe
    if (window.self !== window.top) return;

    const panel = new AssistantPanel();
    window._assistantPanel = panel;
    window._assistantQuickAsk = handleQuickAsk;

    console.log('[Assistant] Judge explanation assistant ready 💬');
  }

  // Start on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
