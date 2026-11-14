import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SUBJECT = os.environ.get("SUBJECT")
TARGET_URL = os.environ.get("TARGET_URL")
REPO = "ari20260322/ebooksjapan"

# 件名から記号を除外して安全なファイル名を作る（例: history_漫画雑誌.json）
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

        # ebookjapanの書籍リスト要素（正常に動いていた既存のセレクタ）
        items = soup.select(".book-item")
        
        if not items:
            break
            
        for item in items:
            link_tag = item.select_one("a")
            title_tag = item.select_one(".title")
            img_tag = item.select_one("img")

            if link_tag and img_tag:
                title = title_tag.text.strip() if title_tag else img_tag.get("alt", "No Title")
                book_url = urljoin(base_url, link_tag.get("href", ""))
                
                img_url = ""
                # 本命の画像URLが隠されている属性を優先順位をつけて探す
                for attr in ["data-original", "data-src", "srcset", "src"]:
                    val = img_tag.get(attr)
                    # "data:image" から始まるダミー画像を除外
                    if val and not val.startswith("data:image"):
                        img_url = val.split(" ")[0] # 不要なスペースを取り除く
                        break

                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                books.append({
                    "title": title,
                    "url": book_url,
                    "img": img_url
                })
        
        current_page += 1

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

    # コメント本文を作成
    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
        # 画像URLが取得できている場合のみ表示する
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
