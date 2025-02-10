from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import requests
import gspread
import json
import os
import time
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ **Google Sheets 設定**
SERVICE_ACCOUNT_FILE = "configGooglesheet.json"  # Render の Secret File に保存済み
SPREADSHEET_NAME = "AirtableTest129"
WORKSHEET_NAME = "wsTableCD"

# **Google Sheets API 認証**
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
client = gspread.authorize(creds)

# ==== Airtable 設定 ====
with open("configAirtable.json", "r") as f:
    config = json.load(f)

AIRTABLE_TOKEN = config["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = config["AIRTABLE_BASE_ID"]

TABLE_WORK_PROCESS = "TableWorkProcess"
WORK_PROCESS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_WORK_PROCESS}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# PersonID に対応する名前を辞書で管理
PERSON_ID_DICT = {
    15: "Aさん",
    18: "Bさん",
    93: "竹ノ内さん",
    36: "Dさん",
    108: "Eさん"
}
PERSON_ID_LIST = list(PERSON_ID_DICT.keys())

# **キャッシュ用の辞書と最終更新時刻**
workcord_dict = {}
last_load_time = 0
CACHE_TTL = 300  # 5分間キャッシュを利用（秒）

def load_workcord_data():
    """Google Sheets から WorkCord, BookName, WorkName を取得し、辞書に格納"""
    global workcord_dict, last_load_time
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records()
        new_dict = {}

        for row in records:
            workcord = str(row.get("WorkCord"))
            workname = row.get("WorkName")

            if workcord and workname:
                if workcord not in new_dict:
                    new_dict[workcord] = []
                if workname not in new_dict[workcord]:  # 重複回避
                    new_dict[workcord].append(workname)

        workcord_dict = new_dict
        last_load_time = time.time()
        print(f"✅ Google Sheets から {len(workcord_dict)} 件の WorkCord をロードしました！")

    except Exception as e:
        print(f"⚠ Google Sheets のデータ取得に失敗: {e}")

def get_cached_workcord_data():
    """キャッシュされたデータを返す。TTLを超えていたら再読み込みする。"""
    global last_load_time
    if time.time() - last_load_time > CACHE_TTL:
        load_workcord_data()
    return workcord_dict

# **アプリ起動時に初回データをロード**
load_workcord_data()

# -------------------------------
# ✅ **WorkCD に対応する WorkName を取得する API**
@app.route("/get_worknames", methods=["GET"])
def get_worknames():
    workcd = request.args.get("workcd", "").strip()
    if not workcd.isdigit():
        return jsonify({"worknames": []})
    cached_data = get_cached_workcord_data()
    worknames = cached_data.get(workcd, [])
    return jsonify({"worknames": worknames})

# -------------------------------
# **Flask のルート**
@app.route("/", methods=["GET", "POST"])
def index():
    # キャッシュは get_cached_workcord_data() 内で自動更新されるため、
    # 毎回 load_workcord_data() を呼ぶ必要はありません。
    get_cached_workcord_data()

    selected_personid = request.form.get("personid", "15")

    if request.method == "POST":
        workcd = request.form.get("workcd", "").strip()
        workname = request.form.get("workname", "").strip()
        workoutput = request.form.get("workoutput", "").strip()
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()

        if not selected_personid.isdigit() or int(selected_personid) not in PERSON_ID_LIST:
            flash("⚠ 有効な PersonID を選択してください！", "error")
            return redirect(url_for("index"))

        if not workcd.isdigit():
            flash("⚠ WorkCD は数値を入力してください！", "error")
            return redirect(url_for("index"))

        if not workoutput.isdigit():
            flash("⚠ WorkOutput は数値を入力してください！", "error")
            return redirect(url_for("index"))

        if not workprocess or not workday or not workname:
            flash("⚠ すべてのフィールドを入力してください！", "error")
            return redirect(url_for("index"))

        # ここに POST 処理の続き（例：Airtable への送信等）を記述可能
        flash("✅ 入力内容を受け付けました！", "success")
        return redirect(url_for("index"))

    return render_template("index.html", personid_list=PERSON_ID_LIST, personid_dict=PERSON_ID_DICT, selected_personid=selected_personid)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
