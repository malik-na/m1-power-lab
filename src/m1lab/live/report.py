"""Self-contained HTML report over saved live results and the sleep ledger."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import time
from typing import Any

from m1lab.live import analysis

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;--card:#fff;--good:#1f7a4d;--bad:#b3261e;--accent:#2f5d9b;--bar:#c9d6ea}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#9a988f;--line:#2e2d2a;--card:#1c1c1a;--good:#5cc28f;--bad:#f08b80;--accent:#8fb3e8;--bar:#33465f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 10px}
.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.card b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
td.num{text-align:right}.good{color:var(--good)}.bad{color:var(--bad)}.wrap{overflow-x:auto}svg text{fill:var(--muted);font-size:11px}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
"""


def _load(results: Path) -> list[tuple[Path, dict[str, Any]]]:
    loaded = []
    for path in sorted(results.glob("*.json")):
        try:
            loaded.append((path, json.loads(path.read_text())))
        except (OSError, ValueError):
            continue
    return loaded


def _when(wall: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(wall)) if wall else "-"


def _w(value: Any, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"


def _effect_bar(delta: float, low: float | None, high: float | None, scale: float) -> str:
    width, mid = 260, 130
    def x(v: float) -> float:
        return mid + max(-1.0, min(1.0, v / scale)) * (mid - 6)
    color = "var(--good)" if high is not None and high < 0 else ("var(--bad)" if low is not None and low > 0 else "var(--muted)")
    parts = [f'<svg width="{width}" height="18" role="img" aria-label="effect {delta * 1000:+.0f} mW">',
             f'<line x1="{mid}" y1="2" x2="{mid}" y2="16" stroke="var(--line)"/>']
    if low is not None and high is not None:
        parts.append(f'<line x1="{x(low):.1f}" y1="9" x2="{x(high):.1f}" y2="9" stroke="{color}" stroke-width="2"/>')
    parts.append(f'<circle cx="{x(delta):.1f}" cy="9" r="4" fill="{color}"/></svg>')
    return "".join(parts)


def _sleep_chart(entries: list[dict[str, Any]]) -> str:
    points = [(e.get("end_wall", 0), w) for e in entries if (w := analysis.sleep_watts(e)) is not None and e.get("slept_s", 0) > 20]
    if len(points) < 2:
        return ""
    width, height, pad = 960, 180, 34
    xs = [p[0] for p in points]
    top = max(p[1] for p in points) * 1.15 or 1
    x0, x1 = min(xs), max(xs)
    def px(t: float) -> float:
        return pad + (t - x0) / max(x1 - x0, 1) * (width - 2 * pad)
    def py(v: float) -> float:
        return height - pad + 10 - v / top * (height - pad - 10)
    dots = "".join(f'<circle cx="{px(t):.1f}" cy="{py(v):.1f}" r="3.5" fill="var(--accent)"><title>{v:.3f} W at {_when(t)}</title></circle>' for t, v in points)
    grid = "".join(
        f'<line x1="{pad}" x2="{width - pad}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="var(--line)"/><text x="4" y="{py(v) + 4:.1f}">{v:.2f}</text>'
        for v in (top / 4, top / 2, top * 3 / 4)
    )
    return f'<div class="wrap"><svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="sleep power over time">{grid}{dots}<text x="{pad}" y="{height - 4}">{_when(x0)}</text><text x="{width - pad - 90}" y="{height - 4}">{_when(x1)}</text></svg></div>'


def render_report(results: Path, ledger: list[dict[str, Any]]) -> str:
    """Build the report HTML from saved results and ledger records; writes nothing."""
    loaded = _load(results)
    ledger = [e for e in ledger if analysis.is_sleep(e)]
    records = [(p, d) for p, d in loaded if d.get("kind") == "record"]
    ab_jobs: list[dict[str, Any]] = []
    sleeps: list[dict[str, Any]] = []
    for _, data in loaded:
        if data.get("kind") == "batch":
            for job in data.get("jobs", []):
                if job.get("job_kind") == "ab" and "blocks" in job:
                    ab_jobs.append(job)
                elif job.get("job_kind") == "sleep" and "slept_s" in job and analysis.is_sleep(job):
                    sleeps.append(job)
    known = {round(s.get("end_wall", 0)) for s in sleeps}
    sleeps += [e for e in ledger if round(e.get("end_wall", 0)) not in known]
    sleeps.sort(key=lambda e: e.get("end_wall", 0))

    html = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>M1 Power Report</title><style>{CSS}</style></head><body><main>"]
    html.append("<h1>M1 power report</h1>")
    html.append(f"<p class='muted'>Generated {_when(time.time())} from {len(loaded)} saved results and {len(ledger)} ledger entries.</p>")

    cards = []
    if records:
        latest = records[-1][1]
        cards.append(("Latest idle capture", f"{_w(latest['summary'].get('sys_w'))} W", latest.get("label") or _when(latest.get("started_wall"))))
    sleep_summary = analysis.summarize_sleeps(sleeps)
    if sleep_summary.get("count"):
        cards.append(("Sleep draw (weighted)", f"{_w(sleep_summary['sleep_w_weighted'])} W", f"{sleep_summary['count']} sleeps, {sleep_summary['slept_hours']} h"))
        if sleep_summary.get("battery_count"):
            cards.append(("Sleep draw on battery", f"{_w(sleep_summary['battery_w_weighted'])} W", f"{sleep_summary['battery_count']} unplugged sleeps"))
        cards.append(("CPUs powered down in sleep", f"{100 * sleep_summary['s2idle_cpus_pd_median']:.0f}%", "median across sleeps"))
    if ab_jobs:
        cards.append(("Knob experiments", str(len(ab_jobs)), "randomized paired blocks"))
    if cards:
        html.append("<div class='cards'>" + "".join(f"<div class='card'><span class='muted'>{escape(t)}</span><b>{escape(v)}</b><span class='muted'>{escape(s)}</span></div>" for t, v, s in cards) + "</div>")

    if ab_jobs:
        analyzed = sorted((analysis.analyze_ab(j) | {"_job": j} for j in ab_jobs), key=lambda a: a["effects"].get("sys_w", {}).get("delta", 0))
        scale = max(
            (abs(a["effects"]["sys_w"]["delta"]) + abs((a["effects"]["sys_w"]["ci_high"] or 0) - (a["effects"]["sys_w"]["ci_low"] or 0)) / 2 for a in analyzed if "sys_w" in a["effects"]),
            default=0.1,
        ) or 0.1
        html.append("<h2>Knob effects on system power</h2><p class='muted'>B minus A, each pair measured back to back in random order. Bars are 95% confidence intervals; green saves power.</p>")
        html.append("<div class='wrap'><table><tr><th>Knob</th><th>A → B</th><th class='num'>A W</th><th class='num'>B W</th><th>Effect</th><th>Verdict</th><th>When</th></tr>")
        for a in analyzed:
            e = a["effects"].get("sys_w")
            if not e:
                continue
            job = a["_job"]
            html.append(
                f"<tr><td><code>{escape(str(a['knob']))}</code></td><td>{escape(str(a['a']))} → {escape(str(a['b']))}</td>"
                f"<td class='num'>{_w(e['mean_a'])}</td><td class='num'>{_w(e['mean_b'])}</td>"
                f"<td>{_effect_bar(e['delta'], e['ci_low'], e['ci_high'], scale)}</td><td>{escape(a.get('verdict', ''))}</td>"
                f"<td class='muted'>{_when(job.get('started_wall'))}<br>display {escape(str(job.get('context', {}).get('display')))}</td></tr>"
            )
        html.append("</table></div>")

    if records:
        html.append("<h2>Idle captures</h2><div class='wrap'><table><tr><th>When</th><th>Label</th><th>Display</th><th class='num'>System W</th><th class='num'>DC-in W</th><th class='num'>SoC W</th><th class='num'>IRQ/s</th><th>Top wakers</th></tr>")
        for _, data in reversed(records[-30:]):
            s = data["summary"]
            wakers = ", ".join(f"{escape(w['comm'])} {w['wakeups_s']:.0f}/s" for w in s.get("top_wakers", [])[:4])
            html.append(
                f"<tr><td>{_when(data.get('started_wall'))}</td><td>{escape(data.get('label') or '')}</td><td>{escape(str(data.get('context', {}).get('display')))}</td>"
                f"<td class='num'>{_w(s.get('sys_w'))}</td><td class='num'>{_w(s.get('dcin_acc_w'))}</td><td class='num'>{_w(s.get('soc_w'))}</td>"
                f"<td class='num'>{_w(s.get('irq_s'), 0)}</td><td class='muted'>{wakers}</td></tr>"
            )
        html.append("</table></div>")

    if sleeps:
        html.append("<h2>Sleep ledger</h2><p class='muted'>Every suspend bracketed by the systemd-sleep hook. Power is the SMC DC-in energy accumulator over the bracket on AC and the battery's energy drop when unplugged (DC-in reads about 0 W on battery).</p>")
        html.append(_sleep_chart(sleeps))
        html.append("<div class='wrap'><table><tr><th>Ended</th><th class='num'>Slept</th><th class='num'>Power W</th><th>Source</th><th class='num'>Battery %/h</th><th class='num'>CPUs powered down</th><th>Woken by</th><th>Knobs</th></tr>")
        for e in reversed(sleeps[-60:]):
            wake = ", ".join(escape(name) for name, _ in e.get("wake_sources", [])[:3])
            pct = e.get("battery_pct_per_hour") if not e.get("on_ac") else None
            html.append(
                f"<tr><td>{_when(e.get('end_wall'))}</td><td class='num'>{e.get('slept_s', 0) / 60:.1f} min</td><td class='num'>{_w(analysis.sleep_watts(e))}</td>"
                f"<td class='muted'>{'AC' if e.get('on_ac') else 'battery'}</td><td class='num'>{_w(pct, 2) if pct is not None else '-'}</td><td class='num'>{100 * e.get('s2idle_cpus_pd', 0):.0f}%</td>"
                f"<td>{wake}</td><td class='muted'>{escape(json.dumps(e.get('knobs'))) if e.get('knobs') else ''}</td></tr>"
            )
        html.append("</table></div>")

    html.append("</main></body></html>")
    return "".join(html)


def write_report(results: Path, ledger: list[dict[str, Any]], out: Path | None = None) -> Path:
    path = out or results / "report.html"
    path.write_text(render_report(results, ledger))
    return path
