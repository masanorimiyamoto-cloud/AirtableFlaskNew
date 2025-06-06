# data_services.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import os
import logging

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
    if not client:
        logger.error("Google Sheets クライアントが初期化されていません。PersonIDデータをロードできません。")
        return
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(PERSONID_WORKSHEET_NAME)
        records = sheet.get_all_records()
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


        PERSON_ID_DICT = temp_dict
        PERSON_ID_LIST = sorted(temp_id_list) # IDリストをソートしておく
        last_personid_load_time = time.time()
        logger.info(f"Google Sheets から {len(PERSON_ID_DICT)} 件の PersonID/PersonName/PINHash レコードをロードしました！")
    except Exception as e:
        logger.error(f"Google Sheets の PersonID データ取得に失敗: {e}", exc_info=True)
        PERSON_ID_DICT = {} # エラー時は空にする
        PERSON_ID_LIST = []

def get_cached_personid_data():
    # この関数は PERSON_ID_DICT と PERSON_ID_LIST を返すので、
    # PERSON_ID_DICT の構造が変わったことを呼び出し元が意識する必要があるかもしれない。
    # 今回は、PersonID選択ドロップダウンで名前も表示するために辞書も返す。
    if not PERSON_ID_DICT or (time.time() - last_personid_load_time > CACHE_TTL):
        logger.info("PersonIDキャッシュが無効または期限切れです。再ロードします。")
        load_personid_data()
    return PERSON_ID_DICT, PERSON_ID_LIST

# ... (WorkCord, WorkProcess関連の関数は変更なし) ...

# ===== WorkCord/WorkName/BookName キャッシュ =====
workcord_dict = {}
last_workcord_load_time = 0

def load_workcord_data():
    global workcord_dict, last_workcord_load_time
    if not client:
        logger.error("Google Sheets クライアントが初期化されていません。WorkCordデータをロードできません。")
        return
    workcord_dict = {} # 毎回初期化
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records()
        for row in records:
            workcord = str(row.get("WorkCord", "")).strip()
            workname = str(row.get("WorkName", "")).strip()
            bookname = str(row.get("BookName", "")).strip()
            if workcord and workname: # BookNameは空でも許容するかもしれないので条件から外す場合も
                if workcord not in workcord_dict:
                    workcord_dict[workcord] = []
                workcord_dict[workcord].append({"workname": workname, "bookname": bookname})
        total_records = sum(len(lst) for lst in workcord_dict.values())
        logger.info(f"Google Sheets から {total_records} 件の WorkCD/WorkName/BookName レコードをロードしました！")
        last_workcord_load_time = time.time()
    except Exception as e:
        logger.error(f"Google Sheets の WorkCordデータ取得に失敗: {e}", exc_info=True)

def get_cached_workcord_data():
    if not workcord_dict or (time.time() - last_workcord_load_time > CACHE_TTL):
        logger.info("WorkCordキャッシュが無効または期限切れです。再ロードします。")
        load_workcord_data()
    return workcord_dict

# ===== WorkProcess/UnitPrice データ =====
workprocess_list_cache = []
unitprice_dict_cache = {}
last_workprocess_load_time = 0

def load_workprocess_data():
    global workprocess_list_cache, unitprice_dict_cache, last_workprocess_load_time
    if not client:
        logger.error("Google Sheets クライアントが初期化されていません。WorkProcessデータをロードできません。")
        return
    try:
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKPROCESS_WORKSHEET_NAME)
        records = sheet.get_all_records()
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
        workprocess_list_cache = temp_list
        unitprice_dict_cache = temp_dict
        last_workprocess_load_time = time.time()
        logger.info(f"Google Sheets から {len(workprocess_list_cache)} 件の WorkProcess/UnitPrice レコードをロードしました！")
    except Exception as e:
        logger.error(f"Google Sheets の WorkProcessデータ取得に失敗: {e}", exc_info=True)

def get_cached_workprocess_data():
    if not workprocess_list_cache or (time.time() - last_workprocess_load_time > CACHE_TTL):
        logger.info("WorkProcessキャッシュが無効または期限切れです。再ロードします。")
        load_workprocess_data()
    return workprocess_list_cache, unitprice_dict_cache