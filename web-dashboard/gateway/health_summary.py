"""
Real-data health summary provider.

Reads equipment_health_score.csv and returns aggregated statistics.
Used by: routes.py (JUDGE_EXPLAIN_PROMPT injection), prompts.py (SYSTEM_PROMPT injection),
         assistant.js (speech library template population via /api/health-summary).
"""
import csv
import os
import json
from datetime import datetime

DASHBOARD_DATA = os.path.join(os.path.dirname(__file__), '..', 'data')


def get_health_summary() -> dict:
    """Read equipment_health_score.csv and return aggregated health statistics."""
    csv_path = os.path.join(DASHBOARD_DATA, 'equipment_health_score.csv')
    devices = []

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                devices.append({
                    'id': row['Equipment.Id'],
                    'score': float(row['health_score']),
                    'level': row['health_level'],
                    'trend': row.get('trend', ''),
                    'top_risk_factor': row.get('top_risk_factor_label', ''),
                })
    except FileNotFoundError:
        return {'error': 'equipment_health_score.csv not found', 'total_devices': 0}
    except Exception as e:
        return {'error': str(e), 'total_devices': 0}

    if not devices:
        return {'error': 'no device data', 'total_devices': 0}

    scores = [d['score'] for d in devices]

    # Level distribution
    level_dist = {'Healthy': 0, 'Warning': 0, 'Degrading': 0, 'Critical': 0}
    for d in devices:
        lv = d['level']
        if lv in level_dist:
            level_dist[lv] += 1

    # Score bins
    score_bins = {
        '<30': sum(1 for s in scores if s < 30),
        '30-40': sum(1 for s in scores if 30 <= s < 40),
        '40-60': sum(1 for s in scores if 40 <= s < 60),
        '60-80': sum(1 for s in scores if 60 <= s < 80),
        '80-100': sum(1 for s in scores if s >= 80),
    }

    # Top/bottom 5
    sorted_devices = sorted(devices, key=lambda d: d['score'])
    top5_lowest = [{'id': d['id'], 'score': d['score'], 'level': d['level']} for d in sorted_devices[:5]]
    top5_highest = [{'id': d['id'], 'score': d['score'], 'level': d['level']} for d in sorted_devices[-5:]]

    # Risk factor distribution
    risk_factors = {}
    for d in devices:
        rf = d.get('top_risk_factor_label', '') or 'Unknown'
        risk_factors[rf] = risk_factors.get(rf, 0) + 1

    return {
        'total_devices': len(devices),
        'mean_score': round(sum(scores) / len(scores), 1),
        'min_score': round(min(scores), 1),
        'max_score': round(max(scores), 1),
        'median_score': round(sorted(scores)[len(scores) // 2], 1),
        'level_distribution': level_dist,
        'score_bins': score_bins,
        'top5_lowest': top5_lowest,
        'top5_highest': top5_highest,
        'top_risk_factors': dict(sorted(risk_factors.items(), key=lambda x: -x[1])[:5]),
        'healthy_count': level_dist.get('Healthy', 0),
        'warning_count': level_dist.get('Warning', 0),
        'degrading_count': level_dist.get('Degrading', 0),
        'critical_count': level_dist.get('Critical', 0),
        'critical_pct': round(100 * level_dist.get('Critical', 0) / len(devices), 1),
        'degrading_pct': round(100 * level_dist.get('Degrading', 0) / len(devices), 1),
        'generated_at': datetime.now().isoformat(),
    }


def get_health_context_text() -> str:
    """Return a plain-text paragraph summarising current health data for prompt injection."""
    s = get_health_summary()
    if 'error' in s:
        return '（健康数据暂不可用）'

    lines = [
        '## 当前系统真实健康数据（必须基于此数据回答，禁止编造数字）',
        f'- 总设备数：{s["total_devices"]}台CNC数控机床',
        f'- 平均健康分：{s["mean_score"]}（满分100）',
        f'- 健康分范围：{s["min_score"]} ~ {s["max_score"]}',
        f'- 健康等级分布：Critical（危急）{s["critical_count"]}台（{s["critical_pct"]}%）| '
        f'Degrading（退化）{s["degrading_count"]}台（{s["degrading_pct"]}%）| '
        f'Warning（警告）{s["warning_count"]}台 | Healthy（健康）{s["healthy_count"]}台',
        f'- 健康分<30的危急设备：{s["score_bins"]["<30"]}台',
        f'- 健康分30-40的退化设备：{s["score_bins"]["30-40"]}台',
        f'- 健康分40-60的设备：{s["score_bins"]["40-60"]}台',
        f'- 健康分>60的设备：{s["score_bins"]["60-80"] + s["score_bins"]["80-100"]}台',
        f'- 健康分最低的5台设备：' + '、'.join(
            f'{d["id"]}({d["score"]})' for d in s['top5_lowest']
        ),
        f'- 最常见的风险因子：' + '、'.join(
            f'{k}({v}台)' for k, v in list(s['top_risk_factors'].items())[:3]
        ),
        '',
        '重要：以上数据来自项目CSV真实文件，每次请求时实时读取，与前端仪表盘数据完全一致。回答任何健康相关问题时必须以这些数字为准。',
    ]
    return '\n'.join(lines)


def get_health_json() -> str:
    """Return JSON string for the /api/health-summary endpoint."""
    return json.dumps(get_health_summary(), ensure_ascii=False, indent=2)
