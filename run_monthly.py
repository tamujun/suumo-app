"""
月次SUUMOスクレイピング実行スクリプト
GitHub Actionsから呼び出される。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from scraper_selsta import scrape_all, STATION_CODES
from notify_line import send_line_notification
from generate_dashboard import generate_dashboard

DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "history.json"
CONFIG_FILE = Path("stations_config.json")


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def calc_stats(properties):
    tankas = sorted(p["tsubo_tanka"] for p in properties if p.get("tsubo_tanka"))
    if not tankas:
        return {"count": len(properties), "avg": None, "median": None, "min": None, "max": None}
    n = len(tankas)
    median = tankas[n // 2] if n % 2 == 1 else round((tankas[n // 2 - 1] + tankas[n // 2]) / 2, 1)
    return {
        "count": len(properties),
        "avg": round(sum(tankas) / n, 1),
        "median": round(median, 1),
        "min": round(min(tankas), 1),
        "max": round(max(tankas), 1),
    }


def main():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)

    target_stations = config.get("stations", list(STATION_CODES.keys()))
    date_str = datetime.now().strftime("%Y-%m-%d")
    dashboard_url = os.environ.get("DASHBOARD_URL")

    print(f"=== SUUMO月次スクレイピング開始: {date_str} ===")
    print(f"対象駅: {', '.join(target_stations)}\n")

    history = load_history()
    month_results = []
    errors = []

    for station_name in target_stations:
        station_code = STATION_CODES.get(station_name)
        if not station_code:
            print(f"[スキップ] 未知の駅: {station_name}")
            continue

        print(f"\n=== {station_name} ({station_code}) を取得中 ===")
        try:
            properties = scrape_all(station_code=station_code, station_name=station_name)
            stats = calc_stats(properties)
            entry = {"date": date_str, "station": station_name, **stats}
            history.append(entry)
            month_results.append(entry)
            print(f"  → {station_name}: {stats['count']}件, 坪単価平均 {stats['avg']}万円/坪")
        except Exception as e:
            print(f"  [エラー] {station_name}: {e}", file=sys.stderr)
            errors.append(station_name)

    save_history(history)
    print(f"\nデータ保存完了: {HISTORY_FILE}")

    generate_dashboard(history)

    if month_results:
        send_line_notification(month_results, date_str, dashboard_url)

    if errors:
        print(f"\n[警告] 以下の駅でエラーが発生しました: {', '.join(errors)}")

    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
