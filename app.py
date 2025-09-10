###################################################################
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import base64
import os
import logging
from flask import Flask, request, abort
###################################################################

# ログ設定
logging.basicConfig(level=logging.INFO)

##### 勤怠管理用コード ###############################################################

# RenderやFly.ioの環境変数から復元（安全な一時ファイルに保存）
json_str = base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]).decode("utf-8")
tmp_path = "/tmp/credentials.json"
with open(tmp_path, "w") as f:
    f.write(json_str)

# 認証スコープ
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 認証情報の読み込み
creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_path, scope)
client = gspread.authorize(creds)

# スプレッドシートとシートに接続
sheet = client.open("勤怠管理").worksheet("勤怠")

# 出勤打刻
def record_clock_in(name):
    try:
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        sheet.append_row([now.split()[0], name, now.split()[1], "", "", "出勤"])
    except Exception as e:
        logging.error(f"出勤記録失敗: {e}")

# 退勤打刻（最後の出勤行を更新）
def record_clock_out(name):
    try:
        records = sheet.get_all_records()
        for i in reversed(range(len(records))):
            if records[i]["名前"] == name and records[i]["退勤時間"] == "":
                row_index = i + 2  # ヘッダー分オフセット
                now = datetime.now().strftime("%H:%M")
                sheet.update_cell(row_index, 4, now)
                sheet.update_cell(row_index, 6, "退勤")
                break
    except Exception as e:
        logging.error(f"退勤記録失敗: {e}")

# 勤務時間集計
def get_work_summary(name):
    try:
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
    except Exception as e:
        logging.error(f"勤務時間集計失敗: {e}")
        return "集計中にエラーが発生しました。"

###################################################################

# 環境変数から認証情報を取得
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

# メッセージイベントの処理（内容に応じて分岐）
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # LINEユーザー名取得（失敗時はIDで代用）
    try:
        profile = line_bot_api.get_profile(event.source.user_id)
        name = profile.display_name
    except Exception:
        name = event.source.user_id

    # 🔽 この「メッセージ内容に応じた処理」の if 文の中に追加！
    if user_text == "出勤":
    record_clock_in(name)
    reply_text = "出勤を記録しました！"
elif user_text == "退勤":
    record_clock_out(name)
    reply_text = "退勤を記録しました！"
elif user_text == "集計":
    reply_text = get_work_summary(name)
elif user_text == "シフト確認":
    reply_text = get_shift_schedule(name)
elif user_text.startswith("休暇申請"):
    reply_text = record_vacation_request(name, user_text)
elif user_text == "メニュー":
    buttons_template = TemplateSendMessage(
        alt_text="勤怠メニュー",
        template=ButtonsTemplate(
            title="勤怠メニュー",
            text="操作を選んでください",
            actions=[
                PostbackAction(label="出勤", data="action=clock_in"),
                PostbackAction(label="退勤", data="action=clock_out"),
                PostbackAction(label="集計", data="action=summary"),
                PostbackAction(label="休暇申請", data="action=vacation"),
                PostbackAction(label="シフト確認", data="action=shift")
            ]
        )
    )
    line_bot_api.reply_message(event.reply_token, buttons_template)
    return
else:
    reply_text = f"「{user_text}」ですね！了解です🦊"

    # 通常のテキスト返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def get_shift_schedule(name):
    try:
        shift_sheet = client.open("勤怠管理").worksheet("シフト")
        records = shift_sheet.get_all_records()
        today = datetime.now()
        this_week = [today.strftime("%Y/%m/%d")]
        for i in range(1, 7):
            day = today.replace(day=today.day + i)
            this_week.append(day.strftime("%Y/%m/%d"))

        shifts = []
        for row in records:
            if row["名前"] == name and row["日付"] in this_week:
                shifts.append(f"{row['日付']}: {row['開始時間']}〜{row['終了時間']}")

        if shifts:
            return "\n".join(shifts)
        else:
            return "今週のシフトは登録されていません。"
    except Exception as e:
        logging.error(f"シフト取得失敗: {e}")
        return "シフト確認中にエラーが発生しました。"

from linebot.models import PostbackEvent

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data

    try:
        profile = line_bot_api.get_profile(event.source.user_id)
        name = profile.display_name
    except Exception:
        name = event.source.user_id

    if data == "action=clock_in":
        record_clock_in(name)
        reply_text = "出勤を記録しました！"
    elif data == "action=clock_out":
        record_clock_out(name)
        reply_text = "退勤を記録しました！"
    elif data == "action=summary":
        reply_text = get_work_summary(name)
    elif data == "action=vacation":
        reply_text = "休暇申請は「休暇申請 有休 2025/09/15 理由」の形式で送ってください🌿"
    elif data == "action=shift":
        reply_text = get_shift_schedule(name)
    else:
        reply_text = "未対応の操作です"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def record_vacation_request(name, text):
    try:
        parts = text.split()
        if len(parts) < 4:
            return "申請形式が正しくありません。例：休暇申請 有休 2025/09/15 理由"

        kind = parts[1]
        date = parts[2]
        reason = " ".join(parts[3:])
        vacation_sheet = client.open("勤怠管理").worksheet("休暇申請")
        vacation_sheet.append_row([date, name, kind, reason, "申請中"])

        # 管理者通知
        admin_id = os.environ.get("LINE_ADMIN_USER_ID")
        if admin_id:
            notify_text = f"{name}さんが{date}に{kind}申請しました。\n理由：{reason}"
            line_bot_api.push_message(admin_id, TextSendMessage(text=notify_text))

        return f"{date}の{kind}申請を受け付けました！"
    except Exception as e:
        logging.error(f"休暇申請失敗: {e}")
        return "申請中にエラーが発生しました。"
        
def approve_vacation(date, name):
    try:
        vacation_sheet = client.open("勤怠管理").worksheet("休暇申請")
        records = vacation_sheet.get_all_records()
        for i, row in enumerate(records):
            if row["日付"] == date and row["名前"] == name:
                row_index = i + 2  # ヘッダー分
                vacation_sheet.update_cell(row_index, 5, "承認済")
                return f"{date}の{name}さんの申請を承認しました！"
        return "該当する申請が見つかりませんでした。"
    except Exception as e:
        logging.error(f"承認処理失敗: {e}")
        return "承認中にエラーが発生しました。"

# ローカル実行（Fly.ioやRenderでもPORT環境変数を使用）
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
