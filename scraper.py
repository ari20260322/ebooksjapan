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

def extract_real_image_url(item):
    """HTMLテキスト全体からebookjapanのCDN画像URLを問答無用で引っこ抜く"""
    html_str = str(item)
    
    # 1. akamaized.net を含むURLを正規表現で全検索（http始まり、//始まり両対応）
    cdn_matches = re.findall(r'(?:https?:)?//[a-zA-Z0-9-]+\.akamaized\.net/[^"\'\s<>]+', html_str)
    if cdn_matches:
        for match in cdn_matches:
            # エスケープ文字などを掃除
            clean_url = match.replace('\\/', '/').replace('&amp;', '&')
            if clean_url.startswith('//'):
                clean_url = 'https:' + clean_url
            
            # 透過ダミー画像は除外して最初の本物URLを返す
            if "noimage" not in clean_url.lower() and not clean_url.endswith(".gif"):
                return clean_url

    # 2. タグの属性を全探索（JSON等で埋め込まれている場合）
    for tag in item.find_all(True):
        for attr, value in tag.attrs.items():
            if isinstance(value, list):
                value = " ".join(value)
            if isinstance(value, str) and "akamaized.net" in value:
                if value.startswith("//"):
                    return "https:" + value
                elif value.startswith("http"):
                    return value

    # 3. 最終手段：imgタグのありとあらゆる属性をチェック
    for tag in item.find_all(["img", "source"]):
        for attr in ["src", "data-src", "data-original", "srcset", "lazy-src"]:
            val = tag.get(attr)
            if val:
                u = str(val).split(" ")[0].strip()
                if not u.startswith("data:image") and not u.endswith(".gif"):
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

        # 本の要素ブロックを広く取得
        items = soup.select(".book-item, li.item, div.item, .list-item")
        if not items:
            items = [a.parent for a in soup.find_all("a") if a.find("img")]
                
        if not items:
            break
            
        for item in items:
            link_tag = item.find("a")
            if not link_tag:
                continue

            # ① タイトル引っこ抜き
            title_tag = item.select_one(".title, .name, .book-title, h2, h3")
            if title_tag:
                title = title_tag.text.strip()
            elif item.find("img") and item.find("img").get("alt"):
                title = item.find("img").get("alt").strip()
            else:
                title = link_tag.text.strip()
            
            if not title:
                title = "タイトル不明"

            # ② 商品URL引っこ抜き
            book_url = urljoin(base_url, link_tag.get("href", ""))

            # ③ 画像URL引っこ抜き
            img_url = extract_real_image_url(item)

            books.append({
                "title": title,
                "url": book_url,
                "img": img_url
            })
        
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
