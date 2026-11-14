name: Ebooksjapan Scraper

on:
  repository_dispatch:
    types: [scrape_trigger]

permissions:
  contents: write
  issues: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run scraper
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SUBJECT: ${{ github.event.client_payload.subject }}
          TARGET_URL: ${{ github.event.client_payload.url }}
        run: python scraper.py

      - name: Commit and push history
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add history.json
          # 変更がある場合のみコミットしてプッシュ
          git diff --quiet && git diff --staged --quiet || (git commit -m "Update scraping history" && git push)
