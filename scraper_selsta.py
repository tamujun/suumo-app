import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup


# 駅コード辞書（SUUMOの実ページから取得した正確な値）
STATION_CODES = {
    "駒沢大学": "15340",
    "三軒茶屋": "16720",
    "池尻大橋": "02000",
    "渋谷": "17640",
    "自由が丘": "18410",
    "学芸大学": "07660",
    "都立大学": "26730",
    "二子玉川": "34230",
    "用賀": "40800",
    "桜新町": "16140",
    "中目黒": "27580",
    "祐天寺": "40640",
    "武蔵小山": "38730",
    "西小山": "28780",
    "目黒": "39110",
    "五反田": "14970",
    "大岡山": "05520",
    "田園調布": "25320",
    "成城学園前": "20990",
    "経堂": "12020",
    "下北沢": "18010",
    "明大前": "39030",
    "笹塚": "16280",
    "代田橋": "21960",
    "松陰神社前": "18530",
    "世田谷": "21210",
    "上町": "09410",
    "豪徳寺": "14220",
    "千歳船橋": "24140",
    "喜多見": "11580",
    "狛江": "15260",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

TSUBO_RATIO = 3.30578  # 1坪 = 3.30578 m²
MAX_WALK_MINUTES = 15   # 徒歩15分以内


def get_urls(station_code):
    """駅コードから新築・中古の検索URLを生成する"""
    return {
        "新築": f"https://suumo.jp/ikkodate/tokyo/ek_{station_code}/",
        "中古": f"https://suumo.jp/chukoikkodate/tokyo/ek_{station_code}/",
    }


def parse_price(text):
    """価格文字列から万円単位の数値を抽出する"""
    text = text.strip().replace(",", "").replace("，", "")
    m = re.search(r"(\d+)\s*億\s*(\d*)\s*万円", text)
    if m:
        oku = int(m.group(1))
        man = int(m.group(2)) if m.group(2) else 0
        return oku * 10000 + man
    m = re.search(r"(\d+)\s*万円", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*億円", text)
    if m:
        return int(m.group(1)) * 10000
    return None


def parse_area(text):
    """面積文字列からm²の数値を抽出する"""
    text = text.strip().replace(",", "")
    m = re.search(r"([\d.]+)\s*m", text)
    if m:
        return float(m.group(1))
    return None


def parse_floors(text):
    """階数を抽出する（例: '地上2階建' → 2, '3階建' → 3）"""
    if not text:
        return None
    m = re.search(r"(\d+)\s*階建", text)
    if m:
        return int(m.group(1))
    return None


def parse_age_years(age_text, category=None):
    """築年月テキストから築年数を計算する。新築の場合は0。"""
    if category == "新築":
        return 0.0
    if not age_text:
        return None
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})?", age_text)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 1
    now = datetime.now()
    diff = (now.year - year) + (now.month - month) / 12
    return round(max(diff, 0), 1)


def parse_walk_minutes(station_text, station_name=None):
    """沿線・駅テキストから指定駅の徒歩分数を抽出する"""
    if not station_text:
        return None
    if station_name:
        pattern = re.escape(station_name) + r".*?徒歩(\d+)分?[～~]?(\d+)?分?"
        m = re.search(pattern, station_text)
        if m:
            minutes = [int(m.group(1))]
            if m.group(2):
                minutes.append(int(m.group(2)))
            return max(minutes)
    # フォールバック: 最初に見つかる徒歩分数
    m = re.search(r"徒歩(\d+)", station_text)
    if m:
        return int(m.group(1))
    return None


def calc_tsubo_tanka(price_man, area_m2):
    """坪単価（万円/坪）を計算する"""
    if price_man and area_m2 and area_m2 > 0:
        tsubo = area_m2 / TSUBO_RATIO
        return round(price_man / tsubo, 1)
    return None


def verify_station(prop, station_name):
    """物件の沿線・駅テキストに指定駅名が含まれるか検証する。
    含まれていれば True、含まれていなければ False。"""
    station_text = prop.get("station", "")
    if not station_text or not station_name:
        return False
    # 「駒沢大学」「駒澤大学」のような表記揺れに対応
    # 基本は駅名がテキスト内に含まれるか
    if station_name in station_text:
        return True
    # 沢↔澤 の揺れ対応
    if "沢" in station_name:
        alt = station_name.replace("沢", "澤")
        if alt in station_text:
            return True
    if "澤" in station_name:
        alt = station_name.replace("澤", "沢")
        if alt in station_text:
            return True
    # 「ケ」「ヶ」「が」の揺れ対応
    for a, b in [("ケ", "ヶ"), ("ケ", "が"), ("ヶ", "が")]:
        if a in station_name:
            if station_name.replace(a, b) in station_text:
                return True
        if b in station_name:
            if station_name.replace(b, a) in station_text:
                return True
    return False


