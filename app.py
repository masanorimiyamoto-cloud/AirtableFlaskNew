from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, session
import requests
import gspread
import json
import os
import time
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta

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
        PERSON_ID_LIST = list(PERSON_ID_DICT.keys()) # PersonIDのリストを保持
        last_personid_load_time = time.time()
        print(f"✅ Google Sheets から {len(PERSON_ID_DICT)} 件の PersonID/PersonName レコードをロードしました！")
    except Exception as e:
        print(f"⚠ Google Sheets の PersonID データ取得に失敗: {e}")

def get_cached_personid_data():
    if time.time() - last_personid_load_time > CACHE_TTL or not PERSON_ID_DICT: # 初回ロードも考慮
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
        resp_json = response.json()
        new_id = resp_json.get("id") 
        return response.status_code, "✅ Airtable にデータを送信しました！", new_id
    except requests.RequestException as e:
        return None, f"⚠ 送信エラー: {str(e)}", None


# ✅ 一覧のデータ取得 (指定された年月のデータを取得するように変更)
# この関数は元の状態（安定版20250515）です
def get_selected_month_records(target_year, target_month):
    selected_personid = session.get("selected_personid")

    if not selected_personid:
        return []

    try:
        # 年月でのフィルタリング
        # 元のコードでは YEAR() と MONTH() を使用
        params = {"filterByFormula": f"AND(YEAR({{WorkDay}})={target_year}, MONTH({{WorkDay}})={target_month})"}
        
        table_name = f"TablePersonID_{selected_personid}"
        
        response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}", headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json().get("records", [])

        records_list = [ # 変数名を records から records_list に変更 (records ルートと区別のため)
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
        records_list.sort(key=lambda x: x["WorkDay"]) # 元のコードのソート順
        return records_list

    except requests.RequestException as e:
        print(f"❌ Airtable データ取得エラー: {e}")
        flash(f"⚠ Airtableからのデータ取得中にエラーが発生しました: {e}", "error")
        return []
    except Exception as e: 
        print(f"❌ 予期せぬエラー (get_selected_month_records): {e}")
        flash("⚠ データ取得中に予期せぬエラーが発生しました。", "error")
        return []


# ✅ レコードの削除
@app.route("/delete_record/<record_id>", methods=["POST"])
def delete_record(record_id):
    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("❌ PersonIDが選択されていません。操作を続行できません。", "error")
        return redirect(url_for("index")) 

    table_name = f"TablePersonID_{selected_personid}"
    
    try:
        response = requests.delete(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}", headers=HEADERS)
        response.raise_for_status() 
        flash("✅ レコードを削除しました！", "success")
    except requests.RequestException as e:
        flash(f"❌ 削除に失敗しました: {e}", "error")
        print(f"❌ Airtable 削除エラー: {e}")

    # 削除後、最後に表示していた月、またはデフォルトの月にリダイレクト
    # records ルートがよしなに処理してくれることを期待
    return redirect(url_for("records"))


# ✅ レコードの修正ページ
@app.route("/edit_record/<record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("❌ PersonIDが選択されていません。操作を続行できません。", "error")
        return redirect(url_for("index"))

    table_name = f"TablePersonID_{selected_personid}"
    
    # GETリクエスト時に、戻り先となる年/月をURLパラメータから取得する試み
    # edit_record.html側でこの情報をフォームにhiddenで含め、POST時に送り返してもらう想定
    original_year = request.args.get('year', session.get('current_display_year'))
    original_month = request.args.get('month', session.get('current_display_month'))


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
        
        # 更新後、どの月の表示に戻るか
        # フォームから送り返された original_year/month または更新後のWorkDayの年月を使用
        redirect_year_str = request.form.get("original_year", original_year)
        redirect_month_str = request.form.get("original_month", original_month)
        
        updated_workday_str = request.form.get("WorkDay")
        if updated_workday_str:
            try:
                updated_workday_dt = datetime.strptime(updated_workday_str, "%Y-%m-%d")
                redirect_year_str = str(updated_workday_dt.year)
                redirect_month_str = str(updated_workday_dt.month)
            except ValueError:
                pass # 不正な日付なら元の月情報を使う

        if redirect_year_str and redirect_month_str:
            try:
                return redirect(url_for("records", year=int(redirect_year_str), month=int(redirect_month_str)))
            except ValueError:
                pass # int変換失敗時
        return redirect(url_for("records")) # デフォルト表示に戻す

    # GETリクエスト (編集対象レコード取得)
    try:
        response = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}",
                                headers=HEADERS)
        response.raise_for_status()
        record_data = response.json().get("fields", {})
        if not record_data:
             flash(f"❌ 編集対象のレコード (ID: {record_id}) が見つかりません。", "error")
             return redirect(url_for("records", year=original_year, month=original_month) if original_year and original_month else url_for("records"))
    except requests.RequestException as e:
        flash(f"❌ 編集対象レコードの取得に失敗しました: {e}", "error")
        return redirect(url_for("records", year=original_year, month=original_month) if original_year and original_month else url_for("records"))
        
    return render_template("edit_record.html", record=record_data, record_id=record_id,
                           original_year=original_year, original_month=original_month)


