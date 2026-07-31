# data_services.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import os
import logging
import unicodedata

# セルの表示形式（桁区切り・日付書式など）に影響されない生の値を取得する
try:
    from gspread.utils import ValueRenderOption
    UNFORMATTED = ValueRenderOption.unformatted
except Exception:  # gspreadのバージョン差異に備えたフォールバック
    UNFORMATTED = "UNFORMATTED_VALUE"

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ✅ Google Sheets 設定 (These should ideally come from environment variables or a config file too)
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", "configGooglesheet.json")
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "AirtableTest129")
# ★ ファイル名は変更・コピーで簡単に壊れるので、可能ならキー(URLのID)で開く
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY", "1RGdKiAqFehapGvTQM7GxCNrLC6Xzdup_O2qJOOWs7Uc")
WORKSHEET_NAME = "wsTableCD"
PERSONID_WORKSHEET_NAME = "wsPersonID"
WORKPROCESS_WORKSHEET_NAME = "wsWorkProcess"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# ★★★ Google Sheets API Client Initialization - ADD THIS BLOCK ★★★
client = None # Initialize client to None
try:
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        logger.info("Google Sheets client initialized successfully.")
    else:
        logger.critical(f"サービスアカウントファイルが見つかりません: {SERVICE_ACCOUNT_FILE}")
        # client remains None, functions using it will log errors and return early
except Exception as e:
    logger.critical(f"Google Sheets クライアントの初期化に失敗しました: {e}", exc_info=True)
    # client remains None
# ★★★ END OF CLIENT INITIALIZATION BLOCK ★★★


CACHE_TTL = 300  # 300秒 (5分間)
ERROR_RETRY_INTERVAL = 30  # ロード失敗時に再試行するまでの秒数（APIを叩き続けないため）


def open_spreadsheet():
    """スプレッドシートを開く。キー指定を優先し、駄目なら名前で開く。

    名前で開く方法はリネームや同名コピーの作成で壊れるため、キーを先に試す。
    """
    if not client:
        raise RuntimeError(f"Google Sheets クライアントが初期化されていません (認証ファイル: {SERVICE_ACCOUNT_FILE})")
    if SPREADSHEET_KEY:
        try:
            return client.open_by_key(SPREADSHEET_KEY)
        except Exception as e:
            logger.warning(f"スプレッドシートをキー({SPREADSHEET_KEY})で開けませんでした: {e}。名前で再試行します。")
    return client.open(SPREADSHEET_NAME)


