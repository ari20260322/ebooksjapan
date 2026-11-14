import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SUBJECT = os.environ.get("SUBJECT")
TARGET_URL = os.environ.get("TARGET_URL")
REPO = "ari20260322/ebooksjapan"
HISTORY_FILE = "history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def scrape_books(start_url):
    books = []
    url = start_url
    visited_pages = set()

    while url and url not in visited_pages:
        visited_pages.add(url)
        print(f"Scraping page: {url}")
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # 【重要】ebooksjapanの実際のHTML構造に合わせてセレクタを変更してください
        # 以下のCSSセレクタは一般的な構造を想定した仮置きのものです
        items = soup.select(".book-item") # 本1冊分のブロック要素
        
        for item in items:
            title_tag = item.select_one(".title a") # タイトルのリンク要素
            img_tag = item.select_one("img")        # 画像要素

            if title_tag and img_tag:
                title = title_tag.text.strip()
                book_url = urljoin(start_url, title_tag.get("href", ""))
                img_url = img_tag.get("src", "")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                books.append({
                    "title": title,
                    "url": book_url,
                    "img": img_url
                })

        # 複数ページ（ページネーション）の処理
        next_page = soup.select_one(".next-page a") # 「次へ」ボタンの要素
        if next_page and next_page.get("href"):
            url = urljoin(start_url, next_page.get("href"))
        else:
            url = None

    return books

def main():
    history = load_history()
    all_books = scrape_books(TARGET_URL)

    new_books = []
    for book in all_books:
        # URLを識別子として履歴に存在しない場合のみ新規扱い
        if book["url"] not in history:
            new_books.append(book)
            history.append(book["url"])

    if not new_books:
        print("新刊はありませんでした。")
        return

    # Issueの本文を作成（添付画像のイメージに基づくMarkdown構成）
    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
        # 横幅を指定して画像を小さめに表示
        body_lines.append(f'<img src="{book["img"]}" width="200">')
        body_lines.append("") # 空行

    body_lines.append("\n@ari20260322")
    issue_body = "\n".join(body_lines)

    # GitHub Issueの作成
    api_url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": SUBJECT,
        "body": issue_body
    }
    
    res = requests.post(api_url, headers=headers, json=data)
    res.raise_for_status()
    print(f"Issue Created: {res.json().get('html_url')}")

    # 履歴を更新して保存（Actionsでコミットされる）
    save_history(history)

if __name__ == "__main__":
    if TARGET_URL:
        main()
    else:
        print("No TARGET_URL provided.")
