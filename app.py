from flask import Flask, render_template, request
from scraper_selsta import scrape_all, STATION_CODES

app = Flask(__name__)


@app.route("/")
def index():
    station_name = request.args.get("station", "駒沢大学")
    station_code = STATION_CODES.get(station_name, "15340")

    properties = scrape_all(station_code=station_code, station_name=station_name)

    # 坪単価でソート（None は末尾に）
    properties.sort(
        key=lambda x: (x.get("tsubo_tanka") is None, x.get("tsubo_tanka") or 0)
    )

    return render_template(
        "index.html",
        properties=properties,
        stations=sorted(STATION_CODES.keys()),
        selected_station=station_name,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
