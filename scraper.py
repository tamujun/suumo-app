import re
import time
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/"

# 駒澤大学駅周辺（世田谷区）の戸建て売買物件
PARAMS = {
    "ar": "030",        # 関東
    "bs": "021",        # 一戸建て
    "ta": "13",         # 東京都
    "sc": "13112",      # 世田谷区
    "kb": "1",          # 価格下限
    "kt": "9999999",    # 価格上限
    "mb": "0",          # 面積下限
    "mt": "9999999",    # 面積上限
    "ekTjCd": "",
    "ekTjNm": "",
    "tj": "0",
    "cnb": "0",
    "cn": "9999999",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

TSUBO_RATIO = 3.30578  # 1坪 = 3.30578 m²


def parse_price(text):
    """価格文字列から万円単位の数値を抽出する"""
    text = text.strip().replace(",", "").replace("，", "")
    # 「x億xxxx万円」パターン（先にチェック）
    m = re.search(r"(\d+)\s*億\s*(\d*)\s*万円", text)
    if m:
        oku = int(m.group(1))
        man = int(m.group(2)) if m.group(2) else 0
        return oku * 10000 + man
    # 「xxxx万円」パターン
    m = re.search(r"(\d+)\s*万円", text)
    if m:
        return int(m.group(1))
    # 「x億円」パターン（万円なし）
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


def calc_tsubo_tanka(price_man, area_m2):
    """坪単価（万円/坪）を計算する"""
    if price_man and area_m2 and area_m2 > 0:
        tsubo = area_m2 / TSUBO_RATIO
        return round(price_man / tsubo, 1)
    return None


def scrape_page(session, page=1):
    """1ページ分の物件情報を取得する"""
    params = {**PARAMS, "pn": str(page)}
    resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def parse_properties(html):
    """HTMLから物件情報をパースする"""
    soup = BeautifulSoup(html, "html.parser")
    properties = []

    container = soup.find(id="js-bukkenList")
    if not container:
        return properties

    # div.property_unit が各物件ブロック
    items = container.find_all("div", class_="property_unit")

    for item in items:
        prop = extract_property_from_item(item)
        if prop and prop.get("price"):
            properties.append(prop)

    return properties


def extract_property_from_item(item):
    """property_unit ブロックから情報を抽出する"""
    prop = {}

    # 物件名とリンク（h2.property_unit-title 内の a タグ）
    title_tag = item.find("h2", class_="property_unit-title")
    if title_tag:
        a_tag = title_tag.find("a")
        if a_tag:
            prop["name"] = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://suumo.jp" + href
            prop["url"] = href

    # dottable 内の dl > dt/dd パターンで情報取得
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

    # 坪単価計算（土地面積ベース）
    prop["tsubo_tanka"] = calc_tsubo_tanka(
        prop.get("price"), prop.get("land_area")
    )

    return prop


def get_total_pages(html):
    """総ページ数を取得する"""
    soup = BeautifulSoup(html, "html.parser")

    # ページネーションリンクから最大ページ数を取得
    page_links = soup.select("a[href*='pn=']")
    max_page = 1
    for link in page_links:
        href = link.get("href", "")
        m = re.search(r"pn=(\d+)", href)
        if m:
            max_page = max(max_page, int(m.group(1)))

    # ページネーションのテキストからも試行
    if max_page == 1:
        pagination = soup.find_all("a")
        for a in pagination:
            text = a.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))

    return max_page


def scrape_all(max_pages=3):
    """全ページの物件情報を取得する（デフォルトは最大3ページ）"""
    session = requests.Session()
    all_properties = []

    # 1ページ目を取得してページ数を確認
    print("ページ1を取得中...")
    html = scrape_page(session, page=1)
    total_pages = get_total_pages(html)
    pages_to_fetch = min(total_pages, max_pages)
    print(f"総ページ数: {total_pages}, 取得ページ数: {pages_to_fetch}")

    props = parse_properties(html)
    all_properties.extend(props)
    print(f"  → {len(props)}件取得")

    # 2ページ目以降
    for page in range(2, pages_to_fetch + 1):
        time.sleep(3)  # マナー遵守
        print(f"ページ{page}を取得中...")
        html = scrape_page(session, page=page)
        props = parse_properties(html)
        all_properties.extend(props)
        print(f"  → {len(props)}件取得")

    print(f"\n合計: {len(all_properties)}件")
    return all_properties


if __name__ == "__main__":
    properties = scrape_all(max_pages=2)
    for p in properties[:5]:
        print(p)
