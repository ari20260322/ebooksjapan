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

        # ※対象サイトの実際のHTMLに合わせて要変更
        items = soup.select(".book-item")
        
        for item in items:
            title_tag = item.select_one(".title a")
            img_tag = item.select_one("img")

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

        next_page = soup.select_one(".next-page a")
        if next_page and next_page.get("href"):
            url = urljoin(start_url, next_page.get("href"))
        else:
            url = None

    return books

def get_or_create_issue():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. オープンなIssue一覧を取得し、A列の件名と同じIssueがあるか探す
    url = f"https://api.github.com/repos/{REPO}/issues?state=open"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    issues = res.json()
    
    for issue in issues:
        if issue.get("title") == SUBJECT:
            return issue.get("number") # 既存のIssue番号を返す
            
    # 2. なければ最初の1回目として新規作成する
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
        return

    # コメント本文を作成
    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
        body_lines.append(f'<img src="{book["img"]}" width="200">')
        body_lines.append("")

    body_lines.append("\n@ari20260322")
    comment_body = "\n".join(body_lines)

    # Issue番号を取得して、コメント（追記）として送信する
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
