from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, session
import requests
import gspread
import json
import os
import time
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta  # ← timedelta を追加


app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Google Sheets 設定
SERVICE_ACCOUNT_FILE = "configGooglesheet.json"  # Render の Secret File に保存済み

SPREADSHEET_NAME = "AirtableTest129"
WORKSHEET_NAME = "wsTableCD"         # WorkCord/WorkName/BookName を含むシート
PERSONID_WORKSHEET_NAME = "wsPersonID"  # PersonID/PersonName を含むシート
WORKPROCESS_WORKSHEET_NAME = "wsWorkProcess"  # WorkProcess/UnitPrice を含むシート

# Google Sheets API 認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
client = gspread.authorize(creds)

# ==== Airtable 設定 (送信先用)
with open("configAirtable.json", "r") as f:
    config = json.load(f)

AIRTABLE_TOKEN = config["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = config["AIRTABLE_BASE_ID"]

SOURCE_TABLE = "TableCD"
# ※ TableWorkProcess は今後使用しない

SOURCE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{SOURCE_TABLE}"
# WORK_PROCESS_URL は削除可能（送信先には影響なし）

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

CACHE_TTL = 300  # 300秒 (5分間)

# ===== PersonID データ (Google Sheets から取得) =====
PERSON_ID_DICT = {}
PERSON_ID_LIST = []
last_personid_load_time = 0

def load_personid_data():
    """Google Sheets の wsPersonID から PersonID/PersonName を読み込み、グローバル変数を更新"""
    global PERSON_ID_DICT, PERSON_ID_LIST, last_personid_load_time
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(PERSONID_WORKSHEET_NAME)
        records = sheet.get_all_records()  # ヘッダー: "PersonID", "PersonName"
        temp_dict = {}
        for row in records:
            pid = str(row.get("PersonID", "")).strip()
            pname = str(row.get("PersonName", "")).strip()
            if pid and pname:
                try:
                    pid_int = int(pid)
                    temp_dict[pid_int] = pname
                except ValueError:
                    continue
        PERSON_ID_DICT = temp_dict
        PERSON_ID_LIST = list(PERSON_ID_DICT.keys())
        last_personid_load_time = time.time()
        print(f"✅ Google Sheets から {len(PERSON_ID_DICT)} 件の PersonID/PersonName レコードをロードしました！")
    except Exception as e:
        print(f"⚠ Google Sheets の PersonID データ取得に失敗: {e}")

def get_cached_personid_data():
    """TTL内であればキャッシュ済みの PersonID データを返し、超えていれば再読み込みする"""
    if time.time() - last_personid_load_time > CACHE_TTL:
        load_personid_data()
    return PERSON_ID_DICT, PERSON_ID_LIST

# ===== WorkCord/WorkName/BookName キャッシュ =====
workcord_dict = {}
last_workcord_load_time = 0

def load_workcord_data():
    """Google Sheets の wsTableCD から WorkCord/WorkName/BookName を読み込み、グローバルキャッシュを更新"""
    global workcord_dict, last_workcord_load_time
    workcord_dict = {}  # キャッシュ初期化
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records()  # 各行は辞書
        for row in records:
            workcord = str(row.get("WorkCord", "")).strip()
            workname = str(row.get("WorkName", "")).strip()
            bookname = str(row.get("BookName", "")).strip()
            if workcord and workname:
                if workcord not in workcord_dict:
                    workcord_dict[workcord] = []
                workcord_dict[workcord].append({"workname": workname, "bookname": bookname})
        total_records = sum(len(lst) for lst in workcord_dict.values())
        print(f"✅ Google Sheets から {total_records} 件の WorkCD/WorkName/BookName レコードをロードしました！")
        last_workcord_load_time = time.time()
    except Exception as e:
        print(f"⚠ Google Sheets のデータ取得に失敗: {e}")

def get_cached_workcord_data():
    """TTL内ならキャッシュ済みのデータを利用、超えていれば再読み込み"""
    if time.time() - last_workcord_load_time > CACHE_TTL:
        load_workcord_data()
    return workcord_dict

# ===== WorkProcess/UnitPrice データ (Google Sheets の wsWorkProcess から取得) =====
workprocess_list_cache = []
unitprice_dict_cache = {}
last_workprocess_load_time = 0

def load_workprocess_data():
    """Google Sheets の wsWorkProcess から WorkProcess と UnitPrice を読み込み、キャッシュを更新"""
    global workprocess_list_cache, unitprice_dict_cache, last_workprocess_load_time
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKPROCESS_WORKSHEET_NAME)
        records = sheet.get_all_records()  # ヘッダー: "WorkProcess", "UnitPrice"
        temp_list = []
        temp_dict = {}
        for row in records:
            wp = str(row.get("WorkProcess", "")).strip()
            up = row.get("UnitPrice", 0)
            if wp:
                temp_list.append(wp)
                temp_dict[wp] = up
        workprocess_list_cache = temp_list
        unitprice_dict_cache = temp_dict
        last_workprocess_load_time = time.time()
        print(f"✅ Google Sheets から {len(temp_list)} 件の WorkProcess/UnitPrice レコードをロードしました！")
    except Exception as e:
        print(f"⚠ Google Sheets の wsWorkProcess データ取得に失敗: {e}")

