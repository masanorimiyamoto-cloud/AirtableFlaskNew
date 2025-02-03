from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
import requests
import datetime
import json
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ==== Airtable 設定 ====
with open("configAirtable.json", "r") as f:
    config = json.load(f)

AIRTABLE_TOKEN = config["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = config["AIRTABLE_BASE_ID"]

SOURCE_TABLE = "TableCD"
DEST_TABLE = "TableTest2025201"
TABLE_WORK_PROCESS = "TableWorkProcess"

SOURCE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{SOURCE_TABLE}"
DEST_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{DEST_TABLE}"
WORK_PROCESS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_WORK_PROCESS}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------------
# **WorkCD に対応する WorkName を取得する API**
@app.route("/get_workname", methods=["GET"])
def get_workname():
    workcd = request.args.get("workcd", "").strip()
    if not workcd.isdigit():
        return jsonify({"workname": "", "error": "⚠ WorkCD は数値で入力してください！"})

    workname, error = get_workname_by_workcd(workcd)
    if error:
        return jsonify({"workname": "", "error": error})

    return jsonify({"workname": workname, "error": ""})

# -------------------------------
# **WorkCD に対応する WorkName を取得**
def get_workname_by_workcd(workcd):
    params = {"filterByFormula": f"{{WorkCord}}={workcd}"}
    try:
        response = requests.get(SOURCE_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        records = data.get("records", [])
        if not records:
            return None, f"⚠ WorkCD {workcd} のデータが見つかりません。"
        return records[0]["fields"].get("WorkName"), None
    except requests.RequestException as e:
        return None, f"⚠ データ取得エラー: {str(e)}"
# -------------------------------
# **TableWorkProcess のデータを取得**
def get_workprocess_data():
    """Airtable の TableWorkProcess から WorkProcess と UnitPrice のデータを取得"""
    TABLE_WORK_PROCESS = "TableWorkProcess"
    WORK_PROCESS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_WORK_PROCESS}"
    
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
# **Airtable へのデータ送信**
def send_record_to_destination(workcord, workname, workoutput, workprocess, unitprice, workday):
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
        response = requests.post(DEST_URL, headers=HEADERS, json=data, timeout=10)
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

    if request.method == "POST":
        workcd = request.form.get("workcd", "").strip()
        workoutput = request.form.get("workoutput", "").strip()
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()

        if not workcd.isdigit():
            flash("⚠ WorkCD は数値を入力してください！", "error")
            return redirect(url_for("index"))

        if not workoutput.isdigit():
            flash("⚠ WorkOutput は数値を入力してください！", "error")
            return redirect(url_for("index"))

        if not workprocess or not workday:
            flash("⚠ すべてのフィールドを入力してください！", "error")
            return redirect(url_for("index"))

        workname, error = get_workname_by_workcd(workcd)
        if error:
            flash(error, "error")
            return redirect(url_for("index"))

        unitprice = unitprice_dict.get(workprocess, 0)
        status_code, response_text = send_record_to_destination(workcd, workname, workoutput, workprocess, unitprice, workday)

        flash(response_text, "success" if status_code == 200 else "error")
        return redirect(url_for("index"))  # ✅ ページをリロードしてフォームをリセット

    return render_template("index.html", workprocess_list=workprocess_list)


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render は PORT を自動設定
    app.run(host="0.0.0.0", port=port, debug=True)
