"""
智能设备预测性维护 — 系统架构图
Nature-figure style: schematic-led composite, clean spacing, no overlaps.
"""
import os
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Nature-figure typography ──
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "DejaVu Sans"],
    "font.size": 8,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "legend.frameon": False,
})

# ── Nature-inspired palette ──
C = {
    'data':  '#0F4D92',
    'skill': '#3775BA',
    'mcp':   '#42949E',
    'orch':  '#B64342',
    'app':   '#2D6A4F',
    'out':   '#9A4D8E',
    'arrow': '#767676',
    'bg':    '#FAFBFC',
}

# ── Canvas: wide schematic, generous height ──
FIG_W, FIG_H = 20, 13
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis('off')
ax.set_facecolor(C['bg'])

# ── Layout grid (y-coordinates of each layer band) ──
# Layer label width = 0.9, content area starts at x=1.2
MARGIN_L = 1.2       # left edge of content
MARGIN_R = 18.8      # right edge of content
CONTENT_W = MARGIN_R - MARGIN_L  # 17.6

layers = {
    'data':  {'y': 10.8, 'h': 1.6, 'color': C['data'],  'label': '数据层'},
    'skill': {'y': 8.2,  'h': 2.2, 'color': C['skill'], 'label': '技能层'},
    'mcp':   {'y': 5.6,  'h': 2.2, 'color': C['mcp'],   'label': 'MCP\n服务层'},
    'orch':  {'y': 3.0,  'h': 2.2, 'color': C['orch'],  'label': '编排层'},
    'app':   {'y': 0.4,  'h': 2.2, 'color': C['app'],   'label': '应用层'},
}
GAP = 0.35  # vertical gap between layer backgrounds


def draw_layer_bg(name, info):
    """Draw a subtle rounded background for a layer."""
    y, h = info['y'], info['h']
    rect = FancyBboxPatch((MARGIN_L - 0.1, y - GAP), CONTENT_W + 0.2, h + 2 * GAP,
                          boxstyle="round,pad=0.15", linewidth=0.8,
                          edgecolor=info['color'], facecolor=info['color'], alpha=0.04, zorder=0)
    ax.add_patch(rect)
    # Layer label — vertical on left
    ax.text(0.3, y + h / 2, info['label'], fontsize=9, fontweight='bold',
            color=info['color'], ha='center', va='center', rotation=90, zorder=5)


def draw_box(cx, cy, w, h, text, color, fontsize=7.5, bold=True, facecolor='white'):
    """Center-positioned rounded box. (cx,cy) = center of box."""
    x, y = cx - w / 2, cy - h / 2
    rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                          linewidth=1.0, edgecolor=color, facecolor=facecolor, zorder=4)
    ax.add_patch(rect)
    weight = 'bold' if bold else 'normal'
    ax.text(cx, cy, text, fontsize=fontsize, fontweight=weight,
            color='#272727', ha='center', va='center', zorder=5, linespacing=1.25)


def h_arrow(x1, x2, y, color=C['arrow'], lw=1.0):
    """Horizontal arrow."""
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw), zorder=3)


def v_arrow(x, y1, y2, color=C['arrow'], lw=1.2):
    """Vertical arrow."""
    ax.annotate('', xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw), zorder=3)


# ═══════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════
ax.text(FIG_W / 2, 12.55, '智能设备预测性维护 — 系统总体架构',
        fontsize=13, fontweight='bold', color='#272727', ha='center', va='center')
ax.text(FIG_W / 2, 12.05, '100台CNC设备  ·  4传感器参数  ·  数据层 → 技能层 → MCP层 → 编排层 → 应用层',
        fontsize=7.5, color='#767676', ha='center', va='center')

# ═══════════════════════════════════════════════
# LAYER 0 — Data source icons (above data layer, decorative)
# ═══════════════════════════════════════════════
csv_cy = 11.4
csv_items = [
    (2.5, 'MACHINE_LOG\n时序传感器+故障标签'),
    (6.5, 'MACHINE_SUMMARY\n设备元数据 · 成本'),
    (10.5, 'ASSEMBLY_LINE\n产线产品关联'),
    (14.5, 'TESTS\n产品测试数据'),
]
for cx, label in csv_items:
    draw_box(cx, csv_cy, 3.2, 0.95, label, C['data'], fontsize=7, bold=False)

