# airtable_service.py
import os
import requests
import logging

# このモジュール用のロガーを設定
logger = logging.getLogger(__name__)
# 基本的なロガー設定 (app.py側の設定とは独立して、このモジュール単体でもログ出力できるように)
if not logger.hasHandlers(): # ハンドラが重複してログが二重に出力されるのを防ぐ
    handler = logging.StreamHandler() # コンソールに出力
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO) # このモジュールからのログはINFOレベル以上を出力

# ==== Airtable 設定 ====
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID_BookSKY")

if not AIRTABLE_TOKEN or not AIRTABLE_BASE_ID:
    logger.critical("Airtableの環境変数 (AIRTABLE_TOKEN, AIRTABLE_BASE_ID_BookSKY) が設定されていません。Airtable連携機能は動作しません。")
    # これらの値がない場合、以降の関数は正常に動作しないため、早期に警告を出す

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

def _build_airtable_url(person_id: str, record_id: str = None) -> str | None:
    """
    指定されたPersonIDとオプションのRecordIDに基づいてAirtableのテーブル/レコードURLを構築します。
    環境変数が設定されていない場合はNoneを返します。
    """
    if not AIRTABLE_TOKEN or not AIRTABLE_BASE_ID:
        logger.error("Airtableの接続情報（トークンまたはベースID）が設定されていません。")
        return None
    if not person_id:
        logger.error("PersonIDが指定されていないため、AirtableのURLを構築できません。")
        return None
        
    table_name = f"TablePersonID_{person_id}"
    base_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}"
    if record_id:
        return f"{base_url}/{record_id}"
    return base_url

def create_airtable_record(person_id: str, workcord: str, workname: str, bookname: str, workoutput: int, workprocess: str, unitprice: float, workday: str):
    """Airtableに新しいレコードを作成します。元のsend_record_to_destination関数に相当。"""
    url = _build_airtable_url(person_id)
    if not url:
        return None, "⚠ AirtableのURL構築に失敗しました（設定不備の可能性）。", None

    # WorkCordが空または数値でない場合は0として扱う (元のコードの挙動に合わせる)
    try:
        workcord_int = int(workcord) if workcord else 0
    except ValueError:
        logger.warning(f"WorkCord '{workcord}' を整数に変換できませんでした。0として扱います。 (PersonID: {person_id})")
        workcord_int = 0

    data = {
        "fields": {
            "WorkCord": workcord_int,
            "WorkName": str(workname),
            "BookName": str(bookname),
            "WorkOutput": int(workoutput),
            "WorkProcess": str(workprocess),
            "UnitPrice": float(unitprice),
            "WorkDay": workday
        }
    }
    try:
        logger.info(f"Airtableへのレコード作成開始: URL={url}, PersonID={person_id}")
        response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
        resp_json = response.json()
        new_id = resp_json.get("id")
        logger.info(f"Airtableへのレコード作成成功: ID={new_id}, PersonID={person_id}")
        return response.status_code, "✅ Airtable にデータを送信しました！", new_id
    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict):
                err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str):
                err_msg = err_detail
        except ValueError: # JSONデコード失敗の場合
             err_msg = http_err.response.text if http_err.response.text else '詳細不明'

        logger.error(f"Airtableレコード作成エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url} - Data: {data.get('fields')}")
        return http_err.response.status_code, f"⚠ 送信エラー (HTTP {http_err.response.status_code}): {err_msg}", None
    except requests.RequestException as e:
        logger.error(f"Airtableレコード作成エラー (RequestException): {str(e)} - URL: {url} - Data: {data.get('fields')}", exc_info=True)
        return None, f"⚠ 送信エラー: {str(e)}", None

