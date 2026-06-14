# 角色选择页面路演级优化 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将角色选择页面从基础 iOS 26 玻璃风格升级为路演级工业科技感界面 — 沉浸式背景、立体卡片、价值文案、流光悬浮动效

**Architecture:** 纯 CSS/HTML 改动，零 JS 逻辑变更。`design-tokens.css` 新增角色主题色变量，`role-gate.html` 重写 `<style>` 块和 `<body>` 内容。所有动画使用 CSS `@keyframes`，无需 JS。

**Tech Stack:** Vanilla CSS (custom properties + gradients + animations), HTML — no new dependencies.

**Files affected:** 2 files (`shared/design-tokens.css`, `role-gate.html`)

---

## File Structure

| 文件 | 职责 |
|------|------|
| `shared/design-tokens.css` | 新增 3 个角色主题色变量（含发光变体） |
| `role-gate.html` | 全部视觉改动：背景渐变+粒子+数据流、标题渐变发光、卡片立体化+主题色、价值文案、悬浮动效、底部提示 |

---

### Task 1: design-tokens.css — 新增角色主题色变量

**Files:**
- Modify: `web-dashboard/shared/design-tokens.css`

- [ ] **Step 1: 在 :root 块末尾（} 前）插入角色主题色变量**

在 `:root { ... }` 块的 `--transition-spring` 行之后、`}` 之前插入：

```css
  /* Role theme colors — roadshow */
  --role-operator: #0EA5E9;
  --role-operator-glow: rgba(14, 165, 233, 0.35);
  --role-manager: #F59E0B;
  --role-manager-glow: rgba(245, 158, 11, 0.35);
  --role-developer: #8B5CF6;
  --role-developer-glow: rgba(139, 92, 246, 0.35);
```

- [ ] **Step 2: 在 [data-theme="light"] 块末尾插入浅色模式对应变量**

在 `[data-theme="light"] { ... }` 块的 `--transition-spring` 行之后、`}` 之前插入：

```css
  --role-operator: #0284c7;
  --role-operator-glow: rgba(2, 132, 199, 0.25);
  --role-manager: #d97706;
  --role-manager-glow: rgba(217, 119, 6, 0.25);
  --role-developer: #7c3aed;
  --role-developer-glow: rgba(124, 58, 237, 0.25);
```

- [ ] **Step 3: 验证 CSS 语法**

Run: `node -e "const fs=require('fs');const c=fs.readFileSync('web-dashboard/shared/design-tokens.css','utf8');require('postcss')||true;console.log('OK: '+c.length+' bytes')"` (simplified — just check file is valid CSS by starting server later)

- [ ] **Step 4: Commit**

```bash
git add web-dashboard/shared/design-tokens.css
git commit -m "feat: design-tokens.css新增角色主题色变量 — operator蓝/manager橙/developer紫"
```

---

### Task 2: role-gate.html — 背景重构（工业科技渐变 + 数据流线条 + 浮动粒子）

**Files:**
- Modify: `web-dashboard/role-gate.html`

- [ ] **Step 1: 替换 body 样式为工业科技渐变背景**

将现有 `body { ... }` 块替换为：

```css
body {
  margin: 0; padding: 0;
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 40px 20px;
  font-family: var(--font-sans);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
  /* Industrial deep navy gradient */
  background:
    radial-gradient(ellipse 120% 80% at 20% 10%, rgba(14, 165, 233, 0.12) 0%, transparent 55%),
    radial-gradient(ellipse 100% 70% at 80% 50%, rgba(139, 92, 246, 0.08) 0%, transparent 55%),
    radial-gradient(ellipse 90% 60% at 50% 90%, rgba(245, 158, 11, 0.06) 0%, transparent 55%),
    linear-gradient(180deg, #0F172A 0%, #0A1628 40%, #0F172A 100%);
  position: relative;
}
```