# ═══════════════════════════════════════════════
# LAYER 1: 数据层 — 4 data files
# ═══════════════════════════════════════════════
draw_layer_bg('data', layers['data'])

# ═══════════════════════════════════════════════
# LAYER 2: 技能层 — pipeline: 1 → 2 ∥ 3 → 4 → 5
# ═══════════════════════════════════════════════
draw_layer_bg('skill', layers['skill'])
sk_y = layers['skill']['y'] + layers['skill']['h'] / 2  # center

sk = [
    (2.5,  sk_y,      2.4, 1.5, 'Skill 1\n数据准备\nz-score · 基线'),
    (5.8,  sk_y + 0.4, 2.4, 1.3, 'Skill 2\n统计推理\nT² · 告警'),
    (5.8,  sk_y - 0.4, 2.4, 1.3, 'Skill 3\nML推理\nXGBoost / MTNN'),
    (9.1,  sk_y,      2.4, 1.5, 'Skill 4\n异常诊断\n4种失效模式'),
    (12.4, sk_y,      2.8, 1.5, 'Skill 5\n决策引擎\n工单生成'),
]
for cx, cy, w, h, text in sk:
    draw_box(cx, cy, w, h, text, C['skill'], fontsize=7)

# Pipeline arrows
h_arrow(3.7, 4.55, sk_y + 0.4, C['skill'])  # 1→2
h_arrow(3.7, 4.55, sk_y - 0.4, C['skill'])  # 1→3
h_arrow(7.0, 7.85, sk_y + 0.4, C['skill'])  # 2→4
h_arrow(7.0, 7.85, sk_y - 0.4, C['skill'])  # 3→4
h_arrow(10.3, 10.9, sk_y, C['skill'])       # 4→5

# "parallel" label
ax.text(6.5, sk_y + 0.82, '并行', fontsize=6, color=C['orch'],
        ha='center', va='center', fontstyle='italic',
        bbox=dict(boxstyle='round,pad=0.1', facecolor='white',
                  edgecolor=C['orch'], alpha=0.7, lw=0.5), zorder=6)

# ═══════════════════════════════════════════════
# LAYER 3: MCP 服务层
# ═══════════════════════════════════════════════
draw_layer_bg('mcp', layers['mcp'])
mcp_y = layers['mcp']['y'] + layers['mcp']['h'] / 2

mcp_upper = [
    (2.5,  mcp_y + 0.45, 2.4, 0.85, 'prepare_data'),
    (5.8,  mcp_y + 0.45, 2.4, 0.85, 'run_stat_analysis'),
    (9.1,  mcp_y + 0.45, 2.4, 0.85, 'run_ml_analysis'),
    (12.4, mcp_y + 0.45, 2.4, 0.85, 'run_diagnosis'),
    (15.7, mcp_y + 0.45, 2.4, 0.85, 'generate_decision'),
]
mcp_lower = [
    (2.5,  mcp_y - 0.45, 2.4, 0.6, 'explain_predictability_limit'),
    (15.7, mcp_y - 0.45, 2.4, 0.6, 'query / list_alarm'),
]

for cx, cy, w, h, text in mcp_upper:
    draw_box(cx, cy, w, h, text, C['mcp'], fontsize=7)
for cx, cy, w, h, text in mcp_lower:
    draw_box(cx, cy, w, h, text, C['mcp'], fontsize=6.2, bold=False, facecolor='#f0f7f8')

# ═══════════════════════════════════════════════
# LAYER 4: 编排层
# ═══════════════════════════════════════════════
draw_layer_bg('orch', layers['orch'])
orch_y = layers['orch']['y'] + layers['orch']['h'] / 2

dag = [
    (2.5,  orch_y, 2.4, 1.4, 'data_prep\n数据准备'),
    (6.2,  orch_y + 0.35, 2.4, 1.1, 'stat_analysis\n统计推理'),
    (6.2,  orch_y - 0.35, 2.4, 1.1, 'ml_analysis\nML推理'),
    (9.9,  orch_y, 2.4, 1.4, 'diagnosis\n诊断'),
    (13.2, orch_y, 2.8, 1.4, 'decision\n决策引擎'),
]
for cx, cy, w, h, text in dag:
    draw_box(cx, cy, w, h, text, C['orch'], fontsize=7)