def get_cached_workprocess_data():
    """TTL内であればキャッシュ済みの WorkProcess データを返し、超えていれば再読み込みする"""
    if time.time() - last_workprocess_load_time > CACHE_TTL:
        load_workprocess_data()
    return workprocess_list_cache, unitprice_dict_cache

def get_workprocess_data():
    """WorkProcess と UnitPrice のデータを返す"""
    wp_list, up_dict = get_cached_workprocess_data()
    return wp_list, up_dict, None

# -------------------------------
# WorkCD に対応する WorkName/BookName の選択肢を取得する API
# ※ JavaScript 側では "/get_worknames" エンドポイントを呼び出す
@app.route("/get_worknames", methods=["GET"])
def get_worknames():
    data = get_cached_workcord_data()
    workcd = request.args.get("workcd", "").strip()
    try:
        workcd_num = int(workcd)
        workcd_key = str(workcd_num)
    except ValueError:
        return jsonify({"worknames": [], "error": "⚠ WorkCD は数値で入力してください！"})
    records = data.get(workcd_key, [])
    return jsonify({"worknames": records, "error": ""})

# -------------------------------
# WorkProcess に対応する UnitPrice を取得する API
@app.route("/get_unitprice", methods=["GET"])
def get_unitprice():
    workprocess = request.args.get("workprocess", "").strip()
    if not workprocess:
        return jsonify({"error": "WorkProcess が指定されていません"}), 400
    wp_list, up_dict, error = get_workprocess_data()
    if error:
        print("⚠ wsWorkProcess データ取得エラー: ", error)
        return jsonify({"error": error}), 500
    if workprocess not in up_dict:
        print("⚠ 該当する WorkProcess が見つかりません")
        return jsonify({"error": "該当する WorkProcess が見つかりません"}), 404
    unitprice = up_dict[workprocess]
    print(f"✅ UnitPrice: {unitprice}")
    return jsonify({"unitprice": unitprice})

# -------------------------------
# Airtable へのデータ送信
def send_record_to_destination(dest_url, workcord, workname, bookname, workoutput, workprocess, unitprice, workday):
    data = {
        "fields": {
            "WorkCord": int(workcord),
            "WorkName": str(workname),
            "BookName": str(bookname),
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
# 🆕 **カレンダーで選択されている月のデータを取得**
# ✅ 一覧のデータ取得
def get_selected_month_records():
    """ユーザーがカレンダーで選択した月のデータを取得"""
    selected_personid = session.get("selected_personid")
    selected_workday = session.get("workday")

    if not selected_personid:
        return []

    try:
        selected_date = datetime.strptime(selected_workday, "%Y-%m-%d") if selected_workday else date.today()
        selected_year, selected_month = selected_date.year, selected_date.month

        params = {"filterByFormula": f"AND(YEAR({{WorkDay}})={selected_year}, MONTH({{WorkDay}})={selected_month})"}
        table_name = f"TablePersonID_{selected_personid}"
        
        response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}", headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json().get("records", [])

        records = [
            {
                "id": record["id"],  # ✅ レコードIDを取得
                "WorkDay": record["fields"].get("WorkDay", "9999-12-31"),
                "WorkCD": record["fields"].get("WorkCord", "不明"),
                "WorkName": record["fields"].get("WorkName", "不明"),
                "WorkProcess": record["fields"].get("WorkProcess", "不明"),
                "UnitPrice": record["fields"].get("UnitPrice", "不明"),
                "WorkOutput": record["fields"].get("WorkOutput", "0"),
            }
            for record in data
        ]

        records.sort(key=lambda x: x["WorkDay"])
        return records

    except requests.RequestException as e:
        print(f"❌ Airtable データ取得エラー: {e}")
        return []

# ✅ レコードの削除
@app.route("/delete_record/<record_id>", methods=["POST"])
def delete_record(record_id):
    selected_personid = session.get("selected_personid")
    table_name = f"TablePersonID_{selected_personid}"
    
    response = requests.delete(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}", headers=HEADERS)
    if response.status_code == 200:
        flash("✅ レコードを削除しました！", "success")
    else:
        flash("❌ 削除に失敗しました。", "error")

    return redirect(url_for("records"))

# ✅ レコードの修正ページ
@app.route("/edit_record/<record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    selected_personid = session.get("selected_personid")
    table_name = f"TablePersonID_{selected_personid}"

    if request.method == "POST":
        updated_data = {
            "fields": {
                "WorkDay": request.form.get("WorkDay"),
                "WorkOutput": int(request.form.get("WorkOutput", 0)),  # ✅ 数値変換
            }
        }

        # ✅ Airtable に PATCH リクエストを送信（WorkDay, WorkOutput のみ）
        response = requests.patch(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}",
                                  headers=HEADERS, json=updated_data)
        
        if response.status_code == 200:
            flash("✅ レコードを更新しました！", "success")
        else:
            error_message = response.json()
            flash(f"❌ 更新に失敗しました: {error_message}", "error")
            print(f"❌ Airtable 更新エラー: {error_message}")  # ログ出力

        return redirect(url_for("records"))

    # ✅ GETリクエスト時（編集フォームを開く）
    response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}",
                            headers=HEADERS)
    record_data = response.json().get("fields", {})

    return render_template("edit_record.html", record=record_data, record_id=record_id)



