from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, session
import requests
import gspread
import json
import os
import time
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta # timedelta は既にインポート済み

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Google Sheets 設定
SERVICE_ACCOUNT_FILE = "configGooglesheet.json"
SPREADSHEET_NAME = "AirtableTest129"
WORKSHEET_NAME = "wsTableCD"
PERSONID_WORKSHEET_NAME = "wsPersonID"
WORKPROCESS_WORKSHEET_NAME = "wsWorkProcess"

# Google Sheets API 認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
client = gspread.authorize(creds)

# ==== Airtable 設定 (送信先用)
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID_BookSKY")

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
    global PERSON_ID_DICT, PERSON_ID_LIST, last_personid_load_time
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(PERSONID_WORKSHEET_NAME)
        records = sheet.get_all_records()
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
    if time.time() - last_personid_load_time > CACHE_TTL:
        load_personid_data()
    return PERSON_ID_DICT, PERSON_ID_LIST

# ===== WorkCord/WorkName/BookName キャッシュ =====
workcord_dict = {}
last_workcord_load_time = 0

def load_workcord_data():
    global workcord_dict, last_workcord_load_time
    workcord_dict = {}
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records()
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
    if time.time() - last_workcord_load_time > CACHE_TTL:
        load_workcord_data()
    return workcord_dict

# ===== WorkProcess/UnitPrice データ (Google Sheets の wsWorkProcess から取得) =====
workprocess_list_cache = []
unitprice_dict_cache = {}
last_workprocess_load_time = 0

def load_workprocess_data():
    global workprocess_list_cache, unitprice_dict_cache, last_workprocess_load_time
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKPROCESS_WORKSHEET_NAME)
        records = sheet.get_all_records()
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
    if time.time() - last_workprocess_load_time > CACHE_TTL:
        load_workprocess_data()
    return workprocess_list_cache, unitprice_dict_cache

def get_workprocess_data():
    wp_list, up_dict = get_cached_workprocess_data()
    return wp_list, up_dict, None

# -------------------------------
# WorkCD に対応する WorkName/BookName の選択肢を取得する API
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

# ✅ 一覧のデータ取得 (指定された年月のデータを取得するように変更)
def get_selected_month_records(target_year, target_month): # 引数に target_year, target_month を追加
    """指定された年月のデータをAirtableから取得"""
    selected_personid = session.get("selected_personid")

    if not selected_personid:
        return []

    try:
        # Airtable APIはYEAR()とMONTH()関数を直接サポートしていない場合があるため、
        # IS_SAME()や、日付範囲でのフィルタリングがより確実です。
        # ここでは、指定された月の初日と最終日を計算して範囲指定します。
        first_day_str = f"{target_year}-{str(target_month).zfill(2)}-01"
        
        if target_month == 12:
            last_day_str = f"{target_year}-12-31"
        else:
            # 次の月の初日を取得し、そこから1日引くことで当月の最終日を得る
            next_month_first_day = date(target_year, target_month + 1, 1)
            last_day_of_month = next_month_first_day - timedelta(days=1)
            last_day_str = last_day_of_month.strftime("%Y-%m-%d")

        # AirtableのfilterByFormulaで日付範囲を指定
        # WorkDayフィールドが 'YYYY-MM-DD' 形式の文字列として保存されていることを前提とします。
        # AirtableのDate型フィールドであれば、IS_AFTER/IS_BEFORE が使えます。
        # formula = f"AND(IS_AFTER({{WorkDay}}, '{first_day_str}'), IS_BEFORE({{WorkDay}}, '{last_day_str}'))"
        # より正確には、月の初日と最終日を含むようにする
        formula = f"AND(IS_SAME({{WorkDay}}, '{first_day_str}', 'day'), OR(IS_BEFORE({{WorkDay}}, '{last_day_str}'), IS_SAME({{WorkDay}}, '{last_day_str}', 'day')))"
        # もしWorkDayがDate型なら、MONTH()とYEAR()が使えるかもしれません。
        # しかし、より安全なのは日付文字列としての比較か、日付範囲です。
        # ここでは、Airtableの関数に合わせたより汎用的なフィルタリングを試みます。
        # 簡単のため、YEAR()とMONTH()が使えると仮定した元のロジックに戻しつつ、引数を使用します。
        params = {"filterByFormula": f"AND(YEAR({{WorkDay}})={target_year}, MONTH({{WorkDay}})={target_month})"}

        table_name = f"TablePersonID_{selected_personid}"
        
        response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}", headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json().get("records", [])

        records = [
            {
                "id": record["id"],
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
        flash(f"⚠ Airtableからのデータ取得中にエラーが発生しました: {e}", "error")
        return []
    except Exception as e: # その他の予期せぬエラー
        print(f"❌ 予期せぬエラー (get_selected_month_records): {e}")
        flash("⚠ データ取得中に予期せぬエラーが発生しました。", "error")
        return []


# ✅ レコードの削除
@app.route("/delete_record/<record_id>", methods=["POST"])
def delete_record(record_id):
    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("❌ PersonIDが選択されていません。操作を続行できません。", "error")
        return redirect(url_for("index")) # または適切なエラーページへ

    table_name = f"TablePersonID_{selected_personid}"
    
    try:
        response = requests.delete(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}", headers=HEADERS)
        response.raise_for_status() # エラーがあれば例外を発生させる
        flash("✅ レコードを削除しました！", "success")
    except requests.RequestException as e:
        flash(f"❌ 削除に失敗しました: {e}", "error")
        print(f"❌ Airtable 削除エラー: {e}")

    # 削除後、現在の表示月にリダイレクトする
    # この時点での year, month を取得する方法が必要。
    # 簡単なのは、削除ボタンのフォームに hidden で year, month を含めるか、
    # referer を使う（ただし、常に安全とは限らない）。
    # ここでは、recordsのデフォルト表示に戻す。
    return redirect(url_for("records"))


# ✅ レコードの修正ページ
@app.route("/edit_record/<record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("❌ PersonIDが選択されていません。操作を続行できません。", "error")
        return redirect(url_for("index"))

    table_name = f"TablePersonID_{selected_personid}"

    if request.method == "POST":
        updated_data = {
            "fields": {
                "WorkDay": request.form.get("WorkDay"),
                "WorkOutput": int(request.form.get("WorkOutput", 0)),
            }
        }
        try:
            response = requests.patch(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}",
                                      headers=HEADERS, json=updated_data)
            response.raise_for_status()
            flash("✅ レコードを更新しました！", "success")
        except requests.RequestException as e:
            error_message = e.response.json() if e.response else str(e)
            flash(f"❌ 更新に失敗しました: {error_message}", "error")
            print(f"❌ Airtable 更新エラー: {error_message}")
        
        # 更新後、現在の表示月にリダイレクトしたいが、year/month情報が必要。
        # 簡単なのは、更新フォームにhiddenでyear/monthを持たせるか、
        # redirect(url_for("records")) でデフォルト表示に戻す。
        return redirect(url_for("records")) 

    try:
        response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}",
                                headers=HEADERS)
        response.raise_for_status()
        record_data = response.json().get("fields", {})
    except requests.RequestException as e:
        flash(f"❌ 編集対象レコードの取得に失敗しました: {e}", "error")
        return redirect(url_for("records"))
        
    return render_template("edit_record.html", record=record_data, record_id=record_id)