# DAG arrows
h_arrow(3.7, 4.95, orch_y + 0.35, C['orch'])
h_arrow(3.7, 4.95, orch_y - 0.35, C['orch'])
h_arrow(7.4, 8.65, orch_y + 0.35, C['orch'])
h_arrow(7.4, 8.65, orch_y - 0.35, C['orch'])
h_arrow(11.1, 11.7, orch_y, C['orch'])

ax.text(7.5, orch_y + 0.75, 'ThreadPool 并行执行', fontsize=6, color=C['orch'],
        ha='center', fontstyle='italic',
        bbox=dict(boxstyle='round,pad=0.1', facecolor='white',
                  edgecolor=C['orch'], alpha=0.7, lw=0.5), zorder=6)

# ═══════════════════════════════════════════════
# LAYER 5: 应用层
# ═══════════════════════════════════════════════
draw_layer_bg('app', layers['app'])
app_y = layers['app']['y'] + layers['app']['h'] / 2

apps = [
    (2.5,  app_y, 3.2, 1.5, '主仪表盘\nindex.html\n4 Tab · ECharts'),
    (6.5,  app_y, 3.2, 1.5, 'AI 聊天\nchat.html\nClaude + SSE'),
    (10.5, app_y, 3.2, 1.5, '报告系统\nreports.html\n设备/风险/周报'),
    (14.5, app_y, 3.2, 1.5, 'API 网关\ngateway.py\nFastAPI + MCP'),
]
for cx, cy, w, h, text in apps:
    draw_box(cx, cy, w, h, text, C['app'], fontsize=7.5)

# ═══════════════════════════════════════════════
# VERTICAL FLOW — layer-to-layer arrows
# ═══════════════════════════════════════════════
v_arrow_x = 1.6  # left side, between layer label and content

v_arrow(v_arrow_x, layers['data']['y'] - GAP,  layers['skill']['y'] + layers['skill']['h'] + GAP, C['arrow'])
v_arrow(v_arrow_x, layers['skill']['y'] - GAP, layers['mcp']['y'] + layers['mcp']['h'] + GAP, C['arrow'])
v_arrow(v_arrow_x, layers['mcp']['y'] - GAP,   layers['orch']['y'] + layers['orch']['h'] + GAP, C['arrow'])
v_arrow(v_arrow_x, layers['orch']['y'] - GAP,  layers['app']['y'] + layers['app']['h'] + GAP, C['arrow'])

# ═══════════════════════════════════════════════
# OUTPUT — final artifact highlight
# ═══════════════════════════════════════════════
out_cx, out_cy = 17.2, 9.5
out_rect = FancyBboxPatch((out_cx - 1.6, out_cy - 0.7), 3.2, 1.4,
                          boxstyle="round,pad=0.15", linewidth=2.0,
                          edgecolor=C['out'], facecolor='#fdf5fc', zorder=6)
ax.add_patch(out_rect)
ax.text(out_cx, out_cy + 0.3, '最终产物', fontsize=8.5, fontweight='bold',
        color=C['out'], ha='center', zorder=7)
ax.text(out_cx, out_cy - 0.2, 'maintenance_\nwork_orders.csv', fontsize=7, color=C['out'],
        ha='center', family='monospace', linespacing=1.3, zorder=7)

# Curved arrow from decision → output
ax.annotate('', xy=(15.6, 9.2), xytext=(14.4, 4.0),
            arrowprops=dict(arrowstyle='->', color=C['out'], lw=1.5,
                            connectionstyle="arc3,rad=0.35"), zorder=5)

# ═══════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════
plt.tight_layout(pad=0.3)
out_dir = os.path.dirname(os.path.abspath(__file__))
out_png = os.path.join(out_dir, 'architecture_diagram.png')
out_svg = os.path.join(out_dir, 'architecture_diagram.svg')
fig.savefig(out_png, dpi=300, bbox_inches='tight', facecolor=C['bg'], edgecolor='none')
fig.savefig(out_svg, bbox_inches='tight', facecolor=C['bg'], edgecolor='none')
plt.close()
print(f"Saved: {out_png}")
print(f"Saved: {out_svg}")
