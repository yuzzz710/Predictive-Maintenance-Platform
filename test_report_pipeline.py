"""Quick end-to-end test of refactored report pipeline."""
import sys
sys.path.insert(0, 'web-dashboard')

from gateway.report_orchestrator import generate_maintenance_report

def test(report_type, **kwargs):
    label = kwargs.pop('label', report_type)
    print(f'--- {label} ---')
    r = generate_maintenance_report(report_type, **kwargs)
    ok = r.get('success')
    html = r.get('html_url', 'NONE')
    pdf = r.get('pdf_url', 'NONE')
    size = r.get('html_size_kb', 0)
    err = r.get('error', '')
    print(f'  success={ok}  html={html}  pdf={pdf}  size={size}KB')
    if err:
        print(f'  ERROR: {err[:300]}')
    if not ok:
        tb = r.get('traceback', '')[:500]
        if tb:
            print(f'  TRACEBACK: {tb}')
    print()
    return ok

results = []
results.append(test('weekly', top_n=2, label='weekly (top 2)'))
results.append(test('device', machine_id='CNC_001', label='device CNC_001'))
results.append(test('risk', top_n=3, label='risk (top 3)'))
results.append(test('thermal', top_n=2, label='thermal'))
results.append(test('health_critical', health_threshold=40, label='health_critical (<40)'))
results.append(test('parts_summary', top_n=3, label='parts_summary'))

passed = sum(1 for r in results if r)
total = len(results)
print(f'Results: {passed}/{total} passed')