# 🆕 **一覧表示のルート (前月・次月機能対応)**
@app.route("/records")
@app.route("/records/<int:year>/<int:month>")
def records(year=None, month=None):
    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("👤 PersonIDを選択してください。", "info")
        return redirect(url_for("index"))

    # 表示する年月を決定
    if year is None or month is None:
        # URLに年月がない場合、セッションの作業日から年月を取得
        selected_workday_from_session = session.get("workday")
        if selected_workday_from_session:
            try:
                base_date = datetime.strptime(selected_workday_from_session, "%Y-%m-%d").date()
            except ValueError: # 不正な日付形式の場合
                base_date = date.today() - timedelta(days=30) # フォールバック
        else:
            # セッションにも作業日がない場合、約30日前の月をデフォルトとする
            base_date = date.today() - timedelta(days=30)
        year = base_date.year
        month = base_date.month
    else:
        # URLで年月が指定された場合
        try:
            # 指定された年月が妥当かチェックするためにdateオブジェクトを生成してみる
            date(year, month, 1)
        except ValueError:
            flash("⚠ 無効な年月が指定されました。デフォルトの月を表示します。", "warning")
            # 不正な場合はデフォルトのロジックに戻す
            selected_workday_from_session = session.get("workday")
            if selected_workday_from_session:
                base_date = datetime.strptime(selected_workday_from_session, "%Y-%m-%d").date()
            else:
                base_date = date.today() - timedelta(days=30)
            year = base_date.year
            month = base_date.month

    current_display_date = date(year, month, 1) # 表示月の1日
    display_month_str = f"{year}年{month}月"

    # Airtableからデータを取得
    records_data = get_selected_month_records(year, month)

    total_amount = 0
    for record in records_data:
        try:
            unit_price = float(record.get("UnitPrice", 0)) if record.get("UnitPrice", "不明") != "不明" else 0
            work_output = int(record.get("WorkOutput", 0))
            record["subtotal"] = unit_price * work_output
        except ValueError:
            record["subtotal"] = 0
        total_amount += record["subtotal"]

    unique_workdays = set(record["WorkDay"] for record in records_data)
    workdays_count = len(unique_workdays)
    
    workoutput_total = sum(
        float(record["WorkOutput"]) for record in records_data if "分給" in record.get("WorkProcess", "")
    )

    # 前月の計算
    first_day_of_current_month = date(year, month, 1)
    last_day_of_prev_month = first_day_of_current_month - timedelta(days=1)
    prev_year = last_day_of_prev_month.year
    prev_month = last_day_of_prev_month.month

    # 次月の計算
    # 現在の月の最終日を求め、それに1日足すと次月の初日になる
    if month == 12:
        first_day_of_next_month = date(year + 1, 1, 1)
    else:
        first_day_of_next_month = date(year, month + 1, 1)
    next_year = first_day_of_next_month.year
    next_month = first_day_of_next_month.month
    
    return render_template(
        "records.html",
        records=records_data,
        personid=selected_personid,
        display_month=display_month_str,
        total_amount=total_amount,
        workdays_count=workdays_count,
        workoutput_total=workoutput_total,
        current_year=year, # テンプレートで現在の年が必要な場合のため
        current_month=month, # テンプレートで現在の月が必要な場合のため
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month
    )


