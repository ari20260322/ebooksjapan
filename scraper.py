import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
SUBJECT = os.environ.get("SUBJECT")
TARGET_URL = os.environ.get("TARGET_URL")
REPO = "ari20260322/ebooksjapan"
HISTORY_FILE = "history.json"

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
    
    # 連続アクセスでブロックされないようブラウザと同じ情報を付与
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    while True:
        # 指定されたURLにページ番号パラメータ（page=1, 2, 3...）を結合して複数ページに対応
        parsed_url = urlparse(base_url)
        query = parse_qs(parsed_url.query)
        query['page'] = [str(current_page)]
        new_query = urlencode(query, doseq=True)
        page_url = urlunparse(parsed_url._replace(query=new_query))
        
        print(f"Scraping page {current_page}: {page_url}")
        res = requests.get(page_url, headers=headers)
        
        # エラーが出た場合やページが存在しない場合はループ終了
        if res.status_code != 200:
            break

        soup = BeautifulSoup(res.text, "html.parser")

        # ==========================================
        # 【重要】ebookjapanのHTML構造に合わせたCSSセレクタ
        # ※ブラウザの「検証(F12)」で実際のクラス名を確認して書き換えてください。
        # 以下は一般的な書籍リスト要素の仮名です。
        # ==========================================
        items = soup.select(".book-item") # 本1冊を囲む大枠のタグ
        
        # ページ内に本が1冊も無くなったら最後のページとみなして終了
        if not items:
            break
            
        for item in items:
            link_tag = item.select_one("a")      # リンクタグ
            title_tag = item.select_one(".title") # タイトル名が入っているタグ
            img_tag = item.select_one("img")      # 画像タグ

            if link_tag and img_tag:
                # タイトルタグが取れなければ画像のalt属性で代用
                title = title_tag.text.strip() if title_tag else img_tag.get("alt", "No Title")
                book_url = urljoin(base_url, link_tag.get("href", ""))
                
                # 画像の遅延読み込み(Lazy Load)に対応するため data-src も確認
                img_url = img_tag.get("src", "")
                if not img_url or "data:image" in img_url:
                    img_url = img_tag.get("data-src", img_url)

                if img_url and img_url.startswith("//"):
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
        # 履歴ファイルが存在しない初期エラーを防ぐため保存処理を通す
        save_history(history)
        return

    # コメント本文を作成
    body_lines = []
    for i, book in enumerate(new_books, 1):
        body_lines.append(f"{i}. [{book['title']}]({book['url']})")
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
