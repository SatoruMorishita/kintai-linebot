###################################################################
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import base64
import os
from flask import Flask, request, abort
####################################################################
#####勤怠管理用コード###############################################################
# Renderの環境変数から復元
json_str = base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]).decode("utf-8")
with open("credentials.json", "w") as f:
    f.write(json_str)
    
#勤怠管理用
# 認証スコープ
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 認証情報の読み込み（JSONファイルは.gitignore推奨）
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# スプレッドシートとシートに接続
sheet = client.open("勤怠管理").worksheet("勤怠")

# 出勤打刻
def record_clock_in(name):
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    sheet.append_row([now.split()[0], name, now.split()[1], "", "", "出勤"])

# 退勤打刻（最後の出勤行を更新）
def record_clock_out(name):
    records = sheet.get_all_records()
    for i in reversed(range(len(records))):
        if records[i]["名前"] == name and records[i]["退勤時間"] == "":
            row_index = i + 2  # ヘッダー分オフセット
            now = datetime.now().strftime("%H:%M")
            sheet.update_cell(row_index, 4, now)
            sheet.update_cell(row_index, 6, "退勤")
            break

def get_work_summary(name):
    records = sheet.get_all_records()
    total_minutes = 0
    for row in records:
        if row["名前"] == name and row["出勤時間"] and row["退勤時間"]:
            in_time = datetime.strptime(row["出勤時間"], "%H:%M")
            out_time = datetime.strptime(row["退勤時間"], "%H:%M")
            total_minutes += int((out_time - in_time).total_seconds() / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{name}さんの今月の勤務時間は {hours}時間{minutes}分 です"
    #################################################
#@app.route("/line_webhook", methods=["POST"])
#def line_webhook():
    # LINEからのイベント処理
 #   return "OK"
    #################################################
# 環境変数から認証情報を取得（Renderで設定）
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# LINE APIインスタンス化
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Flaskアプリ初期化
app = Flask(__name__)

# Webhook受信エンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# メッセージイベントの処理（オウム返し）
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    reply_text = f"「{event.message.text}」ですね！了解です🦊"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# ローカル実行
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))  # Renderが自動でPORTを渡してくる
    app.run(host="0.0.0.0", port=port)
#####################################################################
