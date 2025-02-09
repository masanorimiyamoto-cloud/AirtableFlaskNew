from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import requests
import gspread
import json
import os
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ **Google Sheets 設定**
SERVICE_ACCOUNT_FILE = "configGooglesheet.json"  # Render の Secret File に保存済み
#SERVICE_ACCOUNT_FILE = r"C:\Users\user\OneDrive\SKY\pythonproject2025130\avid-keel-449310-n4-371c2abfe6fc.json"
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

SOURCE_TABLE = "TableCD"
TABLE_WORK_PROCESS = "TableWorkProcess"

SOURCE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{SOURCE_TABLE}"
WORK_PROCESS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_WORK_PROCESS}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# PersonID に対応する名前を辞書で管理
PERSON_ID_DICT = {
    15: "Aさん",
    18: "Bさん",
    24: "Cさん",
    36: "Dさん",
    108: "Eさん"
}

# ID のリスト（選択用）
PERSON_ID_LIST = list(PERSON_ID_DICT.keys())


# **キャッシュ用の辞書**
workcord_dict = {}

def load_workcord_data():
    global workcord_dict
    workcord_dict = {}  # 初期化

    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

        # **すべてのデータを取得（辞書形式）**
        records = sheet.get_all_records()

        # **辞書にデータを格納**
        for row in records:
            workcord = str(row.get("WorkCord"))  # WorkCD を文字列に変換
            workname = row.get("WorkName")  # WorkName
            if workcord and workname:
                workcord_dict[workcord] = workname

        print(f"✅ Google Sheets から {len(workcord_dict)} 件の WorkCD をロードしました！")

    except Exception as e:
        print(f"⚠ Google Sheets のデータ取得に失敗: {e}")


# **アプリ起動時にデータをロード**
load_workcord_data()

# -------------------------------
# ✅ **WorkCD に対応する WorkName を取得する API**
@app.route("/get_workname", methods=["GET"])
def get_workname():
    workcd = request.args.get("workcd", "").strip()
    if not workcd.isdigit():
        return jsonify({"workname": "", "error": "⚠ WorkCD は数値で入力してください！"})

    # **辞書から即時取得**
    workname = workcord_dict.get(workcd)
    if not workname:
        return jsonify({"workname": "", "error": ""})  # **メッセージを非表示に**

    return jsonify({"workname": workname, "error": ""})


# -------------------------------
# **TableWorkProcess のデータを取得**
def get_workprocess_data():
    """Airtable の TableWorkProcess から WorkProcess と UnitPrice のデータを取得"""
    try:
        response = requests.get(WORK_PROCESS_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        records = data.get("records", [])

        workprocess_list = []
        unitprice_dict = {}

        for record in records:
            fields = record.get("fields", {})
            workprocess = fields.get("WorkProcess")
            unitprice = fields.get("UnitPrice", 0)
            if workprocess:
                workprocess_list.append(workprocess)
                unitprice_dict[workprocess] = unitprice

        return workprocess_list, unitprice_dict, None
    except requests.RequestException as e:
        return [], {}, f"⚠ データ取得エラー: {str(e)}"

# -------------------------------
# WorkProcess に対応する UnitPrice を取得する API
@app.route("/get_unitprice", methods=["GET"])
def get_unitprice():
    workprocess = request.args.get("workprocess", "").strip()
    if not workprocess:
        return jsonify({"error": "WorkProcess が指定されていません"}), 400

    #print(f"🔍 WorkProcess 取得リクエスト: {workprocess}")  # デバッグログ

    params = {"filterByFormula": f"{{WorkProcess}}='{workprocess}'"}
    response = requests.get(WORK_PROCESS_URL, headers=HEADERS, params=params)

    if response.status_code != 200:
        print(f"⚠ エラー: {response.status_code}, {response.text}")  # デバッグ
        return jsonify({"error": "データ取得エラー"}), 500

    data = response.json()
    records = data.get("records", [])
    
    if not records:
        print("⚠ 該当する WorkProcess が見つかりません")  # デバッグ
        return jsonify({"error": "該当する WorkProcess が見つかりません"}), 404

    unitprice = records[0]["fields"].get("UnitPrice", "不明")
    print(f"✅ UnitPrice: {unitprice}")  # デバッグ
    return jsonify({"unitprice": unitprice})

# **Airtable へのデータ送信**
def send_record_to_destination(dest_url, workcord, workname, workoutput, workprocess, unitprice, workday):
    data = {
        "fields": {
            "WorkCord": int(workcord),
            "WorkName": str(workname),
            "WorkOutput": int(workoutput),
            "WorkProcess": str(workprocess),
            "UnitPrice": float(unitprice),
            "WorkDay": workday
        }
    }
    try:
        response = requests.post(dest_url, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        return response.status_code, "✅ Airtable にデータを送信しました！"
    except requests.RequestException as e:
        return None, f"⚠ 送信エラー: {str(e)}"

# -------------------------------
# **Flask のルート**
@app.route("/", methods=["GET", "POST"])

def index():
    workprocess_list, unitprice_dict, error = get_workprocess_data()
    if error:
        flash(error, "error")

    selected_personid = request.form.get("personid", "15")

    if request.method == "POST":
        workcd = request.form.get("workcd", "").strip()
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

        if not workprocess or not workday:
            flash("⚠ すべてのフィールドを入力してください！", "error")
            return redirect(url_for("index"))

        dest_table = f"TablePersonID_{selected_personid}"
        dest_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{dest_table}"

        workname = workcord_dict.get(workcd)
        if not workname:
            flash(f"⚠ WorkCD {workcd} のデータが見つかりません。", "error")
            return redirect(url_for("index"))

        unitprice = unitprice_dict.get(workprocess, 0)
        status_code, response_text = send_record_to_destination(dest_url, workcd, workname, workoutput, workprocess, unitprice, workday)

        flash(response_text, "success" if status_code == 200 else "error")
        return redirect(url_for("index"))

    return render_template("index.html",
                           workprocess_list=workprocess_list,
                           personid_list=PERSON_ID_LIST,
                           personid_dict=PERSON_ID_DICT,  # PersonID の辞書を追加
                           selected_personid=selected_personid)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
