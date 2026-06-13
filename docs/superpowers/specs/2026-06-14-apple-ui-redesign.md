# Apple 风格 UI/UX 重构设计文档

> 苗圃杯半决赛 v2.1 | 2026-06-14
> 
> 目标：在不改动业务逻辑、API 逻辑、页面功能的前提下，将全部前端页面重构为 Apple/macOS 现代简洁风格。

---

## 一、设计方向

- **整体风格**：iOS 26 极致透明渐变玻璃（glassmorphism 2.0）—— 高透明度 + 强模糊 + 环境光晕 + 内高光
- **板块原则**：页面中每个独立内容板块（KPI卡片、图表容器、表格、工单卡、过滤栏等）都做成独立的透明磨砂玻璃卡片，像冰块漂浮在背景上，透过玻璃可见下层光晕
- **浅色模式**：浅灰渐变底 + 多层环境光晕 + 极高透明度(28-40%)白色玻璃 + 强模糊(30-50px)
- **深色模式**：纯黑底 + 柔和光晕 + 半透明(30-35%)深灰玻璃 + 强模糊(40-50px)
- **配色策略**：保留工业语义色（青=健康/信息、琥珀=警告、红=危险、紫=SHAP），降低饱和度以符合克制风格

---

## 二、Design Tokens（全局 CSS 变量）

> **注意**：沿用现有项目 CSS 约定——`:root` 为深色默认，`[data-theme="light"]` 为浅色。

### 2.1 深色模式 `:root`（默认）

