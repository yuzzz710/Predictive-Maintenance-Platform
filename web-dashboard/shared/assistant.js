/* ══════════════════════════════════════════════════════════════════════
   Judge Explanation Assistant — Siri-orb + floating panel + speech library
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════════════════
     Speech Library — inline, JSON-migratable. Keyed by page + section.
     ═══════════════════════════════════════════════════════════════════ */
  const SPEECH_LIBRARY = {

    /* ── home.html (Operator + Manager dual dashboard) ── */
    "home.html": {
      "__default__": {
        title: "首页运维仪表盘",
        summary: "双角色仪表盘：运营商查看KPI+紧急设备+工单+备件，管理者查看业务总览+策略+风险",
        speech: {
          what: "首页是整个预测性维护系统的运维仪表盘，根据登录角色分为两个视图：运营商看到的是KPI统计卡片、2×5紧急维护设备网格（Top 10高危设备）、维护工单卡片和零件采购清单；管理者看到的是业务KPI总览、Top 5日成本风险排名和当前维护策略。两种视图共享底层的100台CNC设备健康数据，但呈现的信息层级不同。",
          why: "不同角色关心的问题不同——运营商需要知道'哪台设备最紧急、要修什么、谁去修'，而管理者关心'整体健康趋势怎么样、花了多少钱、策略是否合理'。首页通过角色分流，让每个角色一打开系统就看到自己最需要的信息，而不是在一堆数据中翻找。",
          effect: "当前系统监控100台设备，平均健康分${meanScore}分（满分100）。危急(Critical)${criticalCount}台（${criticalPct}%）、退化(Degrading)${degradingCount}台（${degradingPct}%）、警告(Warning)${warningCount}台、健康(Healthy)${healthyCount}台。健康分最低的5台设备是：${top5Lowest}。这些高危设备会自动出现在运营商视图的紧急维护网格中，并生成包含故障根因、所需备件、推荐技师和预估成本的完整工单。",
          relation: "首页是整个系统的'入口和汇总'——所有AI分析、策略决策、工单执行的结果最终都在这里呈现。它串联起从数据采集→异常检测→根因诊断→维护决策→工单执行的完整闭环。点击任意设备卡片可查看SHAP归因详情，点击工单可追踪执行状态。"
        },
        keywords: ["首页", "仪表盘", "总览", "KPI", "设备", "工单", "运营商", "管理者", "角色", "健康率"]
      },
      "emergency-grid": {
        title: "紧急维护设备 Top 10",
        summary: "2×5网格展示最高危的10台设备，按优先级排序，点击查看详情",
        speech: {
          what: "这是2×5紧急维护设备网格——展示当前健康评分最低、风险最高的10台设备。每张卡片显示设备编号、健康分（带颜色条）、故障模式、建议的维护动作和停机窗口。它是从100台设备中按优先级自动筛选出的'最需要关注'列表。",
          why: "对于一线运维人员来说，100台设备不可能逐台检查。紧急维护网格自动把注意力聚焦在最危急的10台设备上——这就是'基于优先级的运维'（Priority-Based Maintenance）的核心思想：把有限的人力物力用在最关键的地方。",
          effect: "网格中的每台设备都有对应的维护工单——从故障根因、所需备件（精确到零件编号和单价）、推荐技师类型、预估工时到预期节省成本，全链路信息齐备。点击任意设备卡片可打开右侧详情面板，查看SHAP传感器归因和完整诊断报告。",
          relation: "这个网格是'从数据到决策'闭环的第一跳——它把后端五层分析管线（数据预处理→统计推断→ML密度估计→根因诊断→决策融合）的结果浓缩为10张可操作的设备卡片。评委可以看到，我们不是在展示数据，而是在交付可执行的维护方案。"
        },
        keywords: ["紧急", "高危", "Top", "网格", "设备", "优先级", "健康分", "卡片", "维护"]
      },
      "stats-cards": {
        title: "KPI统计卡片",
        summary: "健康率、高危设备数、告警精确率、待维护工单数四维关键指标",
        speech: {
          what: "这四张KPI卡片分别显示：当前健康设备占比、处于危急状态的设备数量、AI诊断准确率（基于30步回测验证）、以及待处理的工单数量。卡片数字实时更新，来自后端CSV分析数据。",
          why: "对于管理者和运维主管来说，不需要滚动页面就能快速判断两件事：设备整体健康状况（健康率和危急数）和AI系统运行质量（准确率）。四个数字，三秒钟，全局在握。",
          effect: "告警精确率在80%-91%之间波动，这是基于30步时序回测的真实数据，不是固定模拟值。点击高危设备卡片可直接跳转到紧急维护网格中对应设备的详情面板。",
          relation: "这四张卡片是整个仪表盘的'摘要层'——如果需要深入，向下滚动查看紧急设备网格和工单明细，或点击设备卡片查看SHAP传感器归因。"
        },
        keywords: ["KPI", "统计", "卡片", "健康率", "危急", "准确率", "工单", "指标", "回测"]
      },
      "work-orders": {
        title: "维护工单",
        summary: "所有待维护设备的工单卡片，含优先级、技师、备件、停机窗口、预期节省",
        speech: {
          what: "维护工单区域以卡片形式展示当前策略下所有待维护设备。每张工单卡片包含：设备编号、优先级（P1紧急/P2重要/P3常规）、维护动作、推荐技师类型、所需备件清单、推荐停机窗口（立即/夜间/周末）、期限天数、以及预期节省金额。",
          why: "传统工厂的工单系统往往是'先报修再派单'的被动模式。我们的工单是在AI诊断完成后自动生成的——从发现问题到生成可执行方案，全流程自动化。运维人员看到的每一张工单都已经是'准备好了的决策'，只需要确认和执行。",
          effect: "工单数量由当前维护策略决定（生产效率默认推荐~20张）。每张工单的预期节省金额基于成本风险矩阵计算——综合了设备故障概率、停机损失、备件成本和人工费用。策略切换后，工单会自动重新生成。",
          relation: "工单是'从诊断到执行'的桥梁——AI的诊断结果如果不转化为工单，就只是图表上的数字。这个模块连接了智能诊断和实际维护操作，是系统闭环的关键环节。"
        },
        keywords: ["工单", "维护", "卡片", "优先级", "技师", "备件", "停机", "节省", "窗口"]
      },
      "detail-panel": {
        title: "设备详情面板",
        summary: "单台设备的完整诊断报告：传感器趋势、故障根因、SHAP归因、维护建议",
        speech: {
          what: "点击紧急网格或工单卡片中的任意设备，右侧会滑出这个详情面板。它集成了一台设备的完整诊断信息：四个传感器（电压/电流/温度/转速）的趋势图、Z-Score异常值、ML密度估计、故障根因分析、推荐维护方案、预估成本和所需备件。",
          why: "运维工程师接到告警后，最需要的是'这台设备具体什么问题？严重吗？怎么修？要花多少钱？'——这个面板用一页展示全部关键信息，不需要工程师在多个系统间切换。",
          effect: "面板内的SHAP可解释性图表能将每个告警追溯到具体的传感器参数——比如'CNC_042的告警主要由温度异常贡献（贡献度67%），其次是电压波动（23%）'。这解决了AI黑箱信任问题。",
          relation: "详情面板是系统可解释性能力的集中体现。评委如果问'AI判断准不准？为什么信它？'——用SHAP归因来回答最有说服力。"
        },
        keywords: ["详情", "面板", "SHAP", "传感器", "趋势", "根因", "设备", "诊断", "滑出"]
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
      "strategy-display": {
        title: "维护策略显示",
        summary: "首页展示当前生效的维护策略（成本效率/生产效率/质量优先），切换在仪表盘执行",
        speech: {
          what: "首页的策略标签显示当前生效的维护策略。系统支持三种策略：成本效率（~15张工单，总成本最低）、生产效率（~20张工单，默认推荐）、质量优先（~30张工单，最高覆盖率）。策略名称通过sessionStorage在页面间同步，确保各页面显示一致。",
          why: "不同时期的工厂需求不同——预算紧张时选成本效率、正常运营选生产效率、客户审核或质量关键期选质量优先。首页的策略标签让管理者和运营商随时知道'当前系统按什么逻辑在分配维护资源'。",
          effect: "策略切换在仪表盘（index.html）的智能维护决策中心执行——后端会重新运行完整的工业计划生成流水线（信号构建→计划生成→备件规划→技师排班→停机调度），整个过程约3-5秒。切换后刷新首页即可看到新策略下的工单和紧急设备列表。",
          relation: "策略选择是'从数据到决策'闭环中的决策层——它定义了健康评分阈值、工单数量上限、停机窗口偏好等参数，直接影响最终给运维人员呈现哪些设备、怎么修、花多少钱。"
        },
        keywords: ["策略", "成本", "生产效率", "质量", "工单", "切换", "标签", "预算"]
      }
    },

    /* ── index.html (Dashboard 8 sections) ── */
    "index.html": {
      "__default__": {
        title: "工业智能运维仪表盘",
        summary: "8个分析模块：全局概览→运行日志→数据探索→基线划定→预测模型→效果验证→决策中心→健康升级",
        speech: {
          what: "这是完整的工业智能运维仪表盘，包含8个分析模块，覆盖从运行监控到模型验证再到维护决策的全维度分析。每个模块按三角色（运营商/管理者/开发者）分工展示，形成'感知→分析→验证→决策→执行'的完整闭环。",
          why: "单一视角的设备监控不够——运维管理需要从多个层次审视：运行状态（运营商）、业务数据（管理者）、算法模型（开发者）。8个模块恰好覆盖这三个角色的核心需求。",
          effect: "所有数据来自同一批CSV分析结果和工业维护计划引擎。前端展示与后端AI Copilot数据完全一致。支持导出CSV、图表交互缩放、策略实时切换、角色视图过滤。",
          relation: "仪表盘是面向全角色（运营/管理/开发）的决策中枢，与首页的设备健康矩阵（面向运维工程师）形成互补。两个页面通过导航栏无缝切换。"
        },
        keywords: ["仪表盘", "仪表", "大盘", "模块", "分析", "8个"]
      },
      "sec0": {
        title: "全局概览 · 三策略KPI对比",
        summary: "高危设备/活跃工单/月度节省/告警精确率/传感器ROI五维KPI卡片 + 三策略雷达图",
        speech: {
          what: "全局概览以五张KPI卡片和三策略雷达图为核心，展示高危设备数量、活跃工单数、预期月度节省金额、AI告警精确率和传感器升级5年ROI五个关键指标。雷达图并行展示成本效率、生产效率和质量优先三种策略在工单数、成本、覆盖率、工时四个维度的对比。",
          why: "管理者或评委一进入仪表盘，不需要滚动就能在三秒内判断：整体设备风险水平（高危数）、AI系统运行质量（精确率）、当前策略的ROI潜力（月度节省）。五张卡片和三张雷达图构成了整个仪表盘的摘要层。",
          effect: "数据来自后端工业维护计划引擎实时计算。告警精确率83.9%（基于Z-Score z>2.0的时序回测）。传感器升级5年ROI预估994%，基于Phase 1振动传感器方案。三种策略的雷达图差异清晰展示了'选成本还是选质量'的取舍关系。",
          relation: "全局概览是仪表盘的入口——每个KPI都可追溯。点击高危设备跳转sec7健康详情，活跃工单关联sec6决策中心，策略数据对应sec5方案验证。"
        },
        keywords: ["全局", "概览", "KPI", "对比", "雷达图", "策略", "高危", "节省"]
      },
      "sec1": {
        title: "运行日志 · 设备状态监控",
        summary: "100台CNC实时运行日志表：时间/设备/传感器读数/状态/故障类型筛选",
        speech: {
          what: "运行日志以数据表形式展示100台CNC设备的运行记录——每条记录包含时间戳、设备编号、四个传感器读数（电压/电流/温度/转速）、运行状态、故障类型标记和操作建议。支持按设备和故障类型筛选。",
          why: "运营商日常最基础的操作就是查看运行日志——设备现在在运转吗？哪个参数异常？最近报了什么故障？这个模块用最直接的数据表格回答这些问题，不需要任何图表解读能力。",
          effect: "数据表可滚动查看全部100台设备，筛选栏支持按设备编号和故障类型快速定位。异常行高亮显示。日志数据来自原始传感器数据集的脱敏CSV文件，确保数据真实性。",
          relation: "运行日志是系统的数据基础层——所有上层分析（统计推断、ML检测、根因诊断）都以这里的传感器数据为输入。评委可以从日志表验证数据源的真实性和规模。"
        },
        keywords: ["运行", "日志", "监控", "表格", "传感器", "状态", "筛选", "数据"]
      },
      "sec2": {
        title: "数据探索 · 传感器分布分析",
        summary: "20张传感器数据分布图库：按参数/设备多维探索，含技术路线全景概览",
        speech: {
          what: "数据探索模块以可展开图库形式展示20张传感器数据分布图——覆盖电压、电流、温度、转速四个参数在不同设备、不同时间维度的分布特征。顶部有数据探索技术路线全景概览，介绍从原始数据到特征工程的方法论。",
          why: "在开始任何建模之前，理解数据分布是工业级AI的第一步——传感器数据正态吗？有离群点吗？不同故障模式的数据能区分吗？这个模块用可视化回答这些前置问题，为后续基线划定和模型训练提供数据洞察。",
          effect: "图库支持折叠展开，20张图涵盖：4参数分布直方图/KDE、按故障类型分组的箱线图、时间序列趋势图、设备间方差对比图。通过数据探索可以发现：4参数Youden's J≤0.075——纯传感器无法有效区分故障，这是项目最核心的数据洞察。",
          relation: "数据探索是'从数据到模型'的起点——这里的分布洞察直接驱动了后续的逐设备基线划定（sec3）、多信号融合决策（sec6）和传感器升级ROI分析（sec7）。它是整个项目方法论链条的第一环。"
        },
        keywords: ["数据", "探索", "分布", "图库", "传感器", "KDE", "直方图", "箱线图"]
      },
      "sec3": {
        title: "基线划定分析 · 逐设备统计建模",
        summary: "每台设备的Z-Score基线参数表 + 7张方法论图库，论证逐设备基线的必要性",
        speech: {
          what: "基线划定分析模块通过逐设备Z-Score基线表格和7张方法论图库，展示了系统的核心设计决策：为每台设备独立建立统计基线，而不是使用全局阈值。每台设备有自己的均值μ、标准差σ和异常判定门限。",
          why: "这是项目最具技术深度的设计决策之一——设备间方差占61-73%，意味着'正常'的定义因设备而异。CNC_001的正常工作温度可能是45°C，CNC_050可能是52°C。如果使用全局阈值，CNC_001会被误报（假阳性），CNC_050会被漏报（假阴性）。逐设备基线解决了这个问题。",
          effect: "逐设备基线需要每台设备≥3个样本才能激活，不足3个样本时使用三层回退策略（同类均值→全局均值→保守阈值）。7张方法论图库包含：设备间方差分解、基线稳定性分析、置信区间演化、回退覆盖率统计等，完整论证了设计合理性。",
          relation: "基线划定是统计推断层（Phase A）的核心——它产出的逐设备异常评分直接输入到预测模型（sec4）的SHAP分析和决策中心（sec6）的多信号融合。如果基线不准，整个告警体系都是空中楼阁。"
        },
        keywords: ["基线", "Z-Score", "逐设备", "统计", "建模", "方差", "回退", "阈值"]
      },
      "sec4": {
        title: "预测性维护模型 · 算法对比与可解释性",
        summary: "6算法×4参数Youden's J对比表 + SHAP归因面板 + 23张模型图库",
        speech: {
          what: "预测性维护模型模块包含三大核心内容：①6种ML算法（XGBoost/RF/MLP/MTNN/IsolationForest/LOF）在4个传感器参数上的Youden's J对比实验表；②可展开的SHAP归因面板，展示MTNN模型如何为每台设备的异常贡献度分配传感器权重；③23张模型图库，涵盖ROC曲线、混淆矩阵、特征重要性等。",
          why: "纯ML的AUC上限约0.537、Youden's J≤0.075——这个发现来自真实数据的benchmark实验，不是假设。它证明了'为什么不能只用机器学习'，从而支撑项目的核心创新：多信号融合补偿策略。SHAP归因解决了AI黑箱信任问题——每个告警都可以追溯到具体传感器参数的贡献度。",
          effect: "6种算法在真实2999行数据上训练对比，XGBoost和RF的AUC约0.48、MTNN约0.537、IsolationForest约0.52。SHAP面板可逐设备展开，显示每个传感器对异常评分的SHAP值（正贡献/负贡献），后端通过四阶段SHAP管线（RiskDecomposer→StatLayerSHAP→MLExplainer→LocalExplainer）生成自然语言解释。",
          relation: "这个模块是项目的'科学论证层'——它为sec3的逐设备基线提供了ML视角的交叉验证，为sec6的多信号融合提供了权重依据（统计40%+ML25%+成本25%+趋势10%），为sec7的传感器升级提供了'数据天花板'的量化证据。"
        },
        keywords: ["模型", "ML", "算法", "对比", "SHAP", "可解释", "Youden", "AUC", "XGBoost"]
      },
      "sec5": {
        title: "方案有效性验证 · 三层回测体系",
        summary: "30步expanding window回测 + KPI验证面板 + 误差分析 + 策略切换验证",
        speech: {
          what: "方案有效性验证模块用三层回测体系——点级逐步混淆矩阵、事件级预警提前量和步进expanding window——验证从统计检测到最终决策的完整方案有效性。包含召回率/精确率/F1-Score的KPI验证面板，以及误差分布和策略切换影响分析。",
          why: "工业场景不能只说'我们的方法好'——需要量化的验证证据。30步expanding window模拟真实时间推进：每步用前N天数据训练、预测下一天、滚动前进。事件级验证检查告警能否在实际故障发生之前被触发（预警提前量），而不仅仅是'是否匹配标签'。这比简单的train/test split更有说服力。",
          effect: "回测结果以混淆矩阵热力图、F1-Score趋势线、预警提前量分布图呈现。策略切换验证展示了从'成本效率'切换到'质量优先'后，KPI如何变化。所有数据基于实际流水线输出，可追溯到具体设备和时间点。",
          relation: "方案验证是整个系统的'质量保证层'——它证明sec3的基线划定、sec4的ML检测和sec6的多信号融合确实有效，而非纸上谈兵。答辩时如果评委问'你们怎么证明方案有效？'——这个Tab就是答案。"
        },
        keywords: ["验证", "回测", "expanding window", "混淆矩阵", "F1", "精确率", "召回率", "预警"]
      },
      "sec6": {
        title: "智能维护决策中心 · 从诊断到执行",
        summary: "策略选择器 + 工单优先队列 + 技师调度甘特图 + 库存(s,S)策略 + 停机窗口调度",
        speech: {
          what: "智能维护决策中心是仪表盘最核心的操作模块，串联起完整'从诊断到执行'的闭环：①策略选择器可切换成本效率/生产效率/质量优先三种模式；②工单优先队列展示Top 15待维护设备及详情；③技师调度甘特图展示技能匹配和负载均衡；④(s,S)备件库存策略展示17种备件的需求和缺口；⑤停机窗口调度展示最优停机时间和生产影响评估。",
          why: "AI诊断如果不转化为可执行的维护方案，就只是图表上的数字。决策中心是整个系统价值落地的关键——把AI的分析结果变成'谁去修什么设备、用什么零件、什么时候停机、花多少钱'的具体指令。策略切换不是前端切换——它会触发后端重新运行完整的工业计划生成流水线（信号构建→计划生成→备件规划→技师排班→停机调度），约3-5秒完成。",
          effect: "生产效率策略（默认）下生成约20张工单，成本效率约15张，质量优先约30张。每张工单包含故障根因、所需备件（精确到零件编号单价）、推荐技师类型、预估工时、停机窗口和预期节省金额。技师调度支持成本感知降级（非关键设备由标准技师执行，降低15-25%人工成本）。库存管理采用(s,S)数学最优策略。停机窗口三因素加权排序（紧急度+生产影响+资源可用性）。",
          relation: "决策中心是五层分析管线的终点汇聚——上游所有分析（统计异常sec3、ML检测sec4、方案验证sec5）的结果在这里被融合为可执行的维护方案。它直接驱动首页的紧急设备网格和工单卡片。"
        },
        keywords: ["决策", "策略", "工单", "技师", "库存", "停机", "调度", "执行", "切换"]
      },
      "sec7": {
        title: "设备健康与感知升级 · 现状评估与投资决策",
        summary: "健康评分分布直方图 + 边缘设备列表 + 三阶段传感器升级ROI (振动/电流谱/红外)",
        speech: {
          what: "设备健康与感知升级模块分为两层：第一层展示100台设备的健康评分分布（0-100分）和边缘设备列表（健康分最低的设备及传感器数据）；第二层展示三阶段传感器升级ROI路线图——Phase 1振动传感器（投资$368K，5年ROI 994%）、Phase 2电流谱分析（追加$271K，ROI 1136%）、Phase 3红外热成像（追加$500K，ROI 1200%+）。",
          why: "健康评分告诉管理者'当前有多健康'，传感器升级告诉管理者'花多少钱能变得多健康'。这是面向管理层汇报的核心页面——现状不容乐观（仅少数设备健康分>60），但投资传感器升级是确定性的改善路径（ROI均为正且显著）。",
          effect: "当前${scoreUnder30}台设备健康分<30（危急），${score30to40}台在30-40之间（退化），${score40to60}台在40-60之间。健康分>60的仅${scoreAbove60}台，>80的${scoreAbove80}台。传感器方案B（振动+电流谱，总投资$639k）预计5年ROI 1136%，将Youden's J从0.075提升到约0.90——彻底打破现有传感器参数的数据天花板。",
          relation: "这个Tab是sec4（ML模型对比）的核心结论的延伸应用——既然4参数Youden's J≤0.075，那就从传感器层面解决问题。它连接'认识到数据天花板'（技术洞察）和'打破数据天花板'（投资决策），是整个项目故事线的高潮收尾。"
        },
        keywords: ["健康", "评分", "分布", "传感器", "升级", "ROI", "振动", "红外", "投资"]
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
    },

    /* ── reports.html ── */
    "reports.html": {
      "__default__": {
        title: "报告中心",
        summary: "6种报告类型自动生成：健康报告、故障分析、成本审计、RCA根因、备件需求、热漂移分析",
        speech: {
          what: "报告中心支持6种专业报告的一键生成：设备健康报告、故障分析报告、成本审计报告、根因分析RCA报告、备件需求汇总、热漂移分析报告。每份报告基于最新流水线数据实时生成，支持HTML预览和导出。",
          why: "工业运维需要文档化——维修记录、成本核算、合规审计都需要正式报告。传统方式需要人工整理数据、编写报告，耗时数小时。系统自动从分析CSV中提取数据，3-5秒生成专业报告，效率提升上百倍。",
          effect: "6种报告类型全部通过验证，基于统一报告数据模型（report_models.py 6个dataclass）和配置驱动架构（report_config.json），确保数据一致性。Apple风格UI渲染，支持打印和导出。",
          relation: "报告中心是系统'数据→文档'的输出环节。仪表盘的分析结果、工单跟踪的执行记录、AI Copilot的诊断结论，最终都可以通过报告中心输出为正式文档。"
        },
        keywords: ["报告", "报表", "导出", "文档", "打印", "健康报告", "故障分析"]
      }
    },

    /* ── knowledge-base.html ── */
    "knowledge-base.html": {
      "__default__": {
        title: "知识库管理",
        summary: "三层知识库（系统文档/运维知识/故障案例）+ BGE向量检索 + ChromaDB存储",
        speech: {
          what: "知识库管理页面展示AI Copilot背后RAG系统的三层知识库：系统文档层（项目架构和算法原理）、运维知识层（设备维护步骤和安全规范）、故障案例层（历史故障及修复记录）。支持文档上传、分块、向量化和检索。",
          why: "通用AI不了解特定项目的架构、算法和业务逻辑。RAG知识库相当于给AI配备了'项目专属记忆'——确保AI的回答基于真实系统文档而非模糊训练数据。这是AI专业性的保障。",
          effect: "使用BGE-small-zh-v1.5本地嵌入模型（~15ms检索）和DeepSeek API嵌入（~300ms）双层回退。ChromaDB向量数据库存储，支持增量更新和版本管理。",
          relation: "知识库是AI Copilot的'大脑'。所有页面中AI助手给出的专业回答，都依赖这个知识库提供准确的上下文信息。"
        },
        keywords: ["知识库", "RAG", "向量", "检索", "ChromaDB", "嵌入", "文档"]
      }
    },

    /* ── workflows.html ── */
    "workflows.html": {
      "__default__": {
        title: "工作流管理",
        summary: "DAG流水线可视化：数据预处理→统计推断→ML推断→诊断→决策",
        speech: {
          what: "工作流管理页面展示系统的DAG（有向无环图）流水线引擎。五层分析管线（数据预处理→统计推断→ML推断→诊断→决策）的每个节点状态、耗时、输入输出关系都可以在这里监控和管理。",
          why: "复杂的多步骤分析流程需要统一调度——哪些步骤可以并行执行、哪些存在依赖关系、某个步骤失败后如何处理。DAG编排引擎通过配置驱动的方式解决了这些问题，确保分析流程的高效和可靠。",
          effect: "完整流水线耗时约9-15秒（取决于是否启用ML和诊断）。支持断点续跑、按需降级、输出版本管理。ThreadPool并行执行无依赖节点，最大化利用计算资源。",
          relation: "工作流是系统'数据流'的骨架。仪表盘展示的所有分析结果，都是通过这个流水线从原始传感器数据一步步加工而来的。"
        },
        keywords: ["工作流", "流水线", "DAG", "编排", "节点", "并行"]
      }
    },

    /* ── inventory.html ── */
    "inventory.html": {
      "__default__": {
        title: "库存管理",
        summary: "17种备件(s,S)最优库存策略 + 采购建议 + 供应商管理",
        speech: {
          what: "库存管理页面展示17种备件的(s,S)库存策略——当库存低于s（补货点）时自动建议补货到S（目标库存）。包含当前库存量、需求量、缺口量、建议采购数量、供应商信息和预估到货日期。",
          why: "备件库存是运维成本控制的关键环节——库存太多占用资金，库存太少维修时缺件导致设备停等。(s,S)策略在库存持有成本和缺货风险之间找到数学最优解。",
          effect: "实时对比当前库存与维护工单需求，自动计算每种备件的缺口。支持一键生成采购申请单，包含供应商、数量、金额和预计到货日期。",
          relation: "库存数据与工单计划直接关联——策略切换导致工单数变化时，备件需求自动重新计算。属于'决策→执行'闭环中的物资保障环节。"
        },
        keywords: ["库存", "备件", "采购", "s,S", "策略", "供应商", "零件"]
      }
    },

    /* ── work-order-tracking.html ── */
    "work-order-tracking.html": {
      "__default__": {
        title: "工单跟踪",
        summary: "工单6状态机：待处理→已分配→进行中→待验收→已完成→已关闭",
        speech: {
          what: "工单跟踪页面管理所有维护工单的完整生命周期——从创建、分配技师、开始维修、等待验收、确认完成到最终关闭，六个状态的流转都有实时跟踪和审计日志。",
          why: "维护执行需要闭环管理——工单发出去了，有没有人处理？处理到哪一步了？卡在哪个环节？这些问题直接影响设备可用率。工单状态机确保每张工单都有明确的责任人和可追踪的进度。",
          effect: "支持工单筛选（按状态/设备/技师/优先级）、批量操作、状态流转审计。与技师调度、备件库存、停机窗口三者联动——一个环节的变更会触发其他环节的更新。",
          relation: "工单跟踪是系统'决策→执行'闭环的最后一公里。策略分析生成了工单，但只有真正执行并跟踪完成，预测性维护的价值才能落地。"
        },
        keywords: ["工单", "跟踪", "状态机", "维修", "执行", "审计"]
      }
    },

    /* ── technicians.html ── */
    "technicians.html": {
      "__default__": {
        title: "技师管理",
        summary: "技师技能档案 + 负载均衡 + 成本感知降级 + 排班甘特图",
        speech: {
          what: "技师管理页面维护所有运维技师的技能档案——包括技能类型（电气/热力/机械）、等级（专家/高级/标准/初级）、当前负载、历史绩效。支持自动排班和技能匹配。",
          why: "技师是企业最宝贵的运维资源。派错人（让电气专家去修热力故障）既浪费技能又可能修不好。系统根据故障模式自动匹配技师技能，同时考虑负载均衡和成本优化。",
          effect: "成本感知降级机制可降低人工成本15%-25%——非关键设备由标准技师执行，仅在ALARM级别且特定故障模式时才分配专家。甘特图直观展示排班时间线和负载分布。",
          relation: "技师管理与工单分配、备件库存、停机窗口四者联动。策略切换或工单变化时，技师排班自动重新计算。"
        },
        keywords: ["技师", "排班", "技能", "负载", "甘特图", "人力资源"]
      }
    },

    /* ── sphere-demo.html ── */
    "sphere-demo.html": {
      "__default__": {
        title: "鹰眼·3D设备球体",
        summary: "Three.js手势交互3D球体——100台设备空间化展示 + 手势识别操控",
        speech: {
          what: "鹰眼3D球体是一个基于Three.js的交互式工业数字孪生演示。100台CNC设备以节点形式分布在3D球体表面，支持手势识别（握拳旋转、张手缩放、双指平移）和语音控制。实时映射设备健康状态到颜色和大小。",
          why: "传统的2D矩阵虽然实用，但在演示场景中缺乏视觉冲击力。3D球体将设备监控升维为空间化交互体验——评委可以直观感受到'站在球体内部俯瞰全局'的沉浸感，是项目技术展示的亮点模块。",
          effect: "基于MediaPipe手势识别（21关键点），支持5种手势。Three.js渲染管线优化至60fps。手势识别延迟<50ms，交互流畅自然。",
          relation: "3D球体是项目的'演示层'——底层仍然是同一套健康评分和分析数据，但用更震撼的视觉形式呈现。适合展厅大屏、路演演示、投资人展示等场景。"
        },
        keywords: ["3D", "球体", "手势", "Three.js", "数字孪生", "交互", "演示"]
      }
    }
  };

  /* ═══════════════════════════════════════════════════════════════════
     Context Extractor
     ═══════════════════════════════════════════════════════════════════ */
  /* ── URL route → page filename mapping ── */
  const PAGE_MAP = {
    '': 'home.html',
    'home': 'home.html',
    'dashboard': 'index.html',
    'chat': 'chat.html',
    'device-grid': 'device-grid.html',
    'technical-overview': 'technical-overview.html',
    'reports': 'reports.html',
    'knowledge-base': 'knowledge-base.html',
    'workflows': 'workflows.html',
    'inventory': 'inventory.html',
    'work-order-tracking': 'work-order-tracking.html',
    'technicians': 'technicians.html',
    'sphere-demo': 'sphere-demo.html',
  };

  function extractContext() {
    const path = window.location.pathname;
    const route = path.split('/').pop() || '';
    const page = PAGE_MAP[route] || 'home.html';
    const ctx = { page, route, sections: [], viewportHeading: null, hashTarget: null };

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
      this._healthData = null;       // cached health summary from /api/health-summary
      this._healthDataPromise = null; // inflight fetch promise
      this._dragging = false;
      this._dragStartX = 0;
      this._dragStartY = 0;
      this._dragOrigLeft = 0;
      this._dragOrigTop = 0;
      this._buildDOM();
      this._restorePosition();
      this._bindEvents();
      this._fetchHealthData();       // pre-fetch real health data on init
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
        if (left) {
          const px = parseFloat(left);
          if (!isNaN(px)) {
            const clamped = Math.max(8, Math.min(window.innerWidth - 64, px));
            this.orbContainer.style.left = clamped + 'px';
          }
        }
        if (top) {
          const py = parseFloat(top);
          if (!isNaN(py)) {
            const clamped = Math.max(8, Math.min(window.innerHeight - 64, py));
            this.orbContainer.style.top = clamped + 'px';
          }
        }
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
        await this._renderSpeech(this.currentSpeech);
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
        'device-grid.html': '设备矩阵',
        'reports.html': '报告中心',
        'knowledge-base.html': '知识库',
        'workflows.html': '工作流',
        'inventory.html': '库存管理',
        'work-order-tracking.html': '工单跟踪',
        'technicians.html': '技师管理',
        'sphere-demo.html': '鹰眼球体'
      };
      return map[page] || page || '当前页面';
    }

    /* ── Fetch real health data from backend ── */
    async _fetchHealthData() {
      if (this._healthDataPromise) return this._healthDataPromise;
      this._healthDataPromise = fetch('/api/health-summary')
        .then(r => r.json())
        .then(data => {
          if (data && !data.error) {
            this._healthData = data;
          }
          return data;
        })
        .catch(e => {
          console.warn('[Assistant] Failed to fetch health summary, using fallback', e);
          return null;
        });
      return this._healthDataPromise;
    }

    /* ── Apply health data template substitution ── */
    _applyHealthData(text) {
      if (!this._healthData || !text) return text;
      const d = this._healthData;
      let result = text;
      // Health distribution
      result = result.replace(/\$\{meanScore\}/g, d.mean_score);
      result = result.replace(/\$\{criticalCount\}/g, d.critical_count);
      result = result.replace(/\$\{criticalPct\}/g, d.critical_pct);
      result = result.replace(/\$\{degradingCount\}/g, d.degrading_count);
      result = result.replace(/\$\{degradingPct\}/g, d.degrading_pct);
      result = result.replace(/\$\{warningCount\}/g, d.warning_count);
      result = result.replace(/\$\{healthyCount\}/g, d.healthy_count);
      // Score bins
      if (d.score_bins) {
        result = result.replace(/\$\{scoreUnder30\}/g, d.score_bins['<30']);
        result = result.replace(/\$\{score30to40\}/g, d.score_bins['30-40']);
        result = result.replace(/\$\{score40to60\}/g, d.score_bins['40-60']);
        result = result.replace(/\$\{score60to80\}/g, d.score_bins['60-80']);
        result = result.replace(/\$\{score80to100\}/g, d.score_bins['80-100']);
        result = result.replace(/\$\{scoreAbove60\}/g, (d.score_bins['60-80'] || 0) + (d.score_bins['80-100'] || 0));
        result = result.replace(/\$\{scoreAbove80\}/g, d.score_bins['80-100'] || 0);
      }
      // Top 5 lowest devices
      if (d.top5_lowest) {
        const top5 = d.top5_lowest.map(dev => dev.id + '(' + dev.score + ')').join('、');
        result = result.replace(/\$\{top5Lowest\}/g, top5);
      }
      return result;
    }

    /* ── Render matched speech ── */
    async _renderSpeech(speech) {
      // Ensure health data is loaded before rendering templates
      if (!this._healthData) {
        await this._fetchHealthData();
      }
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
          const resolved = this._applyHealthData(text);
          html += `<div class="assistant-speech-section">
            <div class="assistant-speech-label">${sec.label}</div>
            <div class="assistant-speech-text">${resolved}</div>
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

      cancel.addEventListener('click', async () => {
        if (this.currentSpeech) await this._renderSpeech(this.currentSpeech);
        else this._renderEmpty();
      });

      submit.addEventListener('click', async () => {
        const q = input.value.trim();
        if (!q) return;
        this.currentSpeech = matchSpeech(this.currentContext, q);
        if (this.currentSpeech && this.currentSpeech.matchType !== 'default') {
          await this._renderSpeech(this.currentSpeech);
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
        await this._renderSpeech(this.currentSpeech);
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