- [ ] **Step 2: 添加数据流网格线条（body::after 伪元素）**

在 `body { ... }` 后添加：

```css
/* Data grid lines — subtle tech texture */
body::after {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0; opacity: 0.04;
  background-image:
    linear-gradient(rgba(14, 165, 233, 0.3) 1px, transparent 1px),
    linear-gradient(90deg, rgba(14, 165, 233, 0.3) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 70% 60% at 50% 50%, black 0%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse 70% 60% at 50% 50%, black 0%, transparent 70%);
}
```

- [ ] **Step 3: 添加浮动粒子容器（.particles 层）**

在 `body::after` 块后添加：

```css
/* Floating particles */
.particles {
  position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden;
}
.particle {
  position: absolute;
  width: 2px; height: 2px;
  background: var(--accent-cyan);
  border-radius: 50%;
  opacity: 0;
  animation: floatUp linear infinite;
}
.particle:nth-child(1)  { left: 10%; animation-duration: 8s; animation-delay: 0s; }
.particle:nth-child(2)  { left: 25%; animation-duration: 12s; animation-delay: 1s; width: 1px; height: 1px; }
.particle:nth-child(3)  { left: 40%; animation-duration: 10s; animation-delay: 3s; }
.particle:nth-child(4)  { left: 55%; animation-duration: 14s; animation-delay: 0.5s; width: 1.5px; height: 1.5px; }
.particle:nth-child(5)  { left: 70%; animation-duration: 9s; animation-delay: 2s; }
.particle:nth-child(6)  { left: 85%; animation-duration: 11s; animation-delay: 4s; width: 1px; height: 1px; }
.particle:nth-child(7)  { left: 15%; animation-duration: 13s; animation-delay: 5s; }
.particle:nth-child(8)  { left: 60%; animation-duration: 7s; animation-delay: 1.5s; }
.particle:nth-child(9)  { left: 35%; animation-duration: 15s; animation-delay: 3.5s; width: 2.5px; height: 2.5px; }
.particle:nth-child(10) { left: 75%; animation-duration: 10s; animation-delay: 6s; }

@keyframes floatUp {
  0%   { transform: translateY(100vh) scale(0); opacity: 0; }
  10%  { opacity: 0.8; }
  90%  { opacity: 0.3; }
  100% { transform: translateY(-10vh) scale(1); opacity: 0; }
}
```

- [ ] **Step 4: 在 HTML <body> 中添加粒子元素**

在 `<body>` 标签后、`.role-gate-container` 前插入：

```html
<div class="particles">
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
  <div class="particle"></div>
</div>
```

- [ ] **Step 5: 更新 design-tokens.css 的 body::before 环境光晕以匹配新背景**

不修改 design-tokens.css 中的 `body::before`，因为 role-gate.html 中新的 body `background` 会覆盖 design-tokens.css 的 `background: var(--bg-root)`。role-gate 自身的背景渐变包含了光晕效果。

但需要处理 design-tokens.css 的 body::before 伪元素 — 它会叠加在 role-gate 自定义背景之上。在 role-gate.html 的 `<style>` 中添加覆盖：

```css
/* Override design-tokens body::before — use our own ambient orbs */
body::before {
  background:
    radial-gradient(ellipse 100% 70% at 30% 15%, rgba(14, 165, 233, 0.07) 0%, transparent 60%),
    radial-gradient(ellipse 80% 60% at 70% 50%, rgba(139, 92, 246, 0.05) 0%, transparent 60%),
    radial-gradient(ellipse 90% 50% at 50% 85%, rgba(245, 158, 11, 0.04) 0%, transparent 60%);
}
```

- [ ] **Step 6: Commit**

```bash
git add web-dashboard/role-gate.html
git commit -m "feat: role-gate背景重构 — 工业科技渐变+数据流网格+浮动粒子"
```

---

### Task 3: role-gate.html — 标题与副标题升级

