import os
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SUBJECT = os.environ.get("SUBJECT")
TARGET_URL = os.environ.get("TARGET_URL")
REPO = "ari20260322/ebooksjapan"

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

def extract_real_image_url(item, base_url):
    """HTML文字列から指定の画像CDNドメインを直接ぶっこ抜く"""
    item_html = str(item)
    
    # 1. ユーザーから提示されたebookjapanのCDNドメインを直接正規表現で読み取る
    cdn_match = re.search(r'(https://cache\d*-ebookjapan\.akamaized\.net/[^"\'\s<>]+)', item_html)
    if cdn_match:
        # HTMLエンティティ（&amp;など）を元に戻して返す
        return cdn_match.group(1).replace('&amp;', '&')

    # 2. 見つからなかった場合の予備手段（汎用的な画像URL抽出）
    for tag in item.find_all(["img", "source"]):
        for attr in ["data-original", "data-src", "srcset", "src"]:
            val = tag.get(attr)
            if val:
                urls = [u.strip().split(" ")[0] for u in val.split(",") if u.strip()]
                for u in urls:
                    if not u.startswith("data:image") and not u.endswith(".gif") and "noimage" not in u.lower():
                        if u.startswith("//"):
                            return "https:" + u
                        elif u.startswith("http"):
                            return u
    return ""

def scrape_books(base_url):
    books = []
    current_page = 1
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    while True:
        parsed_url = urlparse(base_url)
        query = parse_qs(parsed_url.query)
        query['page'] = [str(current_page)]
        new_query = urlencode(query, doseq=True)
        page_url = urlunparse(parsed_url._replace(query=new_query))
        
        print(f"Scraping page {current_page}: {page_url}")
        res = requests.get(page_url, headers=headers)
        
        if res.status_code != 200:
            break

        soup = BeautifulSoup(res.text, "html.parser")

        # 本のリスト要素を取得
        items = soup.select(".book-item")
        if not items:
            items = soup.select("li.item, div.item, .list-item")
            if not items:
                items = [a.parent for a in soup.find_all("a") if a.find("img")]
                
        if not items:
            break
            
        for item in items:
            link_tag = item.select_one("a")
            if not link_tag:
                continue

            # タイトルの取得
            title_tag = item.select_one(".title, .name, .book-title, h2, h3")
            
            # 画像リンクを直接読み取り
            img_url = extract_real_image_url(item, base_url)

            title = ""
            if title_tag:
                title = title_tag.text.strip()
            elif item.find("img") and item.find("img").get("alt"):
                title = item.find("img").get("alt").strip()
            else:
                title = link_tag.text.strip()
                
            if not title:
                title = "タイトル不明"

            book_url = urljoin(base_url, link_tag.get("href", ""))

            books.append({
                "title": title,
                "url": book_url,
                "img": img_url
            })
        
        current_page += 1
        if current_page > 20:
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
        if book["url"] not in history:
            new_books.append(book)
            history.append(book["url"])

    if not new_books:
        print("新刊はありませんでした。")
        save_history(history)
        return

    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
        
        # 取得できた画像URLをそのまま挿入
        if book.get("img"):
            body_lines.append(f'<img src="{book["img"]}" width="200">')
        
        body_lines.append("")

    body_lines.append("\n@ari20260322")
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
