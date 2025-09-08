# ベースイメージ
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 必要ファイルのコピー
COPY . /app

# 依存パッケージのインストール
RUN pip install --no-cache-dir -r requirements.txt

# ポート指定（Fly.ioが環境変数PORTを渡してくる）
ENV PORT=8080

# アプリ起動
CMD ["python", "app.py"]