def scrape_page(session, base_url, page=1):
    """1ページ分のHTMLを取得する"""
    params = {"page": str(page)}
    resp = session.get(base_url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def parse_properties(html, category, station_name=None):
    """HTMLから物件情報をパースする"""
    soup = BeautifulSoup(html, "html.parser")
    properties = []

    units = soup.find_all("div", class_="property_unit")

    for unit in units:
        prop = extract_property_from_item(unit, station_name, category)
        prop["category"] = category
        if prop.get("price"):
            properties.append(prop)

    return properties


def extract_property_from_item(item, station_name=None, category=None):
    """property_unit ブロックから情報を抽出する"""
    prop = {}

    # 物件名とリンク
    title_tag = item.find("h2", class_="property_unit-title")
    if title_tag:
        a_tag = title_tag.find("a")
        if a_tag:
            prop["name"] = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://suumo.jp" + href
            prop["url"] = href

    # dl > dt/dd パターンで情報取得
    dts = item.find_all("dt")
    for dt in dts:
        label = dt.get_text(strip=True)
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(strip=True)

        if "販売価格" in label or "価格" in label:
            prop["price"] = parse_price(value)
            prop["price_text"] = value
        elif "所在地" in label:
            prop["address"] = value
        elif "土地面積" in label:
            prop["land_area"] = parse_area(value)
            prop["land_area_text"] = value
        elif "建物面積" in label:
            prop["building_area"] = parse_area(value)
            prop["building_area_text"] = value
        elif "間取り" in label:
            prop["layout"] = value
        elif "築年月" in label:
            prop["age"] = value
        elif "沿線" in label or "駅" in label:
            prop["station"] = value
        elif "建物構造" in label or "構造" in label:
            prop["floors"] = parse_floors(value)
            prop["structure"] = value

    # 階数が構造欄になければ、全テキストから探す
    if not prop.get("floors"):
        all_text = item.get_text()
        prop["floors"] = parse_floors(all_text)

    # 築年数を計算
    prop["age_years"] = parse_age_years(prop.get("age"), category)

    # 徒歩分数を解析
    prop["walk_minutes"] = parse_walk_minutes(prop.get("station"), station_name)

    # 坪単価計算（土地面積ベース）
    prop["tsubo_tanka"] = calc_tsubo_tanka(
        prop.get("price"), prop.get("land_area")
    )

    return prop


def get_total_pages(html):
    """総ページ数を取得する"""
    soup = BeautifulSoup(html, "html.parser")

    max_page = 1
    page_links = soup.select("a[href*='page=']")
    for link in page_links:
        href = link.get("href", "")
        m = re.search(r"page=(\d+)", href)
        if m:
            max_page = max(max_page, int(m.group(1)))

    if max_page == 1:
        page_links = soup.select("a[href*='pn=']")
        for link in page_links:
            href = link.get("href", "")
            m = re.search(r"pn=(\d+)", href)
            if m:
                max_page = max(max_page, int(m.group(1)))

    return max_page


def scrape_category(session, category, base_url, station_name=None):
    """1カテゴリ（新築/中古）の全ページを取得する"""
    all_properties = []

    print(f"【{category}】ページ1を取得中...")
    html = scrape_page(session, base_url, page=1)
    total_pages = get_total_pages(html)
    print(f"  総ページ数: {total_pages}")

    props = parse_properties(html, category, station_name)
    all_properties.extend(props)
    print(f"  → {len(props)}件取得")

    for page in range(2, total_pages + 1):
        time.sleep(3)
        print(f"【{category}】ページ{page}/{total_pages}を取得中...")
        html = scrape_page(session, base_url, page=page)
        props = parse_properties(html, category, station_name)
        all_properties.extend(props)
        print(f"  → {len(props)}件取得")

    return all_properties


def deduplicate(properties):
    """価格・土地面積・建物面積が同じ物件を重複とみなし、先に見つかった方を残す。"""
    seen = set()
    unique = []
    for p in properties:
        key = (p.get("price"), p.get("land_area"), p.get("building_area"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def scrape_all(station_code=None, station_name=None):
    """新築・中古の両方を全ページ取得し、重複排除・駅名検証・徒歩15分以内でフィルタする"""
    print(f"scrape_all を実行中: {station_name} ({station_code})")

    if station_code is None:
        station_code = "15340"  # デフォルト: 駒沢大学
    if station_name is None:
        for name, code in STATION_CODES.items():
            if code == station_code:
                station_name = name
                break

    urls = get_urls(station_code)
    session = requests.Session()
    all_properties = []

    for category, base_url in urls.items():
        props = scrape_category(session, category, base_url, station_name)
        all_properties.extend(props)
        if category != list(urls.keys())[-1]:
            time.sleep(3)

    # 重複排除
    before_dedup = len(all_properties)
    all_properties = deduplicate(all_properties)
    print(f"\n重複排除: {before_dedup}件 → {len(all_properties)}件")

    # 駅名検証: 物件の沿線・駅テキストに指定駅名が含まれるかチェック
    if station_name:
        verified = []
        rejected = 0
        for p in all_properties:
            if verify_station(p, station_name):
                verified.append(p)
            else:
                rejected += 1
                print(f"  [除外] 駅名不一致: {p.get('station', '?')} （物件: {p.get('name', '?')[:20]}）")
        if rejected:
            print(f"駅名検証: {rejected}件を除外")
        all_properties = verified

    # 徒歩15分以内でフィルタ
    filtered = [
        p for p in all_properties
        if p.get("walk_minutes") is not None and p["walk_minutes"] <= MAX_WALK_MINUTES
    ]

    print(f"{station_name or '指定駅'}徒歩{MAX_WALK_MINUTES}分以内: {len(filtered)}件")
    return filtered


if __name__ == "__main__":
    properties = scrape_all()
    for p in properties[:5]:
        print(p)
