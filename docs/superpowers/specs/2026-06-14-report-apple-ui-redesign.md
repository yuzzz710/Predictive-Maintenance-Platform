# 报告模板 Apple 风格 UI 重构 — 设计文档

> 2026-06-14 | 目标：5 个报告模板统一适配 iOS 26 玻璃风格

## 范围

| 文件 | 类型 |
|------|------|
| `report_templates/weekly_report.html` | 8 板块周报（6 种报告类型共用） |
| `report_templates/device_report.html` | 单设备深度报告 |
| `report_templates/work_order_report.html` | LLM 工单执行单 |
| `report_templates/email_daily_health.html` | 每日巡检邮件 |
| `report_templates/email_weekly_report.html` | 周报通知邮件 |

## 改动规则（5 个模板统一应用）

### 1. 内联 Design Tokens
模板 `<style>` 顶部注入精简 `:root` + `[data-theme="light"]` 块（与 `shared/design-tokens.css` 同源）。

### 2. 背景
`body { background: #000 }` + `body::before` 三层环境光晕（青/蓝/紫 radial-gradient）。

### 3. 卡片
所有 `.section` → 玻璃卡片：
- `background: rgba(44,44,46,0.35)` + `backdrop-filter: blur(45px) saturate(220%)`
- `border-radius: 22px` + `border: 0.5px solid rgba(255,255,255,0.10)`
- `box-shadow` 双层：柔和投影 + `inset 0 0.5px 0 rgba(255,255,255,0.08)` 内高光

### 4. 封面
渐变背景 + 青色脉冲呼吸点 + 品牌标题。

### 5. 排版
| 层级 | 字号 | 字重 | 字体 |
|------|------|------|------|
| Hero | 28px | 700 | SF Pro Display |
| H1 | 20px | 700 | SF Pro Display |
| H2 | 16px | 600 | SF Pro Display |
| Body | 13px | 400 | PingFang SC |
| Caption | 11px | 500 | SF Pro Display |
| Data | 22px | 700 | SF Mono |

### 6. 打印兼容
`@media print` 保留 A4 适配：白色背景、隐藏光晕、黑色文字。

## 不改动
- Jinja2 模板逻辑（`{% if %}` / `{% for %}`）
- 变量名（`report.xxx` / `spec.xxx`）
- 图表 base64 嵌入方式
- 报告生成流水线