# 🆕 **一覧表示のルート**
@app.route("/records")
def records():
    records = get_selected_month_records()

    # ✅ 各行の小計 (WorkOutput * UnitPrice) を計算
    total_amount = 0
    for record in records:
        try:
            unit_price = float(record["UnitPrice"]) if record["UnitPrice"] != "不明" else 0
            work_output = int(record["WorkOutput"])
            record["subtotal"] = unit_price * work_output  # ✅ 小計を計算
        except ValueError:
            record["subtotal"] = 0  # 計算エラー時は 0 にする

        total_amount += record["subtotal"]  # ✅ 月合計を計算
    # ✅ 勤務日数を計算（ユニークな WorkDay の数）
    unique_workdays = set(record["WorkDay"] for record in records)
    workdays_count = len(unique_workdays)  # ✅ ユニークな日付の数 = 勤務日数
    # ✅ WorkProcess に "分給" が含まれるレコードのみ WorkOutput を合計
    workoutput_total = sum(
        float(record["WorkOutput"]) for record in records if "分給" in record["WorkProcess"]
    )
    selected_personid = session.get("selected_personid", "未選択")
    selected_workday = session.get("workday", date.today().strftime("%Y-%m-%d"))
    
    selected_date = datetime.strptime(selected_workday, "%Y-%m-%d")
    display_month = f"{selected_date.year}年{selected_date.month}月"

    return render_template(
        "records.html",
        records=records,
        personid=selected_personid,
        display_month=display_month,
        total_amount=total_amount,
        workdays_count=workdays_count,
        workoutput_total=workoutput_total,
    )


# -------------------------------
# Flask のルート
@app.route("/", methods=["GET", "POST"])
def index():
    # キャッシュを利用して最新データを取得（TTL内なら再読み込みは行われません）
    get_cached_workcord_data()
    personid_dict, personid_list = get_cached_personid_data()
    workprocess_list, unitprice_dict, error = get_workprocess_data()
    if error:
        flash(error, "error")
        
    if request.method == "POST":
        selected_personid = request.form.get("personid", "").strip()
        workcd = request.form.get("workcd", "").strip()
        workoutput = request.form.get("workoutput", "").strip()
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()

        # WorkOutput が空の場合は "0" を設定
        if workoutput == "":
            workoutput = "0"

        # 各入力のバリデーション（エラー時は入力内容を保持して再表示）
        if not selected_personid.isdigit() or int(selected_personid) not in personid_list:
            flash("⚠ 有効な PersonID を選択してください！", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid="",
                                   workprocess_list=workprocess_list,
                                   workday=workday)
        if not workcd.isdigit():
            flash("⚠ WorkCD は数値を入力してください！", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list,
                                   workday=workday)
        if not workoutput.isdigit():
            flash("⚠ WorkOutput は数値を入力してください！", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list,
                                   workday=workday)
        if not workprocess or not workday:
            flash("⚠ すべてのフィールドを入力してください！", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list,
                                   workday=workday)

        selected_option = request.form.get("workname", "").strip()
        if not selected_option:
            flash("⚠ 該当する WorkName の選択が必要です！", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list,
                                   workday=workday)
        try:
            workname, bookname = selected_option.split("||")
        except ValueError:
            flash("⚠ WorkName の選択値に不正な形式が含まれています。", "error")
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list,
                                   workday=workday)

        dest_table = f"TablePersonID_{selected_personid}"
        dest_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{dest_table}"
        unitprice = unitprice_dict.get(workprocess, 0)
        status_code, response_text = send_record_to_destination(
            dest_url, workcd, workname, bookname, workoutput, workprocess, unitprice, workday
        )
        flash(response_text, "success" if status_code == 200 else "error")
        # セッションに前回入力された PersonID と作業日を保存
        session['selected_personid'] = selected_personid
        session['workday'] = workday
        return redirect(url_for("index"))
    else:
        # GET時は、セッションに保存された値を利用（なければ空文字）
        selected_personid = session.get('selected_personid', "")
        workday = session.get('workday', "")
    return render_template("index.html",
                           workprocess_list=workprocess_list,
                           personid_list=personid_list,
                           personid_dict=personid_dict,
                           selected_personid=selected_personid,
                           workday=workday)

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