# -------------------------------
# Flask のルート
@app.route("/", methods=["GET", "POST"])
def index():
    get_cached_workcord_data()
    personid_dict, personid_list = get_cached_personid_data()
    workprocess_list, unitprice_dict, error = get_workprocess_data()
    if error:
        flash(error, "error")
        
    if request.method == "POST":
        selected_personid = request.form.get("personid", "").strip()
        workcd = request.form.get("workcd", "").strip()
        workoutput = request.form.get("workoutput", "").strip() or "0"
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()

        error_occurred = False
        if not selected_personid.isdigit() or int(selected_personid) not in personid_list:
            flash("⚠ 有効な PersonID を選択してください！", "error")
            error_occurred = True
        if not workcd.isdigit():
            flash("⚠ 品名コードは数値を入力してください！", "error")
            error_occurred = True
        try:
            workoutput_val = int(workoutput)
        except ValueError:
            flash("⚠ 数量は数値を入力してください！", "error")
            error_occurred = True
            workoutput_val = 0 # エラーでも処理継続のためデフォルト値
        if not workprocess or not workday:
            flash("⚠ 行程と作業日は入力してください！", "error")
            error_occurred = True
        
        selected_option = request.form.get("workname", "").strip()
        workname, bookname = "", ""
        if not selected_option and not error_occurred: # 他にエラーがなければチェック
            flash("⚠ 該当する WorkName の選択が必要です！", "error")
            error_occurred = True
        elif selected_option:
            try:
                workname, bookname = selected_option.split("||")
            except ValueError:
                flash("⚠ WorkName の選択値に不正な形式が含まれています。", "error")
                error_occurred = True
        
        if error_occurred:
            return render_template("index.html",
                                   personid_list=personid_list,
                                   personid_dict=personid_dict,
                                   selected_personid=selected_personid, # POSTされた値を維持
                                   workprocess_list=workprocess_list,
                                   workday=workday) # POSTされた値を維持

        dest_table = f"TablePersonID_{selected_personid}"
        dest_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{dest_table}"
        unitprice = unitprice_dict.get(workprocess, 0)
        status_code, response_text = send_record_to_destination(
            dest_url, workcd, workname, bookname, workoutput_val, workprocess, unitprice, workday
        )
        flash(response_text, "success" if status_code == 200 else "error")
        
        session['selected_personid'] = selected_personid
        session['workday'] = workday # 最後に送信成功した作業日を保存
        
        # 送信成功時は、その作業日が含まれる月のレコードページにリダイレクト
        if status_code == 200:
            try:
                workday_dt = datetime.strptime(workday, "%Y-%m-%d")
                return redirect(url_for("records", year=workday_dt.year, month=workday_dt.month))
            except ValueError:
                return redirect(url_for("records")) # 日付パース失敗時はデフォルトへ
        else: # 送信失敗時
             return redirect(url_for("index"))


    else: # GET request
        selected_personid_session = session.get('selected_personid', "")
        session_workday = session.get('workday')

        if session_workday:
            workday_default = session_workday
        else:
            workday_default = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

        return render_template("index.html",
                               workprocess_list=workprocess_list,
                               personid_list=personid_list,
                               personid_dict=personid_dict,
                               selected_personid=selected_personid_session,
                               workday=workday_default)


if __name__ == "__main__":
    from waitress import serve
    #ポート番号はRender環境変数でPORTが指定されていればそれを使う
    port = int(os.environ.get("PORT", 10000))
    #ローカルテスト用にhost='0.0.0.0'の代わりにhost='127.0.0.1'を使ってもよい
    serve(app, host="0.0.0.0", port=port)