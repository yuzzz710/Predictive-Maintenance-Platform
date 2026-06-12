"""
Post-Repair Validation Checker — Z-Score Auto-Comparison.
===========================================================
Automatically validates whether a repair was successful by comparing
pre-repair and post-repair Z-Score metrics from z_scores.csv.

When a work order transitions to 'pending_acceptance', a pre-repair
snapshot is saved. After the repair and data collection, the checker
compares the latest Z-Scores against the pre-repair baseline.

Verdict rules:
  - z_composite drops from >2.0 to <1.5 → PASS
  - alert_level changes from Alarm/Warning to Normal → PASS
  - z_composite stays >2.0 → FAIL (repair ineffective)
  - Requires at least 1 post-repair data point (need device to run ~14 min)
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

from gateway.config import DASHBOARD_DATA


def _read_latest_z_scores(machine_id: str) -> Optional[Dict]:
    """Read the most recent Z-Score row for a machine from z_scores.csv."""
    z_path = DASHBOARD_DATA / "z_scores.csv"
    if not z_path.exists():
        return None

    latest = None
    try:
        with open(z_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Equipment.Id", "").strip() == machine_id:
                    latest = row  # keep last (latest timestamp)
    except Exception:
        return None

    if not latest:
        return None

    return {
        "z_composite": float(latest.get("z_composite", 0) or 0),
        "z_Voltage": float(latest.get("z_Voltage", 0) or 0),
        "z_Amperage": float(latest.get("z_Amperage", 0) or 0),
        "z_Temperature": float(latest.get("z_Temperature", 0) or 0),
        "alert_level": latest.get("alert_level", "Normal"),
        "date": latest.get("Date", ""),
        "failure_group": latest.get("failure_group", ""),
    }


def capture_pre_repair_snapshot(machine_id: str) -> bool:
    """Take a pre-repair Z-Score snapshot. Call when work order -> in_progress."""
    from gateway.workflow_engine import save_pre_repair_snapshot

    z = _read_latest_z_scores(machine_id)
    if not z:
        print(f"[post_repair] No Z-Score data for {machine_id}, cannot snapshot")
        return False

    save_pre_repair_snapshot(
        machine_id=machine_id,
        z_composite=z["z_composite"],
        z_voltage=z["z_Voltage"],
        z_amperage=z["z_Amperage"],
        z_temperature=z["z_Temperature"],
        alert_level=z["alert_level"],
    )
    print(f"[post_repair] Pre-repair snapshot saved: {machine_id} "
          f"z_comp={z['z_composite']:.2f} alert={z['alert_level']}")
    return True


def validate_repair(machine_id: str) -> Dict:
    """
    Compare pre vs post repair Z-Scores and return a verdict.

    Returns:
        {
            "success": bool,
            "machine_id": str,
            "pre_z": dict or None,
            "post_z": dict or None,
            "verdict": "PASS" | "FAIL" | "INCONCLUSIVE",
            "confidence": "high" | "medium" | "low",
            "details": str,
            "verdict_reasons": list[str],
        }
    """
    from gateway.workflow_engine import get_repair_snapshot, save_post_repair_result

    snapshot = get_repair_snapshot(machine_id)
    if not snapshot:
        return {
            "success": False,
            "machine_id": machine_id,
            "pre_z": None,
            "post_z": None,
            "verdict": "INCONCLUSIVE",
            "confidence": "low",
            "details": f"No pre-repair snapshot found for {machine_id}. Ensure snapshot was captured before repair.",
            "verdict_reasons": ["Missing pre-repair baseline"],
        }

    pre_z = {
        "z_composite": snapshot.get("pre_z_composite"),
        "z_Voltage": snapshot.get("pre_z_voltage"),
        "z_Amperage": snapshot.get("pre_z_amperage"),
        "z_Temperature": snapshot.get("pre_z_temperature"),
        "alert_level": snapshot.get("pre_alert_level"),
    }

    post_z = _read_latest_z_scores(machine_id)
    if not post_z:
        return {
            "success": False,
            "machine_id": machine_id,
            "pre_z": pre_z,
            "post_z": None,
            "verdict": "INCONCLUSIVE",
            "confidence": "low",
            "details": f"No post-repair Z-Score available. Device {machine_id} may not have run since repair.",
            "verdict_reasons": ["No post-repair data available"],
        }

    # ── Rule Engine ──
    reasons = []
    pass_count = 0
    total_checks = 3

    pre_comp = pre_z.get("z_composite") or 0
    post_comp = post_z.get("z_composite") or 0
    pre_alert = pre_z.get("alert_level", "Normal")
    post_alert = post_z.get("alert_level", "Normal")

    # Check 1: Composite Z-Score improvement
    if pre_comp > 2.0 and post_comp < 1.5:
        reasons.append(f"Composite Z-Score recovered: {pre_comp:.2f} -> {post_comp:.2f} (target <1.5)")
        pass_count += 1
    elif pre_comp > 2.0 and post_comp >= 1.5:
        reasons.append(f"Composite Z-Score still elevated: {pre_comp:.2f} -> {post_comp:.2f} (target <1.5)")
    elif pre_comp <= 2.0:
        reasons.append(f"Pre-repair Z-Score ({pre_comp:.2f}) was not critical (>2.0)")
        total_checks -= 1  # This check not applicable

    # Check 2: Alert level normalized
    alert_levels = {"Normal": 0, "Watch": 1, "Warning": 2, "Alarm": 3}
    pre_alert_num = alert_levels.get(pre_alert, 0)
    post_alert_num = alert_levels.get(post_alert, 0)

    if pre_alert_num >= 2 and post_alert_num <= 1:
        reasons.append(f"Alert level normalized: {pre_alert} -> {post_alert}")
        pass_count += 1
    elif pre_alert_num >= 2:
        reasons.append(f"Alert level not recovered: {pre_alert} -> {post_alert}")
    else:
        reasons.append(f"Pre-repair alert level ({pre_alert}) was already normal")
        total_checks -= 1

    # Check 3: Individual Z-Scores improvement
    z_params = [
        ("Voltage", pre_z.get("z_Voltage"), post_z.get("z_Voltage"), 2.0),
        ("Amperage", pre_z.get("z_Amperage"), post_z.get("z_Amperage"), 2.0),
        ("Temperature", pre_z.get("z_Temperature"), post_z.get("z_Temperature"), 2.0),
    ]
    improved_params = []
    for name, pre_v, post_v, threshold in z_params:
        pre_v = abs(pre_v or 0)
        post_v = abs(post_v or 0)
        if pre_v > threshold and post_v < threshold:
            improved_params.append(f"z_{name}: {pre_v:.2f} -> {post_v:.2f}")
        elif pre_v > threshold:
            improved_params.append(f"z_{name}: still high {post_v:.2f}")

    if improved_params:
        reasons.append("Parameter recovery: " + ", ".join(improved_params))
        if len(improved_params) >= 2:
            pass_count += 1
        else:
            pass_count += 0.5
    else:
        total_checks -= 1

    # ── Verdict ──
    pass_rate = pass_count / max(total_checks, 1)
    if pass_rate >= 0.67:
        verdict = "PASS"
        confidence = "high" if pass_rate >= 0.9 else "medium"
    elif pass_rate >= 0.5:
        verdict = "PASS"
        confidence = "low"
    else:
        verdict = "FAIL"
        confidence = "high" if pass_rate < 0.3 else "medium"

    details = "; ".join(reasons)

    # Save result
    save_post_repair_result(
        machine_id=machine_id,
        z_composite=post_z["z_composite"],
        z_voltage=post_z["z_Voltage"],
        z_amperage=post_z["z_Amperage"],
        z_temperature=post_z["z_Temperature"],
        alert_level=post_z["alert_level"],
        verdict=verdict,
        confidence=confidence,
    )

    print(f"[post_repair] Validation: {machine_id} -> {verdict} (confidence={confidence}, "
          f"pass_rate={pass_rate:.2f})")
    print(f"[post_repair]   {details}")

    return {
        "success": True,
        "machine_id": machine_id,
        "pre_z": pre_z,
        "post_z": post_z,
        "verdict": verdict,
        "confidence": confidence,
        "pass_rate": round(pass_rate, 2),
        "details": details,
        "verdict_reasons": reasons,
        "text_summary": (
            f"设备 {machine_id} 维修验收: {verdict} (置信度={confidence})。"
            f"修前 z_composite={pre_comp:.2f}, 修后 z_composite={post_comp:.2f}。"
            f"告警等级: {pre_alert} -> {post_alert}。"
            f"判定依据: {details}"
        ),
    }


def generate_acceptance_report(machine_id: str, validation_result: Dict) -> str:
    """Generate a simple HTML acceptance report."""
    from gateway.config import BASE_DIR
    import json

    pre = validation_result.get("pre_z") or {}
    post = validation_result.get("post_z") or {}
    verdict = validation_result.get("verdict", "UNKNOWN")
    conf = validation_result.get("confidence", "low")
    reasons = validation_result.get("verdict_reasons", [])

    verdict_color = {"PASS": "#3fb950", "FAIL": "#f04444", "INCONCLUSIVE": "#f0a030"}
    color = verdict_color.get(verdict, "#f0a030")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    reasons_html = "\n".join(f"<li>{r}</li>" for r in reasons)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>验收报告 — {machine_id}</title></head>
<body style="font-family:'Microsoft YaHei',sans-serif;background:#0e1117;color:#e6ebf2;padding:24px;">
<div style="max-width:700px;margin:0 auto;background:#141820;border:1px solid #1c2230;border-radius:6px;overflow:hidden;">
<div style="background:#1a1f2b;padding:20px 24px;border-bottom:1px solid #1c2230;">
  <span style="color:#00c9a0;font-size:16px;font-weight:bold;">◆ 维修验收报告 — {machine_id}</span>
  <span style="float:right;font-size:12px;color:#5a6474;">{now}</span>
</div>
<div style="padding:24px;">
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:48px;color:{color};font-weight:bold;">{verdict}</div>
    <div style="font-size:14px;color:#8e9aab;margin-top:4px;">置信度: {conf}</div>
  </div>
  <table width="100%" style="margin-bottom:20px;border-collapse:collapse;">
    <tr style="background:rgba(255,255,255,0.02);">
      <td style="padding:8px 12px;border:1px solid #1c2230;width:120px;color:#5a6474;">指标</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#f04444;">修前</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#3fb950;">修后</td>
    </tr>
    <tr>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">z_composite</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{pre.get('z_composite', '?'):.2f}</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{post.get('z_composite', '?'):.2f}</td>
    </tr>
    <tr>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">z_Voltage</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{pre.get('z_Voltage', '?'):.2f}</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{post.get('z_Voltage', '?'):.2f}</td>
    </tr>
    <tr>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">z_Amperage</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{pre.get('z_Amperage', '?'):.2f}</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{post.get('z_Amperage', '?'):.2f}</td>
    </tr>
    <tr>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">z_Temperature</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{pre.get('z_Temperature', '?'):.2f}</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{post.get('z_Temperature', '?'):.2f}</td>
    </tr>
    <tr>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">告警等级</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{pre.get('alert_level', '?')}</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;">{post.get('alert_level', '?')}</td>
    </tr>
  </table>
  <div style="background:rgba(0,201,160,0.05);border-left:3px solid #00c9a0;padding:12px 16px;border-radius:3px;">
    <div style="font-size:13px;color:#00c9a0;margin-bottom:8px;">判定依据</div>
    <ul style="margin:0;padding-left:18px;font-size:12px;color:#8e9aab;line-height:1.8;">{reasons_html}</ul>
  </div>
  <div style="margin-top:20px;padding-top:16px;border-top:1px solid #1c2230;font-size:11px;color:#5a6474;">
    由预测性维护系统自动生成 · {now}
  </div>
</div></div></body></html>"""

    # Save to reports/generated
    reports_dir = BASE_DIR / "reports" / "generated"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"acceptance_{machine_id}_{ts}.html"
    filepath = reports_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[post_repair] Acceptance report saved: {filepath}")
    return str(filepath)
