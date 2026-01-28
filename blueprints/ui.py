# blueprints/ui.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, session, current_app
)
from datetime import datetime, date, timedelta
import json

# サービスモジュールから必要な関数をインポート
from data_services import get_cached_personid_data, get_cached_workprocess_data # forms.pyは使わないので削除

# ★★★ airtable_serviceからのインポートを再確認 ★★★
from airtable_service import (
    create_airtable_record,
    get_airtable_records_for_month,  # ← この行が重要です！
    delete_airtable_record,
    get_airtable_record_details,
    update_airtable_record_fields
)
from .auth import login_required # auth.py が同じ blueprints フォルダにあると仮定

# UI用 Blueprint を作成 (変更なし)
ui_bp = Blueprint(
    'ui_bp', __name__,
    template_folder='../templates',
    static_folder='../static'
)

# -------------------------------
# Flask のルート (入力フォーム) - "/"
@ui_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    logged_in_pid = session.get('logged_in_personid')
    logged_in_pname = session.get('logged_in_personname', '不明なユーザー')

    workprocess_list_data, unitprice_dict_data = get_cached_workprocess_data() # Pythonの辞書として取得

    template_context = {
        "logged_in_personid": logged_in_pid,
        "logged_in_personname": logged_in_pname,
        "workprocess_list": workprocess_list_data,
        # ★★★ 変更点: Python辞書をそのまま渡す ★★★
        "unitprice_data_for_js": unitprice_dict_data, 
        "workday": session.get('workday', (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")),
        "workcd": "",
        "workoutput": "",
        "workprocess_selected": "",
        "selected_workname_option": "",
        "bookname_hidden": "",
        "unitprice": "" 
    }

    if request.method == "POST":
        workcd = request.form.get("workcd", "").strip()
        workoutput = request.form.get("workoutput", "").strip() or "0"
        workprocess = request.form.get("workprocess", "").strip()
        workday = request.form.get("workday", "").strip()
        selected_option = request.form.get("workname", "").strip()
        bookname_from_hidden = request.form.get("bookname_hidden", "").strip()

        template_context.update({
            "workcd": workcd, "workoutput": workoutput, "workprocess_selected": workprocess,
            "workday": workday, "selected_workname_option": selected_option,
            "bookname_hidden": bookname_from_hidden
        })

        workname, bookname = "", ""
        workoutput_val = 0
        error_occurred = False

        if workcd and not workcd.isdigit():
            flash("⚠ WorkCD は数値で入力してください！", "error"); error_occurred = True
        try:
            workoutput_val = int(workoutput)
        except ValueError:
            flash("⚠ 数量は数値を入力してください！", "error"); error_occurred = True; workoutput_val = 0
        if not workprocess or not workday:
            flash("⚠ 行程と作業日は入力してください！", "error"); error_occurred = True
        else:
            try: datetime.strptime(workday, "%Y-%m-%d")
            except ValueError: flash("⚠ 作業日はYYYY-MM-DDの形式で入力してください！", "error"); error_occurred = True
        if not selected_option and workcd:  
            flash("⚠ WorkCDを入力した場合は品名も選択してください！", "error"); error_occurred = True
        elif selected_option:
            workname = selected_option
            bookname = bookname_from_hidden
        
        if error_occurred:
            current_app.logger.warning(f"UI index POST - 入力エラー: LoggedInPersonID={logged_in_pid}, WorkCD={workcd}")
            # unitprice_data_for_js も渡す
            return render_template("index.html", **template_context) # template_contextにunitprice_data_for_jsは既に入っている

        unitprice = unitprice_dict_data.get(workprocess, 0.0)

        current_app.logger.info(f"UI index POST - Airtable送信準備: LoggedInPersonID={logged_in_pid}, WorkCD={workcd or 'N/A'}")
        status_code, response_text, new_record_id = create_airtable_record(
            str(logged_in_pid), workcd, workname, bookname, workoutput_val, workprocess, unitprice, workday
        )

        flash(response_text, "success" if status_code in (200, 201) and new_record_id else "error")
        session['selected_personid'] = str(logged_in_pid) 
        session['workday'] = workday

        if status_code in (200, 201) and new_record_id:
            session['new_record_id'] = new_record_id
            try:
                workday_dt = datetime.strptime(workday, "%Y-%m-%d")
                return redirect(url_for(".records", year=workday_dt.year, month=workday_dt.month))
            except ValueError: 
                return redirect(url_for(".records")) 
        else:
            # unitprice_data_for_js も渡す
            return render_template("index.html", **template_context)

    # GET リクエスト時
    # template_context は既に unitprice_data_for_js を含んでいる
    return render_template("index.html", **template_context)


# ----------------------------------------------------------------------------------
# 以下、records, edit_record, delete_record ルートは変更なし (前回のUI Blueprint化時点のまま)
# ----------------------------------------------------------------------------------
@ui_bp.route("/records")
@ui_bp.route("/records/<int:year>/<int:month>")
@login_required # ★★★ records ルートにも login_required を適用 ★★★
def records(year=None, month=None):
    # --- ログインユーザー情報をセッションから取得 ---
    # selected_personid の代わりに logged_in_personid を使用する
    logged_in_pid = session.get('logged_in_personid')
    # logged_in_pname = session.get('logged_in_personname', '不明なユーザー') # 必要なら

    # personid_from_param の処理は、他人のデータを見せないようにするため、
    # logged_in_pid と比較するか、あるいはURLパラメータ自体を廃止しセッションのみ使う
    personid_from_param = request.args.get("personid")
    person_id_to_use = str(logged_in_pid) # デフォルトはログインユーザー

    if personid_from_param:
        if personid_from_param == str(logged_in_pid):
            # URLパラメータがログインユーザーのものならOK (ただし、通常は不要)
            pass 
        else:
            # 他のユーザーのIDが指定された場合は警告し、ログインユーザーのIDを使用
            flash("他のユーザーのレコードは表示できません。", "warning")
            current_app.logger.warning(f"UI records - URLパラメータで異なるPersonIDが指定されました: {personid_from_param} (ログイン中: {logged_in_pid})")
        # 結局、セッションのIDを常に使う
        # このURLクリーンアップロジックは、personidパラメータをURLに残さない方がシンプルになる
        redirect_url = url_for('.records', year=year, month=month) # personidパラメータなしでリダイレクト
        return redirect(redirect_url)

    # selected_personid の代わりに logged_in_pid を使用
    if not person_id_to_use: # logged_in_pid がない場合 (通常は@login_requiredで防がれる)
        flash("ログインしていません。", "error") # 通常ここには来ない
        return redirect(url_for("auth_bp.login"))


    today = date.today()
    default_display_date = today - timedelta(days=30)

    if year is None or month is None:
        selected_workday_from_session = session.get("workday")
        if selected_workday_from_session:
            try: base_date = datetime.strptime(selected_workday_from_session, "%Y-%m-%d").date()
            except ValueError: base_date = default_display_date
        else: base_date = default_display_date
        year = base_date.year
        month = base_date.month
    else:
        try: date(year, month, 1)
        except ValueError:
            flash("⚠ 無効な年月が指定されました。デフォルトの月を表示します。", "warning")
            base_date = default_display_date
            year = base_date.year; month = base_date.month
    
    session['current_display_year'] = year
    session['current_display_month'] = month
    display_month_str = f"{year}年{month}月"
    
   
    force_refresh = (request.args.get("refresh") == "1")
    records_data = get_airtable_records_for_month(person_id_to_use, year, month, force_refresh=force_refresh)

    
    if records_data is None: records_data = []

    total_amount = 0
    for record_item in records_data:
        try:
            unit_price_str = str(record_item.get("UnitPrice", "0")).strip()
            unit_price = float(unit_price_str) if unit_price_str and unit_price_str != "不明" else 0.0
            work_output_str = str(record_item.get("WorkOutput", "0")).strip()
            work_output = int(work_output_str) if work_output_str else 0
            record_item["subtotal"] = unit_price * work_output
        except ValueError: record_item["subtotal"] = 0
        total_amount += record_item["subtotal"]

    unique_workdays = set(r["WorkDay"] for r in records_data if r.get("WorkDay") != "9999-12-31")
    workdays_count = len(unique_workdays)
    
    workoutput_total = 0
    for r_item in records_data:
        if "分給" in r_item.get("WorkProcess", ""):
            work_output_value = str(r_item.get("WorkOutput", "0")).strip()
            if work_output_value and work_output_value.replace('.', '', 1).isdigit():
                try: workoutput_total += float(work_output_value)
                except ValueError: pass # ログは既に出力されていると仮定

    first_day_of_current_month = date(year, month, 1)
    prev_month_date = first_day_of_current_month - timedelta(days=1)
    prev_year, prev_month = prev_month_date.year, prev_month_date.month
    next_month_date = (first_day_of_current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    next_year, next_month = next_month_date.year, next_month_date.month
    
    new_record_id_from_session = session.pop('new_record_id', None)
    edited_record_id_from_session = session.pop('edited_record_id', None)
    personid_dict_data_for_template, _ = get_cached_personid_data()
    personid_dict_all, _ = get_cached_personid_data()
    current_person_name = "不明なユーザー"
    if logged_in_pid is not None:
        person_info = personid_dict_all.get(int(logged_in_pid))
        if person_info and 'name' in person_info:
            current_person_name = person_info['name']
    return render_template(
        "records.html",
        records=records_data,
        current_person_name_for_display=current_person_name, # ★追加
        personid=person_id_to_use, # ログイン中のユーザーID
        personid_dict=personid_dict_data_for_template,
        display_month=display_month_str,
        total_amount=total_amount,
        workdays_count=workdays_count,
        workoutput_total=workoutput_total,
        current_year=year, current_month=month, 
        new_record_id=new_record_id_from_session,
        edited_record_id=edited_record_id_from_session,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month
    )

@ui_bp.route("/delete_record/<record_id>", methods=["POST"])
@login_required
def delete_record(record_id):
    logged_in_pid = str(session.get("logged_in_personid"))

    success, message = delete_airtable_record(logged_in_pid, record_id)
    flash(message, "success" if success else "error")

    try:
        year  = int(request.form.get("year"))
        month = int(request.form.get("month"))
    except (TypeError, ValueError):
        year  = session.get("current_display_year", date.today().year)
        month = session.get("current_display_month", date.today().month)

    # ✅ キャッシュの当月から record_id を消す（あれば）
    if success:
        try:
            from airtable_cache import month_cache_remove_record
            ok = month_cache_remove_record(logged_in_pid, year, month, record_id)
            if ok:
                current_app.logger.info(f"[CACHE] removed record {record_id} from {year}-{month:02d}")
        except Exception as e:
            current_app.logger.warning(f"delete cache update skipped: {e}")

    return redirect(url_for(".records", year=year, month=month))


@ui_bp.route("/edit_record/<record_id>", methods=["GET", "POST"])
@login_required # ★★★ 保護 ★★★
def edit_record(record_id):
    logged_in_pid = str(session.get("logged_in_personid"))

    original_year = session.get('current_display_year', date.today().year)
    original_month = session.get('current_display_month', date.today().month)
    # ... (URLパラメータからの年月取得ロジックは変更なし) ...

    if request.method == "POST":
        # ... (フォームデータ取得) ...
        new_day = request.form.get("WorkDay", "")
        new_output_str = request.form.get("WorkOutput", "")
        try:
            new_output_val = int(new_output_str)
        except ValueError:
            # ... (エラー処理、レコード再取得してフォーム表示) ...
            flash("❌ 作業量は数値で入力してください。", "error")
            record_data_for_render, error_get_msg = get_airtable_record_details(logged_in_pid, record_id)
            # ... (エラー時のテンプレート再表示) ...
            return render_template("edit_record.html", record=record_data_for_render, record_id=record_id, original_year=original_year, original_month=original_month)


        updated_fields = { "WorkDay": new_day, "WorkOutput": new_output_val }
        # ★★★ logged_in_pid を使用 ★★★
        success, message = update_airtable_record_fields(logged_in_pid, record_id, updated_fields)
        # ... (flashメッセージ、リダイレクト処理) ...
        if success:
            session['edited_record_id'] = record_id

            # ✅ キャッシュ反映（Airtable追加GETなし）
            try:
                from airtable_cache import month_cache_update_record, month_cache_move_record
                new_dt = datetime.strptime(new_day, "%Y-%m-%d")
                new_y, new_m = new_dt.year, new_dt.month

                # records表示で使うキー名に合わせる（あなたの processed_records は WorkDay/WorkOutput 等）
                patch_fields = {"WorkDay": new_day, "WorkOutput": new_output_val}

                if (new_y == original_year) and (new_m == original_month):
                    ok = month_cache_update_record(logged_in_pid, original_year, original_month, record_id, patch_fields)
                else:
                    ok = month_cache_move_record(
                        logged_in_pid,
                        original_year, original_month,
                        new_y, new_m,
                        record_id,
                        patch_fields
                    )

                if ok:
                    current_app.logger.info(f"[CACHE] updated/moved record {record_id}")
            except Exception as e:
                current_app.logger.warning(f"edit cache update skipped: {e}")



    # GET リクエスト時
    # ★★★ logged_in_pid を使用 ★★★
    record_data, error_message = get_airtable_record_details(logged_in_pid, record_id)
    if error_message or record_data is None:
        flash(error_message or "❌ レコード取得に失敗しました。", "error")
        return redirect(url_for(".records", year=original_year, month=original_month))

    return render_template(
        "edit_record.html",
        record=record_data,
        record_id=record_id,
        original_year=original_year,
        original_month=original_month
    )