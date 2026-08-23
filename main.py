name: Check BTC Sentiment

on:
  schedule:
    - cron: '0 * * * *'  # اجرا سر هر ساعت
  workflow_dispatch:      # امکان اجرای دستی

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run script
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py

      - name: Commit & Push state file
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add last_sentiment.json || true
          git commit -m "Update sentiment state" || true
          git push || true