```css
:root {
  /* 背景层级 */
  --bg-root: #000000;
  --bg-surface: #1c1c1e;
  --bg-card: rgba(44, 44, 46, 0.7);
  --bg-card-alt: rgba(58, 58, 60, 0.5);
  --bg-input: rgba(44, 44, 46, 0.6);

  /* 文字层级 */
  --text-primary: #f5f5f7;
  --text-secondary: #98989d;
  --text-muted: #636366;

  /* 边框 */
  --border: rgba(255, 255, 255, 0.08);
  --border-light: rgba(255, 255, 255, 0.05);
  --border-accent: rgba(255, 255, 255, 0.12);

  /* 语义色（深色模式适度提亮） */
  --accent-cyan: #66d9c8;      /* 原 #00c9a0 */
  --accent-green: #30d158;     /* 原 #3fb950 */
  --accent-blue: #6db5f9;      /* 原 #4d94ff */
  --accent-amber: #ffb340;     /* 原 #f0a030 */
  --accent-red: #ff453a;       /* 原 #f04444 */
  --accent-purple: #bf5af2;    /* 原 #a371f7 */
  --accent-pink: #ff6482;      /* 原 #db61a2 */

  /* 阴影（深色多层） */
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.5);
  --shadow-xl: 0 12px 48px rgba(0, 0, 0, 0.6);

  /* 圆角（iOS 26 大圆角） */
  --radius-sm: 10px;
  --radius: 14px;
  --radius-md: 18px;
  --radius-lg: 22px;
  --radius-xl: 28px;

  /* 毛玻璃（深色 — 高透明 + 强模糊） */
  --glass-bg-card: rgba(44, 44, 46, 0.35);
  --glass-bg-header: rgba(28, 28, 30, 0.4);
  --glass-bg-modal: rgba(44, 44, 46, 0.55);
  --glass-bg-sidebar: rgba(28, 28, 30, 0.5);
  --glass-blur: blur(45px) saturate(220%);
  --glass-blur-light: blur(30px) saturate(200%);
  --glass-blur-strong: blur(55px) saturate(240%);

  /* 玻璃边框 */
  --glass-border: 0.5px solid rgba(255, 255, 255, 0.10);
  --glass-border-light: 0.5px solid rgba(255, 255, 255, 0.14);

  /* 内高光（iOS 26 标志性效果） */
  --glass-highlight: inset 0 0.5px 0 rgba(255, 255, 255, 0.08);
  --glass-highlight-strong: inset 0 0.5px 0 rgba(255, 255, 255, 0.14);

  /* 字体 */
  --font-sans: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;

  /* 间距体系 */
  --space-xs: 6px;
  --space-sm: 10px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  /* 过渡 */
  --transition: 0.25s cubic-bezier(0.25, 0.1, 0.25, 1);
  --transition-spring: 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

### 2.2 浅色模式 `[data-theme="light"]`

```css
[data-theme="light"] {
  --bg-root: #f2f2f7;
  --bg-surface: #fafafa;
  --bg-card: rgba(255, 255, 255, 0.72);
  --bg-card-alt: rgba(245, 245, 247, 0.6);
  --bg-input: rgba(255, 255, 255, 0.65);

  --text-primary: #1d1d1f;
  --text-secondary: #6e6e73;
  --text-muted: #aeaeb2;

  --border: rgba(0, 0, 0, 0.06);
  --border-light: rgba(0, 0, 0, 0.04);
  --border-accent: rgba(0, 0, 0, 0.10);

  /* 语义色（浅色模式降低饱和度） */
  --accent-cyan: #5ac8b8;
  --accent-green: #4cd964;
  --accent-blue: #64b5f6;
  --accent-amber: #f0a840;
  --accent-red: #e06060;
  --accent-purple: #b388eb;
  --accent-pink: #e080a0;

  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 8px 30px rgba(0, 0, 0, 0.10);
  --shadow-xl: 0 12px 40px rgba(0, 0, 0, 0.14);

  --glass-bg-card: rgba(255, 255, 255, 0.38);
  --glass-bg-header: rgba(250, 250, 250, 0.45);
  --glass-bg-modal: rgba(255, 255, 255, 0.55);
  --glass-bg-sidebar: rgba(250, 250, 250, 0.5);
  --glass-blur: blur(40px) saturate(220%);
  --glass-blur-light: blur(30px) saturate(200%);
  --glass-blur-strong: blur(50px) saturate(240%);

  /* 玻璃边框 */
  --glass-border: 0.5px solid rgba(255, 255, 255, 0.5);
  --glass-border-light: 0.5px solid rgba(255, 255, 255, 0.65);

  /* 内高光 */
  --glass-highlight: inset 0 0.5px 0 rgba(255, 255, 255, 0.6);
  --glass-highlight-strong: inset 0 0.5px 0 rgba(255, 255, 255, 0.85);
}
```

### 2.3 板块级玻璃化原则（核心）

**每个独立的业务内容板块都做成独立的 iOS 26 透明磨砂玻璃卡片**。这包括但不限于：

- KPI 统计卡片、图表容器、数据表格
- 工单卡片、设备网格卡片、策略选择器
- 过滤/搜索栏、Tab 切换栏、分页器
- 侧滑面板、弹窗、确认框
- 每个 sec 内的每个子区块

**统一玻璃卡片类** `.glass-card`：

```css
.glass-card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm), var(--glass-highlight);
  transition: box-shadow var(--transition), transform var(--transition);
}
.glass-card:hover {
  box-shadow: var(--shadow-md), var(--glass-highlight);
  transform: translateY(-1px);
}
/* 嵌套玻璃卡片增加层次感 */
.glass-card .glass-card {
  background: rgba(255, 255, 255, 0.25); /* 浅色嵌套更透明 */
  backdrop-filter: var(--glass-blur-light);
  border-radius: var(--radius-md);
}
```

**页面背景要求**：必须有渐变光晕，否则透明玻璃看不出效果。

```css
body {
  background: var(--bg-root);
}
body::before {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  /* 多层径向渐变光晕 — 让透明玻璃展现层次 */
  background:
    radial-gradient(ellipse 80% 60% at 30% 20%, rgba(90,200,184,0.06) 0%, transparent 60%),
    radial-gradient(ellipse 60% 50% at 70% 60%, rgba(100,181,246,0.05) 0%, transparent 60%),
    radial-gradient(ellipse 50% 40% at 50% 80%, rgba(179,136,235,0.04) 0%, transparent 60%);
}
[data-theme="light"] body::before {
  background:
    radial-gradient(ellipse 80% 60% at 30% 20%, rgba(90,200,184,0.08) 0%, transparent 60%),
    radial-gradient(ellipse 60% 50% at 70% 60%, rgba(100,181,246,0.06) 0%, transparent 60%),
    radial-gradient(ellipse 50% 40% at 50% 80%, rgba(179,136,235,0.05) 0%, transparent 60%);
}
```

### 2.4 移除的旧设计元素

- ~~`body::before` 大气径向渐变背景~~ → 改为多层柔光光晕
- ~~`body::after` 扫描线叠加~~ → 移除
- ~~`--radius: 3px` 工业锐角~~ → 统一 18-28px 大圆角
- ~~3D Keycap 效果~~ → 毛玻璃卡片替代
- ~~粗实色 `--border: #1c2230`~~ → 0.5px 半透明边框 + 内高光

---

## 三、组件库

### 3.1 卡片 (Card)

所有卡片统一使用毛玻璃效果：

```css
.card {
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition), transform var(--transition);
}
.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
```

**KPI 统计卡片**：大数字(28px/700) + 辅助标签(11px/muted)
**工单卡片**：左侧 3px 语义色竖线 + 右上角优先级徽章
**设备网格卡片**：用毛玻璃 + 健康色底替代 3D keycap 效果

### 3.2 按钮 (Button)