**Files:**
- Modify: `web-dashboard/role-gate.html`

- [ ] **Step 1: 更新标题 CSS 为渐变发光字体**

替换 `.role-gate-title { ... }` 块：

```css
.role-gate-title {
  font-size: 34px; font-weight: 800; letter-spacing: -0.5px;
  margin-bottom: 8px;
  background: linear-gradient(135deg, #0EA5E9 0%, #8B5CF6 50%, #F59E0B 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 2px 12px rgba(14, 165, 233, 0.3));
}
```

- [ ] **Step 2: 更新副标题 CSS**

替换 `.role-gate-subtitle { ... }` 块：

```css
.role-gate-subtitle {
  font-size: 15px; color: var(--text-secondary); margin-bottom: 40px;
  letter-spacing: 1px; font-weight: 400;
}
```

- [ ] **Step 3: 更新 HTML 中的标题文案**

将 `<h1>` 保持不变。将 `<p class="role-gate-subtitle">` 替换为：

```html
<p class="role-gate-subtitle">同一智能平台 · 三大专属视角 · 赋能工业全链路运维升级</p>
```

- [ ] **Step 4: Commit**

```bash
git add web-dashboard/role-gate.html
git commit -m "feat: role-gate标题升级 — 渐变发光字体+价值型副标题"
```

---

### Task 4: role-gate.html — 角色卡片立体化 + 主题色 + 流光动效

**Files:**
- Modify: `web-dashboard/role-gate.html`

- [ ] **Step 1: 重写 .role-card 基础样式（立体玻璃 + 双阴影）**

替换 `.role-card { ... }` 和 `.role-card:hover { ... }` 块：

```css
.role-card {
  flex: 1; min-width: 260px; max-width: 300px;
  background: var(--glass-bg-card);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-xl);
  padding: 32px 24px 24px;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04) inset,
    0 1px 2px rgba(0, 0, 0, 0.2),
    0 8px 24px rgba(0, 0, 0, 0.3),
    0 20px 48px rgba(0, 0, 0, 0.2);
  cursor: pointer; text-align: center;
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative; overflow: hidden;
}
.role-card::before {
  content: '';
  position: absolute; top: 0; left: 12px; right: 12px; height: 3px;
  border-radius: 0 0 3px 3px;
  transition: all 0.4s ease;
}
.role-card:hover {
  transform: translateY(-10px) scale(1.04);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.06) inset,
    0 2px 4px rgba(0, 0, 0, 0.3),
    0 12px 36px rgba(0, 0, 0, 0.5),
    0 32px 64px rgba(0, 0, 0, 0.3);
}
.role-card:active { transform: scale(0.97); transition: all 0.1s ease; }
```

- [ ] **Step 2: 添加各角色主题色顶部发光条（含 hover 流光动画）**

替换 `.role-card.card-operator { ... }` 等三行：