def get_airtable_records_for_month(person_id: str, target_year: int, target_month: int):
    """指定されたPersonIDと年月のレコードをAirtableから取得します。元のget_selected_month_records関数に相当。"""
    url = _build_airtable_url(person_id)
    if not url:
        return [] # 設定不備などの場合は空リスト

    params = {"filterByFormula": f"AND(YEAR({{WorkDay}})={target_year}, MONTH({{WorkDay}})={target_month})"}
    try:
        logger.info(f"Airtableからのレコード取得開始: URL={url}, Params={params}, PersonID={person_id}")
        response = requests.get(url, headers=HEADERS, params=params, timeout=15) # 少し長めのタイムアウト
        response.raise_for_status()
        records_data = response.json().get("records", [])
        logger.info(f"Airtableから {len(records_data)} 件のレコードを取得 (PersonID: {person_id}, {target_year}-{target_month})")
        
        processed_records = []
        for record in records_data:
            fields = record.get("fields", {})
            processed_records.append({
                "id": record.get("id", "不明なID"),
                "WorkDay": fields.get("WorkDay", "9999-12-31"),
                "WorkCD": fields.get("WorkCord", "不明"),
                "WorkName": fields.get("WorkName", "不明"),
                "WorkProcess": fields.get("WorkProcess", "不明"),
                "UnitPrice": fields.get("UnitPrice", "不明"), # 文字列として取得される可能性も考慮
                "WorkOutput": fields.get("WorkOutput", "0"),
            })
        processed_records.sort(key=lambda x: x["WorkDay"])
        return processed_records
    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict): err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str): err_msg = err_detail
        except ValueError: err_msg = http_err.response.text if http_err.response.text else '詳細不明'
        logger.error(f"Airtableレコード取得エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url}")
        return []
    except requests.RequestException as e:
        logger.error(f"Airtableレコード取得エラー (RequestException): {str(e)} - URL: {url}", exc_info=True)
        return []
    except Exception as e: # その他の予期せぬエラー
        logger.error(f"Airtableレコード取得中の予期せぬエラー: {e} - URL: {url}", exc_info=True)
        return []

def delete_airtable_record(person_id: str, record_id: str):
    """指定されたレコードIDのデータをAirtableから削除します。"""
    url = _build_airtable_url(person_id, record_id)
    if not url:
        return False, "⚠ AirtableのURL構築に失敗しました（設定不備の可能性）。"

    try:
        logger.info(f"Airtableレコード削除開始: URL={url}, PersonID={person_id}, RecordID={record_id}")
        response = requests.delete(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        logger.info(f"Airtableレコード削除成功: RecordID={record_id}, PersonID={person_id}")
        return True, "✅ レコードを削除しました！"
    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict): err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str): err_msg = err_detail
        except ValueError: err_msg = http_err.response.text if http_err.response.text else '詳細不明'
        logger.error(f"Airtableレコード削除エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url}")
        return False, f"❌ 削除に失敗しました (HTTP {http_err.response.status_code}): {err_msg}"
    except requests.RequestException as e:
        logger.error(f"Airtableレコード削除エラー (RequestException): {str(e)} - URL: {url}", exc_info=True)
        return False, f"❌ 削除に失敗しました: {str(e)}"

def get_airtable_record_details(person_id: str, record_id: str):
    """指定されたレコードIDの詳細データをAirtableから取得します（編集画面用）。"""
    url = _build_airtable_url(person_id, record_id)
    if not url:
        return None, "⚠ AirtableのURL構築に失敗しました（設定不備の可能性）。"

    try:
        logger.info(f"Airtableレコード詳細取得開始: URL={url}, PersonID={person_id}, RecordID={record_id}")
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        record_data = response.json().get("fields", {})
        logger.info(f"Airtableレコード詳細取得成功: RecordID={record_id}, PersonID={person_id}")
        return record_data, None # データとエラーメッセージなし
    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict): err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str): err_msg = err_detail
        except ValueError: err_msg = http_err.response.text if http_err.response.text else '詳細不明'
        logger.error(f"Airtableレコード詳細取得エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url}")
        return None, f"❌ レコード取得に失敗しました (HTTP {http_err.response.status_code}): {err_msg}"
    except requests.RequestException as e:
        logger.error(f"Airtableレコード詳細取得エラー (RequestException): {str(e)} - URL: {url}", exc_info=True)
        return None, f"❌ レコード取得に失敗しました: {str(e)}"

def update_airtable_record_fields(person_id: str, record_id: str, fields_to_update: dict):
    """Airtableの既存レコードの指定されたフィールドを更新します。"""
    url = _build_airtable_url(person_id, record_id)
    if not url:
        return False, "⚠ AirtableのURL構築に失敗しました（設定不備の可能性）。"

    data = {"fields": fields_to_update}
    try:
        logger.info(f"Airtableレコード更新開始: URL={url}, Data={data}, PersonID={person_id}, RecordID={record_id}")
        response = requests.patch(url, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        logger.info(f"Airtableレコード更新成功: RecordID={record_id}, PersonID={person_id}")
        return True, "✅ レコードを更新しました！" # 成功時はメッセージのみを返す
    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict): err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str): err_msg = err_detail
        except ValueError: err_msg = http_err.response.text if http_err.response.text else '詳細不明'
        logger.error(f"Airtableレコード更新エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url}")
        return False, f"❌ 更新に失敗しました (HTTP {http_err.response.status_code}): {err_msg}"
    except requests.RequestException as e:
        logger.error(f"Airtableレコード更新エラー (RequestException): {str(e)} - URL: {url}", exc_info=True)
        return False, f"❌ 更新に失敗しました: {str(e)}"