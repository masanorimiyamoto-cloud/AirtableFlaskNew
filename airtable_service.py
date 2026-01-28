# airtable_service.py
import os
import requests
import logging


from airtable_cache import cache_get, cache_set, cache_delete, month_key, MONTH_CACHE_TTL_SEC


MONTH_CACHE_TTL = 60  # まず60秒でOK（30〜300秒で調整）
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

def create_airtable_record(person_id: str, workcord: str, workname: str, bookname: str,
                           workoutput: int, workprocess: str, unitprice: float, workday: str):
    """Airtableに新しいレコードを作成。成功時に当月キャッシュがあれば差分追加で更新する。"""
    url = _build_airtable_url(person_id)
    if not url:
        return None, "⚠ AirtableのURL構築に失敗しました（設定不備の可能性）。", None

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
        response.raise_for_status()
        resp_json = response.json()
        new_id = resp_json.get("id")

        # ✅ Airtable成功コードは 200/201 両方あり得る
        status = response.status_code
        if status not in (200, 201) or not new_id:
            return status, "⚠ 送信は完了したようですがID取得に失敗しました。", None

        # ✅ キャッシュが存在するなら “差分追加” して更新（次の records でGETしない）
        try:
            from airtable_cache import cache_get, cache_set, month_key
            CACHE_TTL_SEC = 300
            y = int(workday[:4]); m = int(workday[5:7])
            key = month_key(person_id, y, m)
            cached = cache_get(key)
            if cached is not None:
                new_row = {
                    "id": new_id,
                    "WorkDay": workday,
                    "WorkCD": workcord_int,
                    "WorkName": str(workname),
                    "WorkProcess": str(workprocess),
                    "UnitPrice": float(unitprice),
                    "WorkOutput": int(workoutput),
                }
                cached2 = list(cached) + [new_row]
                cached2.sort(key=lambda x: x.get("WorkDay", "9999-12-31"))
                cache_set(key, cached2, CACHE_TTL_SEC)
                logger.info(f"[CACHE WRITE-THROUGH] appended new record to {key}")
        except Exception as e:
            logger.warning(f"キャッシュ差分更新に失敗（無視して継続）: {e}")

        logger.info(f"Airtableへのレコード作成成功: ID={new_id}, PersonID={person_id}")
        return status, "✅ Airtable にデータを送信しました！", new_id

    except requests.exceptions.HTTPError as http_err:
        err_msg = "詳細不明"
        try:
            err_detail = http_err.response.json().get('error', {})
            if isinstance(err_detail, dict):
                err_msg = err_detail.get('message', '詳細不明')
            elif isinstance(err_detail, str):
                err_msg = err_detail
        except ValueError:
            err_msg = http_err.response.text if http_err.response.text else '詳細不明'

        logger.error(f"Airtableレコード作成エラー (HTTPError): {http_err.response.status_code} {err_msg} - URL: {url} - Data: {data.get('fields')}")
        return http_err.response.status_code, f"⚠ 送信エラー (HTTP {http_err.response.status_code}): {err_msg}", None

    except requests.RequestException as e:
        logger.error(f"Airtableレコード作成エラー (RequestException): {str(e)} - URL: {url} - Data: {data.get('fields')}", exc_info=True)
        return None, f"⚠ 送信エラー: {str(e)}", None


    




def get_airtable_records_for_month(person_id: str, target_year: int, target_month: int, force_refresh: bool = False):
    """指定されたPersonIDと年月のレコードをAirtableから取得（短TTLキャッシュ + 強制更新対応）。"""

    # ✅ まずキャッシュ（強制更新でなければ）
    key = None
    CACHE_TTL_SEC = 10  # ← まず10秒推奨（運用により 5〜30秒で調整）
    if not force_refresh:
        try:
            from airtable_cache import cache_get, cache_set, month_key
            key = month_key(person_id, target_year, target_month)
            cached = cache_get(key)
            if cached is not None:
                logger.info(f"[CACHE HIT] {key}")
                return cached
        except Exception as e:
            logger.warning(f"キャッシュ参照失敗（無視）: {e}")

    url = _build_airtable_url(person_id)
    if not url:
        return []

    params = {
        "filterByFormula": f"AND(YEAR({{WorkDay}})={target_year}, MONTH({{WorkDay}})={target_month})",
        "fields[]": ["WorkDay","WorkCord","WorkName","WorkProcess","UnitPrice","WorkOutput","BookName"],
        "sort[0][field]": "WorkDay",
        "sort[0][direction]": "asc",
        "pageSize": 100
    }

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        records_data = response.json().get("records", [])

        processed_records = []
        for record in records_data:
            fields = record.get("fields", {})
            processed_records.append({
                "id": record.get("id", "不明なID"),
                "WorkDay": fields.get("WorkDay", "9999-12-31"),
                "WorkCD": fields.get("WorkCord", "不明"),
                "WorkName": fields.get("WorkName", "不明"),
                "WorkProcess": fields.get("WorkProcess", "不明"),
                "UnitPrice": fields.get("UnitPrice", "不明"),
                "WorkOutput": fields.get("WorkOutput", "0"),
            })

        # ✅ キャッシュ保存（短TTL）
        try:
            from airtable_cache import cache_set, month_key
            key = month_key(person_id, target_year, target_month)
            cache_set(key, processed_records, CACHE_TTL_SEC)
            logger.info(f"[CACHE SET] {key} ttl={CACHE_TTL_SEC}s")
        except Exception as e:
            logger.warning(f"キャッシュ保存失敗（無視）: {e}")

        return processed_records

    except Exception as e:
        logger.error(f"Airtableレコード取得エラー: {e}", exc_info=True)
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