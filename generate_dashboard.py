import json
from collections import defaultdict
from pathlib import Path

DOCS_DIR = Path("docs")


def generate_dashboard(history):
    DOCS_DIR.mkdir(exist_ok=True)

    by_station = defaultdict(list)
    for entry in history:
        by_station[entry["station"]].append(entry)

    for station in by_station:
        by_station[station].sort(key=lambda x: x["date"])

    stations = sorted(by_station.keys())

    chart_data = {}
    for station in stations:
        entries = by_station[station]
        chart_data[station] = {
            "dates": [e["date"] for e in entries],
            "avg": [e.get("avg") for e in entries],
            "median": [e.get("median") for e in entries],
            "count": [e.get("count") for e in entries],
        }

    chart_data_json = json.dumps(chart_data, ensure_ascii=False)
    stations_json = json.dumps(stations, ensure_ascii=False)

    latest = []
    for station in stations:
        entries = by_station[station]
        if entries:
            latest.append(entries[-1])
    latest.sort(key=lambda x: (x.get("avg") is None, x.get("avg") or 0))

    rows_html = ""
    for r in latest:
        avg = f"{r['avg']}万円" if r.get("avg") else "-"
        median = f"{r.get('median')}万円" if r.get("median") else "-"
        mn = f"{r.get('min')}万円" if r.get("min") else "-"
        mx = f"{r.get('max')}万円" if r.get("max") else "-"
        rows_html += f"""
            <tr>
              <td>{r["station"]}</td>
              <td class="num">{r.get("count", 0)}</td>
              <td class="num avg">{avg}</td>
              <td class="num">{median}</td>
              <td class="num">{mn}</td>
              <td class="num">{mx}</td>
              <td class="num">{r["date"]}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SUUMO 坪単価トレンド</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Hiragino Sans", "Meiryo", sans-serif; background: #f5f6fa; color: #2d3436; }}
    header {{ background: #0984e3; color: #fff; padding: 16px 24px; }}
    header h1 {{ font-size: 1.3rem; font-weight: 700; }}
    header p {{ font-size: 0.85rem; opacity: 0.85; margin-top: 2px; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
    .card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.08); padding: 20px; margin-bottom: 24px; }}
    .card h2 {{ font-size: 1rem; font-weight: 700; margin-bottom: 16px; color: #0984e3; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
    .tab {{ padding: 6px 14px; border-radius: 20px; border: 2px solid #0984e3; color: #0984e3;
             background: #fff; cursor: pointer; font-size: 0.85rem; transition: all .2s; }}
    .tab.active {{ background: #0984e3; color: #fff; }}
    .tab:hover:not(.active) {{ background: #e8f4fd; }}
    .chart-wrap {{ position: relative; height: 320px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    th {{ background: #f0f6ff; text-align: left; padding: 10px 12px; border-bottom: 2px solid #dfe6e9; }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }}
    tr:hover td {{ background: #f8fbff; }}
    .num {{ text-align: right; }}
    .avg {{ font-weight: 700; color: #0984e3; }}
    @media (max-width: 600px) {{
      table {{ font-size: 0.78rem; }}
      th, td {{ padding: 8px 6px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>🏠 SUUMO 坪単価トレンド</h1>
    <p>東京・世田谷エリア 月次自動集計</p>
  </header>
  <main>
    <div class="card">
      <h2>📈 坪単価推移（月次）</h2>
      <div class="tabs" id="tabs"></div>
      <div class="chart-wrap">
        <canvas id="chart"></canvas>
      </div>
    </div>
    <div class="card">
      <h2>📋 最新データ一覧（坪単価 安い順）</h2>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th>駅名</th>
              <th class="num">件数</th>
              <th class="num">坪単価 平均</th>
              <th class="num">中央値</th>
              <th class="num">最低</th>
              <th class="num">最高</th>
              <th class="num">取得日</th>
            </tr>
          </thead>
          <tbody>{rows_html}
          </tbody>
        </table>
      </div>
    </div>
  </main>
  <script>
    const DATA = {chart_data_json};
    const STATIONS = {stations_json};

    const COLORS = [
      "#0984e3","#e17055","#00b894","#6c5ce7","#fdcb6e",
      "#d63031","#00cec9","#fd79a8","#2d3436","#55efc4"
    ];

    const ctx = document.getElementById("chart").getContext("2d");
    let chart = null;
    let activeStation = STATIONS[0] || null;

    function buildTabs() {{
      const tabsEl = document.getElementById("tabs");
      STATIONS.forEach((s, i) => {{
        const btn = document.createElement("button");
        btn.className = "tab" + (s === activeStation ? " active" : "");
        btn.textContent = s;
        btn.onclick = () => {{
          activeStation = s;
          document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
          btn.classList.add("active");
          renderChart();
        }};
        tabsEl.appendChild(btn);
      }});
    }}

    function renderChart() {{
      if (!activeStation || !DATA[activeStation]) return;
      const d = DATA[activeStation];
      if (chart) chart.destroy();
      chart = new Chart(ctx, {{
        type: "line",
        data: {{
          labels: d.dates,
          datasets: [
            {{
              label: "坪単価 平均（万円/坪）",
              data: d.avg,
              borderColor: "#0984e3",
              backgroundColor: "rgba(9,132,227,.1)",
              borderWidth: 2,
              pointRadius: 5,
              fill: true,
              tension: 0.3,
            }},
            {{
              label: "坪単価 中央値（万円/坪）",
              data: d.median,
              borderColor: "#e17055",
              backgroundColor: "rgba(225,112,85,.05)",
              borderWidth: 2,
              pointRadius: 4,
              fill: false,
              tension: 0.3,
              borderDash: [5, 4],
            }},
          ],
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ position: "top" }},
            title: {{
              display: true,
              text: activeStation + " 坪単価推移",
              font: {{ size: 14 }},
            }},
            tooltip: {{
              callbacks: {{
                afterBody: (items) => {{
                  const idx = items[0]?.dataIndex;
                  const cnt = d.count[idx];
                  return cnt != null ? ["件数: " + cnt + "件"] : [];
                }},
              }},
            }},
          }},
          scales: {{
            y: {{
              title: {{ display: true, text: "万円/坪" }},
              beginAtZero: false,
            }},
          }},
        }},
      }});
    }}

    buildTabs();
    renderChart();
  </script>
</body>
</html>
"""

    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"ダッシュボードを生成しました: {out}")


if __name__ == "__main__":
    history_path = Path("data/history.json")
    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
        generate_dashboard(history)
    else:
        print("data/history.json が見つかりません")
