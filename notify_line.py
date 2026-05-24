import os
import requests


def send_line_notification(results, date_str, dashboard_url=None):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("LINE_CHANNEL_ACCESS_TOKEN が設定されていません。スキップします。")
        return

    lines = [f"📊 SUUMO月次レポート ({date_str})\n"]
    for r in sorted(results, key=lambda x: (x["avg"] or 99999)):
        if r["avg"]:
            lines.append(f"【{r['station']}】{r['count']}件 | 坪単価avg: {r['avg']}万円")
        else:
            lines.append(f"【{r['station']}】{r['count']}件 | データなし")

    if dashboard_url:
        lines.append(f"\n📈 詳細はこちら: {dashboard_url}")

    message = "\n".join(lines)

    resp = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": message}]},
        timeout=30,
    )

    if resp.status_code == 200:
        print("LINE通知を送信しました")
    else:
        print(f"LINE通知エラー: {resp.status_code} {resp.text}")
