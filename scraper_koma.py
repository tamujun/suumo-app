import re
import time
import requests
from bs4 import BeautifulSoup


# 駒澤大学駅 (ek_15340) の戸建て検索URL
URLS = {
    "新築": "https://suumo.jp/ikkodate/tokyo/ek_15340/",
    "中古": "https://suumo.jp/chukoikkodate/tokyo/ek_15340/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

TSUBO_RATIO = 3.30578  # 1坪 = 3.30578 m²
MAX_WALK_MINUTES = 15   # 徒歩15分以内


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


def parse_walk_minutes(station_text):
    """沿線・駅テキストから駒澤大学駅の徒歩分数を抽出する"""
    if not station_text:
        return None
    # 「徒歩X分～Y分」パターン（大きい方を採用）
    m = re.search(r"駒[沢澤]大学.*?徒歩(\d+)分[～~](\d+)分", station_text)
    if m:
        return max(int(m.group(1)), int(m.group(2)))
    # 「駒沢大学」「駒澤大学」両方に対応
    m = re.search(r"駒[沢澤]大学.*?徒歩(\d+)", station_text)
    if m:
        return int(m.group(1))
    return None


def calc_tsubo_tanka(price_man, area_m2):
    """坪単価（万円/坪）を計算する"""
    if price_man and area_m2 and area_m2 > 0:
        tsubo = area_m2 / TSUBO_RATIO
        return round(price_man / tsubo, 1)
    return None


def scrape_page(session, base_url, page=1):
    """1ページ分のHTMLを取得する"""
    params = {"page": str(page)}
    resp = session.get(base_url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def parse_properties(html, category):
    """HTMLから物件情報をパースする"""
    soup = BeautifulSoup(html, "html.parser")
    properties = []

    units = soup.find_all("div", class_="property_unit")

    for unit in units:
        prop = extract_property_from_item(unit)
        prop["category"] = category
        if prop.get("price"):
            properties.append(prop)

    return properties


def extract_property_from_item(item):
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

    # 徒歩分数を解析
    prop["walk_minutes"] = parse_walk_minutes(prop.get("station"))

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


def scrape_category(session, category, base_url):
    """1カテゴリ（新築/中古）の全ページを取得する"""
    all_properties = []

    print(f"【{category}】ページ1を取得中...")
    html = scrape_page(session, base_url, page=1)
    total_pages = get_total_pages(html)
    print(f"  総ページ数: {total_pages}")

    props = parse_properties(html, category)
    all_properties.extend(props)
    print(f"  → {len(props)}件取得")

    for page in range(2, total_pages + 1):
        time.sleep(3)
        print(f"【{category}】ページ{page}/{total_pages}を取得中...")
        html = scrape_page(session, base_url, page=page)
        props = parse_properties(html, category)
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


def scrape_all():
    """新築・中古の両方を全ページ取得し、重複排除・徒歩15分以内でフィルタする"""
    session = requests.Session()
    all_properties = []

    for category, base_url in URLS.items():
        props = scrape_category(session, category, base_url)
        all_properties.extend(props)
        if category != list(URLS.keys())[-1]:
            time.sleep(3)

    # 重複排除
    before_dedup = len(all_properties)
    all_properties = deduplicate(all_properties)
    print(f"\n重複排除: {before_dedup}件 → {len(all_properties)}件")

    # 駒澤大学駅 徒歩15分以内でフィルタ
    filtered = [
        p for p in all_properties
        if p.get("walk_minutes") is not None and p["walk_minutes"] <= MAX_WALK_MINUTES
    ]

    print(f"駒澤大学駅徒歩{MAX_WALK_MINUTES}分以内: {len(filtered)}件")
    return filtered


if __name__ == "__main__":
    properties = scrape_all()
    for p in properties[:5]:
        print(p)