```css
.role-card.card-operator::before {
  background: linear-gradient(90deg, transparent, var(--role-operator), var(--role-operator-glow), var(--role-operator), transparent);
  background-size: 200% 100%;
  box-shadow: 0 0 12px var(--role-operator-glow);
}
.role-card.card-manager::before {
  background: linear-gradient(90deg, transparent, var(--role-manager), var(--role-manager-glow), var(--role-manager), transparent);
  background-size: 200% 100%;
  box-shadow: 0 0 12px var(--role-manager-glow);
}
.role-card.card-developer::before {
  background: linear-gradient(90deg, transparent, var(--role-developer), var(--role-developer-glow), var(--role-developer), transparent);
  background-size: 200% 100%;
  box-shadow: 0 0 12px var(--role-developer-glow);
}
.role-card:hover::before {
  animation: lightFlow 1.5s ease-in-out infinite;
}
@keyframes lightFlow {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

- [ ] **Step 3: 更新图标样式（放大 + 主题色渐变）**

替换 `.role-card .card-icon { ... }`：

```css
.role-card .card-icon {
  font-size: 48px; margin-bottom: 16px; display: block;
  transition: transform 0.4s var(--transition-spring);
}
.role-card:hover .card-icon { transform: scale(1.1); }
```

- [ ] **Step 4: 更新角色名称样式（主题色 + 更大）**

替换 `.role-card .card-title { ... }`：

```css
.role-card .card-title {
  font-size: 18px; font-weight: 700; margin-bottom: 2px;
  transition: color 0.3s ease;
}
.role-card.card-operator .card-title { color: var(--role-operator); }
.role-card.card-manager .card-title { color: var(--role-manager); }
.role-card.card-developer .card-title { color: var(--role-developer); }
```

- [ ] **Step 5: 更新角色英文副标题**

替换 `.role-card .card-subtitle { ... }`：

```css
.role-card .card-subtitle {
  font-size: 10px; color: var(--text-muted); margin-bottom: 14px;
  text-transform: uppercase; letter-spacing: 0.08em; font-weight: 500;
}
```

- [ ] **Step 6: 更新功能描述样式（两行布局 + 数字高亮动效）**

替换 `.role-card .card-desc { ... }`：

```css
.role-card .card-desc {
  font-size: 12px; color: var(--text-secondary); line-height: 1.8;
}
.role-card .card-desc .desc-primary {
  display: block; font-weight: 600; color: var(--text-primary);
  font-size: 13px; margin-bottom: 6px;
}
.role-card .card-desc .desc-metrics {
  display: block; font-size: 11px; color: var(--text-muted);
}
.role-card .card-desc .metric-num {
  font-weight: 700; font-family: var(--font-mono);
  transition: all 0.3s ease;
  display: inline-block;
}
.role-card:hover .card-desc .metric-num {
  animation: numBounce 0.6s var(--transition-spring);
}
@keyframes numBounce {
  0%, 100% { transform: scale(1); }
  30% { transform: scale(1.25); color: var(--text-primary); }
  60% { transform: scale(0.95); }
}
```

- [ ] **Step 7: 替换 HTML 中的卡片内容为新价值文案**

替换三张卡片的 HTML：

```html
<div class="role-card card-operator" onclick="selectRole('operator')">
  <span class="card-icon">&#9881;</span>
  <div class="card-title">运维工程师</div>
  <div class="card-subtitle">Operator · 执行层</div>
  <div class="card-desc">
    <span class="desc-primary">设备全生命周期健康管理</span>
    <span class="desc-metrics">异常智能告警 · 工单自动流转 · 根因快速定位 · <span class="metric-num">运维成本降低 35%</span></span>
  </div>
</div>

<div class="role-card card-manager" onclick="selectRole('manager')">
  <span class="card-icon">&#128202;</span>
  <div class="card-title">生产管理负责人</div>
  <div class="card-subtitle">Manager · 决策层</div>
  <div class="card-desc">
    <span class="desc-primary">全局运维数据实时看板</span>
    <span class="desc-metrics">关键指标一目了然 · 成本效益精准分析 · <span class="metric-num">决策效率提升 50%</span> · <span class="metric-num">设备稼动率提高 15%</span></span>
  </div>
</div>

<div class="role-card card-developer" onclick="selectRole('developer')">
  <span class="card-icon">&#128295;</span>
  <div class="card-title">平台开发人员</div>
  <div class="card-subtitle">Developer · 全量视图</div>
  <div class="card-desc">
    <span class="desc-primary">一站式开发与运维平台</span>
    <span class="desc-metrics">完整数据探索 · 模型快速迭代 · 系统灵活扩展 · <span class="metric-num">开发周期缩短 60%</span></span>
  </div>
