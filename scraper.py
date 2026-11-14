import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SUBJECT = os.environ.get("SUBJECT")
TARGET_URL = os.environ.get("TARGET_URL")
REPO = "ari20260322/ebooksjapan"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.8",
}

# 商品ページURLの形式: /books/数字/A数字/
BOOK_LINK_PATTERN = re.compile(r"/books/\d+/A\d+/")

safe_subject = "".join([c if c.isalnum() else "_" for c in SUBJECT]) if SUBJECT else "default"
HISTORY_FILE = f"history_{safe_subject}.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def normalize_url(u):
    u = u.strip().replace("\\/", "/").replace("&amp;", "&")
    if u.startswith("//"):
        return "https:" + u
    return u

def extract_real_image_url(item):
    """一覧ページ側のHTMLから画像URLを探す（og:imageが取れなかった時の予備）"""
    html_str = str(item)

    cdn_matches = re.findall(r'(?:https?:)?//[a-zA-Z0-9.-]+\.akamaized\.net/[^"\'\s<>]+', html_str)
    for match in cdn_matches:
        clean_url = normalize_url(match)
        if "noimage" not in clean_url.lower() and not clean_url.endswith(".gif"):
            return clean_url

    for tag in item.find_all(["img", "source"]):
        for attr in ["src", "data-src", "data-original", "data-lazy-src", "lazy-src", "srcset", "data-srcset"]:
            val = tag.get(attr)
            if not val:
                continue
            u = str(val).split(",")[0].split(" ")[0].strip()
            if not u or u.startswith("data:image") or u.lower().endswith(".gif"):
                continue
            if "noimage" in u.lower():
                continue
            u = normalize_url(u)
            if u.startswith("http"):
                return u
    return ""

def fetch_og_image(book_url):
    """商品ページの og:image から画像URLを取得"""
    try:
        res = requests.get(book_url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, "html.parser")
        for prop in ("og:image", "twitter:image"):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return normalize_url(tag["content"])
    except requests.RequestException:
        pass
    return ""

def find_book_container(a_tag, book_url, base_url):
    """このリンクが属する「1冊分のブロック」を親方向にたどって探す"""
    container = a_tag
    for _ in range(5):
        parent = container.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        urls = {
            urljoin(base_url, x["href"])
            for x in parent.find_all("a", href=BOOK_LINK_PATTERN)
        }
        if urls - {book_url}:
            break
        container = parent
    return container

def scrape_books(base_url):
    books = []
    seen_urls = set()
    current_page = 1

    while True:
        parsed_url = urlparse(base_url)
        query = parse_qs(parsed_url.query)
        query['page'] = [str(current_page)]
        new_query = urlencode(query, doseq=True)
        page_url = urlunparse(parsed_url._replace(query=new_query))

        print(f"Scraping page {current_page}: {page_url}")
        res = requests.get(page_url, headers=HEADERS)

        if res.status_code != 200:
            break

        soup = BeautifulSoup(res.text, "html.parser")

        # 商品リンクをURLごとにまとめる
        page_items = {}
        for a in soup.find_all("a", href=BOOK_LINK_PATTERN):
            book_url = urljoin(base_url, a["href"])
            if book_url in seen_urls:
                continue
            entry = page_items.setdefault(book_url, {"anchors": [], "title": ""})
            entry["anchors"].append(a)
            if not entry["title"]:
                text = a.get_text(" ", strip=True)
                if text:
                    entry["title"] = text

        if not page_items:
            break

        for book_url, entry in page_items.items():
            container = find_book_container(entry["anchors"][0], book_url, base_url)

            title = entry["title"]
            if not title:
                img = container.find("img")
                if img and img.get("alt"):
                    title = img["alt"].strip()
            if not title:
                title = "タイトル不明"

            books.append({
                "title": title,
                "url": book_url,
                "img": extract_real_image_url(container)
            })
            seen_urls.add(book_url)

        current_page += 1
        if current_page > 20: # 暴走防止
            break

    return books

def get_or_create_issue():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    issues = res.json()
    
    for issue in issues:
        if issue.get("title") == SUBJECT:
            return issue.get("number")
            
    create_url = f"https://api.github.com/repos/{REPO}/issues"
    data = {"title": SUBJECT, "body": f"{SUBJECT} の新刊通知用イシューです。"}
    res = requests.post(create_url, headers=headers, json=data)
    res.raise_for_status()
    return res.json().get("number")

def main():
    history = load_history()
    all_books = scrape_books(TARGET_URL)

    new_books = []
    for book in all_books:
        # URLをベースに重複チェック
        if book["url"] not in history:
            new_books.append(book)
            history.append(book["url"])

    if not new_books:
        print("新刊はありませんでした。")
        save_history(history)
        return

    # 商品ページの og:image を優先、取れなければ一覧ページの画像を使う
    for book in new_books:
        og = fetch_og_image(book["url"])
        if og:
            book["img"] = og
        time.sleep(1)

    # コメント作成（Markdownフォーマット）
    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
        
        if book.get("img"):
            # 画像タグを直接挿入
            body_lines.append(f'<img src="{book["img"]}" width="200">')
        else:
            # 抽出失敗の確認用（デバッグ）
            body_lines.append("*(画像URL取得失敗)*")
            
        body_lines.append("") # 空行

    body_lines.append(f"\n@ari20260322")
    comment_body = "\n".join(body_lines)

    issue_number = get_or_create_issue()
    comment_url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    res = requests.post(comment_url, headers=headers, json={"body": comment_body})
    res.raise_for_status()
    print(f"Comment Added to Issue #{issue_number}: {res.json().get('html_url')}")

    save_history(history)

if __name__ == "__main__":
    if TARGET_URL:
        main()
    else:
        print("No TARGET_URL provided.")