# 🆕 **一覧表示のルート (前月・次月機能対応)**
@app.route("/records")
@app.route("/records/<int:year>/<int:month>")
def records(year=None, month=None):
    # === PersonIDの処理: URLパラメータからの取得を試み、セッションに保存 ===
    personid_from_param = request.args.get("personid")
    if personid_from_param:
        # PersonIDが有効かチェック (PERSON_ID_LISTがロードされている前提)
        _, personid_list_for_check = get_cached_personid_data() 
        try:
            if int(personid_from_param) in personid_list_for_check:
                session['selected_personid'] = personid_from_param
            else:
                flash("⚠ 無効なPersonIDが指定されました。", "warning")
                # 不正なIDの場合はindexに戻すか、エラー処理
                return redirect(url_for("index")) 
        except ValueError:
            flash("⚠ PersonIDの形式が無効です。", "warning")
            return redirect(url_for("index"))

        # クエリパラメータを削除してリダイレクト (URLをクリーンに保つ)
        # 元のURLに年月情報があればそれを引き継ぐ
        redirect_url = url_for('records', year=year, month=month) if year is not None and month is not None else url_for('records')
        return redirect(redirect_url)
    # === PersonIDの処理ここまで ===

    selected_personid = session.get("selected_personid")
    if not selected_personid:
        flash("👤 PersonIDを選択してください。", "info")
        return redirect(url_for("index"))

    # 表示する年月を決定
    if year is None or month is None:
        selected_workday_from_session = session.get("workday")
        if selected_workday_from_session:
            try:
                base_date = datetime.strptime(selected_workday_from_session, "%Y-%m-%d").date()
            except ValueError: 
                base_date = date.today() - timedelta(days=30) 
        else:
            base_date = date.today() - timedelta(days=30)
        year = base_date.year
        month = base_date.month
    else:
        try:
            date(year, month, 1) # 有効な年月かチェック
        except ValueError:
            flash("⚠ 無効な年月が指定されました。デフォルトの月を表示します。", "warning")
            selected_workday_from_session = session.get("workday")
            if selected_workday_from_session:
                try:
                    base_date = datetime.strptime(selected_workday_from_session, "%Y-%m-%d").date()
                except ValueError:
                    base_date = date.today() - timedelta(days=30)
            else:
                base_date = date.today() - timedelta(days=30)
            year = base_date.year
            month = base_date.month
    
    session['current_display_year'] = year
    session['current_display_month'] = month

    display_month_str = f"{year}年{month}月"
    records_data = get_selected_month_records(year, month)

    total_amount = 0
    for record_item in records_data: # recordだと関数の引数と被る可能性があるので変更
        try:
            unit_price = float(record_item.get("UnitPrice", 0)) if record_item.get("UnitPrice", "不明") != "不明" else 0
            work_output = int(record_item.get("WorkOutput", 0))
            record_item["subtotal"] = unit_price * work_output
        except ValueError:
            record_item["subtotal"] = 0
        total_amount += record_item["subtotal"]

    unique_workdays = set(r["WorkDay"] for r in records_data)
    workdays_count = len(unique_workdays)
    
    # workoutput_total の計算を修正
    workoutput_total = 0
    for r_item in records_data: # ループ変数を r から r_item に変更し、より明確に
        # "分給" を含む WorkProcess のみを対象
        if "分給" in r_item.get("WorkProcess", ""):
            work_output_value = r_item.get("WorkOutput", "0") # デフォルト値は文字列 "0"
            
            # WorkOutput を安全に文字列に変換し、前後の空白を除去
            work_output_str = str(work_output_value).strip() 

            # 文字列が空でなく、かつ数値（整数または正の小数）として解釈可能かチェック
            # replace('.', '', 1) は最初の'.'を削除し、残りが全て数字か確認
            # これにより "10", "10.5" はOK, ".5" や "10." もOKになる
            # "" や "abc", "10.5.5" はNG
            if work_output_str and work_output_str.replace('.', '', 1).isdigit():
                try:
                    workoutput_total += float(work_output_str)
                except ValueError:
                    # isdigitチェックを通過してもfloat変換に失敗するケースは稀だが念のため
                    print(f"警告: WorkOutput '{work_output_str}' をfloatに変換できませんでした（isdigitチェック後）。")
            elif work_output_str: # isdigitチェックでFalseだったが空文字列ではない場合（例: "abc", "-" を含むなど）
                 print(f"情報: WorkOutput '{work_output_str}' は '分給' の集計対象外の形式です。")


    first_day_of_current_month = date(year, month, 1)
    last_day_of_prev_month = first_day_of_current_month - timedelta(days=1)
    prev_year = last_day_of_prev_month.year
    prev_month = last_day_of_prev_month.month

    if month == 12:
        first_day_of_next_month = date(year + 1, 1, 1)
    else:
        first_day_of_next_month = date(year, month + 1, 1)
    next_year = first_day_of_next_month.year
    next_month = first_day_of_next_month.month
    
    new_record_id = session.pop('new_record_id', None)
    return render_template(
        "records.html",
        records=records_data,
        personid=selected_personid,
        personid_dict=get_cached_personid_data()[0], # ヘッダー等でPersonName表示に使うため
        display_month=display_month_str,
        total_amount=total_amount,
        workdays_count=workdays_count,
        workoutput_total=workoutput_total,
        current_year=year, 
        current_month=month, 
        new_record_id=new_record_id,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month
    )