</div>
```

- [ ] **Step 8: Commit**

```bash
git add web-dashboard/role-gate.html
git commit -m "feat: role-gate卡片立体化 — 主题色流光+双阴影+价值文案+数字动效"
```

---

### Task 5: role-gate.html — 底部提示优化 + 响应式适配

**Files:**
- Modify: `web-dashboard/role-gate.html`

- [ ] **Step 1: 更新底部提示 CSS 和 HTML**

替换 `.role-gate-footer { ... }` 和 `.role-gate-footer span { ... }`：

```css
.role-gate-footer {
  text-align: center; margin-top: 40px;
  font-size: 13px; color: var(--text-muted);
  letter-spacing: 0.3px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
}
.role-gate-footer .footer-hint {
  color: var(--text-secondary); font-weight: 500;
}
.role-gate-footer .footer-arrow {
  display: inline-block; font-size: 16px;
  animation: arrowWiggle 2s ease-in-out infinite;
}
@keyframes arrowWiggle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}
```

替换 HTML 中的 `<p class="role-gate-footer">`：

```html
<p class="role-gate-footer">
  <span class="footer-arrow">&#8593;</span>
  <span>提示：任意页面顶部导航栏可<span class="footer-hint">一键切换角色</span>，无需重新登录</span>
</p>
```

- [ ] **Step 2: 更新响应式断点（适配新卡片宽度）**

替换 `@media` 块：

```css
@media (max-width: 860px) {
  .role-cards { flex-direction: column; align-items: center; }
  .role-card { max-width: 380px; min-width: 0; width: 100%; }
  .role-gate-title { font-size: 26px; }
  .role-gate-subtitle { font-size: 13px; letter-spacing: 0.5px; }
}
@media (max-width: 480px) {
  .role-gate-title { font-size: 22px; }
  .role-gate-subtitle { font-size: 12px; letter-spacing: 0; }
  .role-card { padding: 24px 18px 20px; }
  .role-card .card-icon { font-size: 36px; }
  .role-card .card-title { font-size: 16px; }
}
```

- [ ] **Step 3: Commit**

```bash
git add web-dashboard/role-gate.html
git commit -m "feat: role-gate底部提示优化+响应式适配"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 启动服务器**

```bash
cd web-dashboard; python app.py
```

- [ ] **Step 2: 验证角色选择页面渲染**

Visit `http://localhost:8765/role-gate`，逐项检查：

- [ ] 背景显示为深蓝工业渐变（非纯黑）
- [ ] 数据流网格线条可见（微弱）
- [ ] 浮动粒子缓慢上升
- [ ] 主标题为青→紫→橙渐变发光字体
- [ ] 副标题显示"同一智能平台 · 三大专属视角 · 赋能工业全链路运维升级"
- [ ] 三张卡片各有独立主题色发光条（蓝/橙/紫）
- [ ] 卡片背景为毛玻璃效果
- [ ] 卡片有双层阴影（柔和投影 + 深投影）
- [ ] Hover 时卡片上浮 10px + 放大 4% + 发光条流光动画
- [ ] Hover 时量化数字跳动一次
- [ ] Hover 时图标放大
- [ ] 卡片显示价值型文案（功能 + 数字指标）
- [ ] 底部提示有向上箭头动效
- [ ] 点击卡片正常跳转角色页面
- [ ] 响应式：860px 以下卡片纵向排列
- [ ] 无控制台 CSS/JS 报错

- [ ] **Step 3: 关闭服务器，完成**

---

## Verification Checklist

- [ ] 背景渐变 + 网格 + 粒子全部渲染
- [ ] 三张卡片各有蓝/橙/紫主题色
- [ ] 顶部发光条 hover 时流动
- [ ] 数字指标 hover 时跳动
- [ ] 卡片 hover 上浮 10px + 放大 4%
- [ ] 标题渐变发光
- [ ] 文案已全部替换为价值型
- [ ] 响应式布局正常
- [ ] 无 JS/CSS 控制台报错
- [ ] 点击跳转正常
- [ ] 仅修改 2 个文件，零 JS 逻辑变更