三级按钮体系：

| 级别 | 样式 | 用途 |
|------|------|------|
| Primary | 实色填充 `var(--accent-cyan)` | 主要操作 |
| Secondary | 8% 青底 + 青边框 | 次要操作 |
| Ghost | 透明 + 细边框 | 取消/回退 |

```css
.btn-primary {
  background: var(--accent-cyan); border: none; color: #fff;
  padding: 10px 20px; border-radius: var(--radius); font-weight: 500;
  transition: all var(--transition);
}
.btn-primary:hover { opacity: 0.88; transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.btn-primary:active { transform: scale(0.98); }
```

交互微动效：hover 上浮 1px + 微增阴影，click 缩放 0.98。

### 3.3 输入框 (Input)

```css
.input {
  background: var(--bg-input);
  backdrop-filter: var(--glass-blur-light);
  border: 0.5px solid var(--border-accent);
  border-radius: var(--radius);
  padding: 10px 14px;
  font-size: 13px; color: var(--text-primary);
  transition: border-color var(--transition), box-shadow var(--transition);
}
.input:focus {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 3px rgba(90, 200, 184, 0.12);
  outline: none;
}
```

Focus 态：青色外发光环 + 边框变青。

### 3.4 标签/徽章 (Tag/Badge)

```css
.tag { padding: 4px 10px; border-radius: var(--radius-sm); font-size: 11px; font-weight: 500; }
.tag-healthy { background: rgba(76, 217, 100, 0.08); color: var(--accent-green); }
.tag-degrading { background: rgba(240, 168, 64, 0.08); color: var(--accent-amber); }
.tag-critical { background: rgba(224, 96, 96, 0.08); color: var(--accent-red); }
```

### 3.5 进度条 (Progress Bar)

```css
.progress-bar {
  height: 6px; border-radius: 3px; background: var(--border-light); overflow: hidden;
}
.progress-fill { height: 100%; border-radius: 3px; transition: width 0.6s var(--transition); }
```

### 3.6 表格 (Table)

```css
.table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  font-size: 12px;
}
.table th {
  text-align: left; padding: 10px 14px; font-weight: 600;
  color: var(--text-secondary); border-bottom: 0.5px solid var(--border);
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em;
}
.table td {
  padding: 10px 14px; border-bottom: 0.5px solid var(--border-light);
  color: var(--text-primary);
}
.table tr:hover td { background: var(--bg-card-alt); }
```

### 3.7 弹窗 (Modal)

```css
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45); /* 深色默认 */
  backdrop-filter: blur(4px);
  z-index: 2000; opacity: 0; pointer-events: none;
  transition: opacity 0.25s ease;
}
[data-theme="light"] .modal-overlay { background: rgba(0, 0, 0, 0.18); }
.modal-overlay.open { opacity: 1; pointer-events: auto; }

.modal {
  position: fixed; top: 50%; left: 50%;
  transform: translate(-50%, -50%) scale(0.95);
  background: var(--glass-bg-modal);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 0.5px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  z-index: 2001; opacity: 0; pointer-events: none;
  transition: opacity 0.25s ease, transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.modal.open { opacity: 1; pointer-events: auto; transform: translate(-50%, -50%) scale(1); }
```

---

## 四、布局系统

### 4.1 侧边栏导航

- 宽度：200px 固定
- 位置：fixed left:0 top:0 bottom:0
- 背景：`rgba(250,250,250,0.85)` 浅色 / `rgba(28,28,30,0.85)` 深色
- 毛玻璃：`blur(24px) saturate(180%)`
- 结构：
  - Logo 区（青色脉冲点 + 项目名）
  - 6个导航链接（纵向排列，间距 1px）
  - 底部操作区（角色切换 / 主题切换 / 降级指示器 / 版本徽章）
- 激活态：左侧 3px 青色竖线 + 6% 青底
- 响应式 ≤768px：收窄为顶部横条

### 4.2 页面头部

- 毛玻璃卡片形式
- 标题 + 视图徽章（青/琥珀色胶囊标签）
- 角色对应语义色

### 4.3 内容区域

- body padding-left: 200px（匹配侧边栏）
- 主内容 max-width: 1400px，水平居中
- 网格间隙：16px（桌面）/ 12px（平板）/ 8px（手机）

### 4.4 详情侧滑面板

- 宽度 420px，从右侧滑入
- 毛玻璃背景 + overlay 遮罩
- 关闭方式：Esc / 点击遮罩 / 点击 ×

---

## 五、字体层级