# -------------------------------
# Flask のルート
@app.route("/", methods=["GET", "POST"])
def index():
    # --- データ読み込み (GET/POST共通) ---
    get_cached_workcord_data() # WorkCordデータロード
    personid_dict_data, personid_list_data = get_cached_personid_data() # PersonIDデータロード
    workprocess_list_data, unitprice_dict_data, error_wp = get_workprocess_data() # WorkProcessデータロード
    if error_wp:
        flash(error_wp, "error")

    if request.method == "POST":
        selected_personid = request.form.get("personid", "").strip()
        workcd = request.form.get("workcd", "").strip()
        workoutput = request.form.get("workoutput", "").strip() or "0"
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()
        selected_option = request.form.get("workname", "").strip()

        workname, bookname = "", ""
        workoutput_val = 0
        error_occurred = False

        if not selected_personid.isdigit() or int(selected_personid) not in personid_list_data:
            flash("⚠ 有効な PersonID を選択してください！", "error")
            error_occurred = True
        
        if workcd and not workcd.isdigit(): # WorkCDは入力されていれば数値かチェック
            flash("⚠ WorkCD は数値で入力してください！", "error")
            error_occurred = True
            
        try:
            workoutput_val = int(workoutput)
        except ValueError:
            flash("⚠ 数量は数値を入力してください！", "error")
            error_occurred = True
        
        if not workprocess or not workday:
            flash("⚠ 行程と作業日は入力してください！", "error")
            error_occurred = True
        else: # 作業日の形式チェック
            try:
                datetime.strptime(workday, "%Y-%m-%d")
            except ValueError:
                flash("⚠ 作業日はYYYY-MM-DDの形式で入力してください！", "error")
                error_occurred = True

        if workcd and not selected_option and not error_occurred: # WorkCD入力時のみWorkName選択を必須とする場合
            flash("⚠ WorkCDに対応するWorkNameの選択が必要です！", "error")
            error_occurred = True
        elif selected_option: # WorkNameが選択されている場合
            try:
                workname, bookname = selected_option.split("||")
            except ValueError:
                flash("⚠ WorkNameの選択値に不正な形式が含まれています。", "error")
                error_occurred = True
        
        if error_occurred:
            return render_template("index.html",
                                   personid_list=personid_list_data,
                                   personid_dict=personid_dict_data,
                                   selected_personid=selected_personid,
                                   workprocess_list=workprocess_list_data,
                                   workday=workday,
                                   workcd=workcd,
                                   workoutput=workoutput,
                                   workprocess=workprocess,
                                   selected_workname_option=selected_option
                                   )

        dest_table = f"TablePersonID_{selected_personid}"
        dest_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{dest_table}"
        unitprice = unitprice_dict_data.get(workprocess, 0)

        status_code, response_text, new_record_id = send_record_to_destination(
            dest_url, workcd if workcd else "0", workname, bookname, workoutput_val, workprocess, unitprice, workday # workcdが空なら"0"
        )

        flash(response_text, "success" if status_code == 200 else "error")
        session['selected_personid'] = selected_personid
        session['workday'] = workday

        if status_code == 200 and new_record_id:
            session['new_record_id'] = new_record_id
            try:
                workday_dt = datetime.strptime(workday, "%Y-%m-%d")
                return redirect(url_for("records", year=workday_dt.year, month=workday_dt.month))
            except ValueError: 
                 return redirect(url_for("records")) 
        else:
            # 送信失敗時も入力値を保持してindex.htmlを再表示
            return render_template("index.html",
                                   personid_list=personid_list_data,
                                   personid_dict=personid_dict_data,
                                   selected_personid=selected_personid, # POSTされた値を維持
                                   workprocess_list=workprocess_list_data,
                                   workday=workday, # POSTされた値を維持
                                   workcd=workcd,
                                   workoutput=workoutput,
                                   workprocess=workprocess,
                                   selected_workname_option=selected_option
                                   )

    # GET リクエスト
    selected_personid_session = session.get('selected_personid', "")
    session_workday = session.get('workday')

    if session_workday:
        workday_default = session_workday
    else:
        workday_default = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

    return render_template("index.html",
                           workprocess_list=workprocess_list_data,
                           personid_list=personid_list_data,
                           personid_dict=personid_dict_data,
                           selected_personid=selected_personid_session, 
                           workday=workday_default)


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 10000)) 
    serve(app, host="0.0.0.0", port=port)