def normalize_workcord(value):
    """WorkCord を検索キー用の半角数字文字列に正規化する。

    シートのセル書式（桁区切り "1,555"、小数 "1555.0"、全角 "１５５５"、
    前後の空白）に左右されずに一致させるための正規化。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = unicodedata.normalize("NFKC", str(value)).strip()
    s = s.replace(",", "").replace(" ", "").replace("　", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ===== PersonID データ =====
PERSON_ID_DICT = {}
# ... (rest of your data_services.py code, like load_personid_data, etc.) ...
# The load_* functions will now correctly find the 'client' variable defined above.

# ===== PersonID データ =====
PERSON_ID_DICT = {} # 構造変更: { pid: {"name": "pname", "pin_hash": "hash_value"}, ... }
PERSON_ID_LIST = [] # これはPIDの数値リストのままでOK
last_personid_load_time = 0

def load_personid_data():
    global PERSON_ID_DICT, PERSON_ID_LIST, last_personid_load_time
    try:
        sheet = open_spreadsheet().worksheet(PERSONID_WORKSHEET_NAME)
        records = sheet.get_all_records(
            expected_headers=["PersonID", "PersonName", "PINHash"],
            value_render_option=UNFORMATTED,
        )
        temp_dict = {}
        temp_id_list = [] # PersonIDの数値リストもここで再構築
        for row in records:
            pid_str = str(row.get("PersonID", "")).strip()
            pname = str(row.get("PersonName", "")).strip()
            pin_hash = str(row.get("PINHash", "")).strip() # ★★★ PINHash列を読み込む ★★★

            if pid_str and pname: # PINHashは空でも許容するかもしれないが、ログイン機能には必須
                try:
                    pid_int = int(pid_str)
                    if not pin_hash: # PINHashが設定されていないユーザーはログインできない
                        logger.warning(f"PersonID '{pid_int}' にPINHashが設定されていません。このユーザーはログインできません。")
                        # ログインさせないユーザーは辞書に含めないか、特別なマークを付ける
                        # ここでは、ログイン機能のためPINHashが必須であるとして、なければスキップする例
                        # continue 
                        # もしくは、辞書には含めておき、ログイン時にPINHashの有無をチェックする
                    
                    # ★★★ PERSON_ID_DICTの構造を変更 ★★★
                    temp_dict[pid_int] = {"name": pname, "pin_hash": pin_hash}
                    temp_id_list.append(pid_int)

                except ValueError:
                    logger.warning(f"PersonID '{pid_str}' を整数に変換できませんでした。スキップします。")
                    continue
            elif pid_str: # IDはあるが名前がない場合など（通常はないはず）
                 logger.warning(f"PersonID '{pid_str}' のデータが不完全です（名前がないなど）。")


        if not temp_dict:
            raise ValueError(
                f"'{PERSONID_WORKSHEET_NAME}' から有効な行を1件も取得できませんでした "
                f"(読み込み行数: {len(records)})。ヘッダー行の列名を確認してください。"
            )
        PERSON_ID_DICT = temp_dict
        PERSON_ID_LIST = sorted(temp_id_list) # IDリストをソートしておく
        last_personid_load_time = time.time()
        logger.info(f"Google Sheets から {len(PERSON_ID_DICT)} 件の PersonID/PersonName/PINHash レコードをロードしました！")
    except Exception as e:
        # ★ 失敗時に空にすると全員ログインできなくなるため、直前のキャッシュを保持する
        last_personid_load_time = time.time() - CACHE_TTL + ERROR_RETRY_INTERVAL
        logger.error(f"Google Sheets の PersonID データ取得に失敗: {e}", exc_info=True)

def get_cached_personid_data():
    # この関数は PERSON_ID_DICT と PERSON_ID_LIST を返すので、
    # PERSON_ID_DICT の構造が変わったことを呼び出し元が意識する必要があるかもしれない。
    # 今回は、PersonID選択ドロップダウンで名前も表示するために辞書も返す。
    if time.time() - last_personid_load_time > CACHE_TTL:
        logger.info("PersonIDキャッシュが無効または期限切れです。再ロードします。")
        load_personid_data()
    return PERSON_ID_DICT, PERSON_ID_LIST

# ... (WorkCord, WorkProcess関連の関数は変更なし) ...

# ===== WorkCord/WorkName/BookName キャッシュ =====
workcord_dict = {}
last_workcord_load_time = 0
workcord_load_error = ""  # 直近のロード失敗理由（空文字なら正常）

# ★ 他の列（Kname, Material など）のヘッダーが空欄・重複していても
#   gspread が GSpreadException を投げないように、必要な列だけを明示する
WORKCORD_EXPECTED_HEADERS = ["WorkCord", "WorkName", "BookName"]

def load_workcord_data():
    global workcord_dict, last_workcord_load_time, workcord_load_error
    try:
        sheet = open_spreadsheet().worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records(
            expected_headers=WORKCORD_EXPECTED_HEADERS,
            value_render_option=UNFORMATTED,
        )
        new_dict = {}
        for row in records:
            workcord = normalize_workcord(row.get("WorkCord"))
            workname = str(row.get("WorkName", "")).strip()
            bookname = str(row.get("BookName", "")).strip()
            if workcord and workname: # BookNameは空でも許容するかもしれないので条件から外す場合も
                new_dict.setdefault(workcord, []).append({"workname": workname, "bookname": bookname})

        if not new_dict:
            # 行は読めたのに1件も作れない = ヘッダー名の変更やシート差し替えを疑う
            raise ValueError(
                f"'{WORKSHEET_NAME}' から有効な行を1件も取得できませんでした "
                f"(読み込み行数: {len(records)})。ヘッダー行の WorkCord / WorkName 列名を確認してください。"
            )

        workcord_dict = new_dict
        workcord_load_error = ""
        last_workcord_load_time = time.time()
        total_records = sum(len(lst) for lst in workcord_dict.values())
        logger.info(f"Google Sheets から {total_records} 件の WorkCD/WorkName/BookName レコードをロードしました！")
    except Exception as e:
        # ★ 失敗しても既存のキャッシュは消さない（一時的なエラーで全滅させないため）
        workcord_load_error = f"{type(e).__name__}: {e}"
        last_workcord_load_time = time.time() - CACHE_TTL + ERROR_RETRY_INTERVAL
        logger.error(f"Google Sheets の WorkCordデータ取得に失敗: {e}", exc_info=True)

def get_cached_workcord_data():
    # last_workcord_load_time は成功時も失敗時も更新されるので、
    # 失敗中に入力1文字ごとへAPIを叩き続ける（レート制限を誘発する）ことがない
    if time.time() - last_workcord_load_time > CACHE_TTL:
        logger.info("WorkCordキャッシュが無効または期限切れです。再ロードします。")
        load_workcord_data()
    return workcord_dict

def get_workcord_load_error():
    """WorkCordデータのロードに失敗している場合、その理由を返す（正常時は空文字）。"""
    return workcord_load_error

# ===== WorkProcess/UnitPrice データ =====
workprocess_list_cache = []
unitprice_dict_cache = {}
last_workprocess_load_time = 0

def load_workprocess_data():
    global workprocess_list_cache, unitprice_dict_cache, last_workprocess_load_time
    try:
        sheet = open_spreadsheet().worksheet(WORKPROCESS_WORKSHEET_NAME)
        records = sheet.get_all_records(
            expected_headers=["WorkProcess", "UnitPrice"],
            value_render_option=UNFORMATTED,
        )
        temp_list = []
        temp_dict = {}
        for row in records:
            wp = str(row.get("WorkProcess", "")).strip()
            up_str = str(row.get("UnitPrice", "0")).strip() # 文字列として取得
            if wp:
                temp_list.append(wp)
                try:
                    # UnitPriceをfloatに変換しようと試みる
                    up = float(up_str)
                except ValueError:
                    logger.warning(f"WorkProcess '{wp}' の UnitPrice '{up_str}' をfloatに変換できませんでした。0として扱います。")
                    up = 0.0 # エラーの場合は0または他のデフォルト値
                temp_dict[wp] = up
        if not temp_list:
            raise ValueError(
                f"'{WORKPROCESS_WORKSHEET_NAME}' から有効な行を1件も取得できませんでした "
                f"(読み込み行数: {len(records)})。ヘッダー行の列名を確認してください。"
            )
        workprocess_list_cache = temp_list
        unitprice_dict_cache = temp_dict
        last_workprocess_load_time = time.time()
        logger.info(f"Google Sheets から {len(workprocess_list_cache)} 件の WorkProcess/UnitPrice レコードをロードしました！")
    except Exception as e:
        # ★ 失敗しても直前のキャッシュを保持する
        last_workprocess_load_time = time.time() - CACHE_TTL + ERROR_RETRY_INTERVAL
        logger.error(f"Google Sheets の WorkProcessデータ取得に失敗: {e}", exc_info=True)

def get_cached_workprocess_data():
    if time.time() - last_workprocess_load_time > CACHE_TTL:
        logger.info("WorkProcessキャッシュが無効または期限切れです。再ロードします。")
        load_workprocess_data()
    return workprocess_list_cache, unitprice_dict_cache