| 层级 | 字号 | 字重 | 颜色 | 用途 |
|------|------|------|------|------|
| Hero | 28px | 700 (-0.5px letter-spacing) | text-primary | KPI 主数值 |
| H1 | 20px | 700 | text-primary | 页面标题 |
| H2 | 16px | 600 | text-primary | 区块标题 |
| H3 | 13px | 600 | text-secondary | 卡片标题 |
| Body | 13px | 400 | text-primary | 正文 |
| Caption | 11px | 500 | text-secondary | 辅助说明 |
| Label | 10px | 600 (uppercase, +0.03em) | text-muted | 标签/UPPERCASE |

---

## 六、交互与动效

### 6.1 过渡缓动

- 所有交互使用 `cubic-bezier(0.25, 0.1, 0.25, 1)`（Safari 默认缓动）
- 弹窗/面板打开使用 `cubic-bezier(0.34, 1.56, 0.64, 1)`（弹性 overshoot）
- 持续时间：微交互 0.15-0.2s，面板 0.25-0.3s

### 6.2 hover 微交互

- 卡片：上浮 1px + 阴影加深
- 按钮：opacity 0.88 + 上浮 1px
- 导航链接：文字变亮 + 微背景
- 表格行：交替色背景

### 6.3 click 反馈

- 按钮：scale(0.98) 按压感
- 卡片选择：边框亮起 + 微缩

### 6.4 入场动画

- 卡片 stagger：50ms 间隔依次淡入
- 页面切换：opacity 0 → 1，0.25s
- 弹窗：scale(0.95) → scale(1) + opacity，弹性缓动

### 6.5 脉冲指示器

- Logo 点：2.5s ease-in-out 呼吸
- 活跃工单设备：2s 光晕脉冲（替代之前的红色脉冲）
- 降级状态：颜色变化过渡

---

## 七、响应式策略

| 断点 | 布局变化 |
|------|---------|
| ≥1200px | 完整桌面布局：侧边栏 + 多列网格 |
| 1024-1199px | 侧边栏保持，网格减为 3 列 |
| 768-1023px | 侧边栏缩窄为 64px 图标模式 |
| 520-767px | 侧边栏转为顶部横条，网格 2 列 |
| <520px | 顶栏隐藏 logo 文字，网格 1 列 |

---

## 八、文件改动范围

### 核心改动（影响所有页面）

| 文件 | 改动内容 |
|------|---------|
| `web-dashboard/shared/navbar.js` | 重写 CSS 块（design tokens + 侧边栏样式）和 HTML 结构 |
| `web-dashboard/shared/sidebar.css` | 更新为 Apple 风格侧边栏变量 |
| `web-dashboard/shared/theme-init.js` | 适配新主题变量（可能无需改动） |

### 页面级改动（按优先级）

| 优先级 | 文件 | 改动范围 |
|--------|------|---------|
| P0 | `home.html` | 全局 CSS 变量 + 卡片/按钮/网格/面板全面重构 |
| P0 | `index.html` | 全局 CSS 变量 + 8个Tab区全部卡片/图表容器/表格 |
| P0 | `role-gate.html` | 角色卡片重构（毛玻璃 + 大圆角） |
| P1 | `chat.html` | 对话气泡/输入区/侧边栏重构 |
| P1 | `device-grid.html` | 设备网格/详情面板/弹窗重构 |
| P1 | `technical-overview.html` | 板块卡片/架构图容器重构 |
| P2 | `knowledge-base.html` | 卡片/表格/输入区重构 |
| P2 | `inventory.html` | 表格/卡片/按钮重构 |
| P2 | `reports.html` | 列表/卡片/筛选栏重构 |
| P2 | `technicians.html` | 卡片/表格重构 |
| P2 | `work-order-tracking.html` | 面板/按钮/状态指示器重构 |
| P2 | `workflows.html` | 卡片/表格重构 |

### 不改动的文件

- `web-dashboard/shared/role-check.js` — 纯逻辑，无样式
- `web-dashboard/shared/role-switcher.js` — 纯逻辑
- `web-dashboard/shared/device-grid-component.js` — 样式由所在页面控制
- `web-dashboard/shared/demo-mode.js` — 纯逻辑
- 所有 `gateway/*.py` — 后端无改动
- 所有 `data/*` — 数据文件无改动

---

## 九、实施原则

1. **不改业务逻辑** — 只改 CSS 和 HTML 结构，不碰 JS 函数签名和 API 调用
2. **用 removeAttribute/setAttribute 替代硬编码** — 主题切换不变更逻辑
3. **渐进式改造** — 先 P0 页面建立设计基准，再推广到 P1/P2
4. **保持角色分版机制** — `data-role` + CSS `:not()` 过滤完整保留
5. **每步测试** — 每改完一个页面立即启动服务器验证
6. **复用 Design Tokens** — 所有页面共用同一套 CSS 变量
