# app.py
from flask import Flask
import os
import logging

# データサービスモジュールから初期ロード用関数をインポート
from data_services import (
    load_personid_data,
    load_workcord_data,
    load_workprocess_data
)

# Blueprint をインポート
from blueprints.api import api_bp  # 既存のAPI Blueprint
from blueprints.ui import ui_bp    # 新しく作成したUI Blueprint
from blueprints.auth import auth_bp # ★★★ auth_bp をインポート ★★★
app = Flask(__name__)
# 環境変数からSECRET_KEYを読み込む
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_strong_default_secret_key_for_dev_only_CHANGE_ME")

# ===== ロギング設定 =====
# (既存のロギング設定はそのまま、または必要に応じて調整)
for handler in app.logger.handlers[:]: 
    app.logger.removeHandler(handler)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(module)s:%(lineno)d]'
)
stream_handler.setFormatter(formatter)
app.logger.addHandler(stream_handler)
if os.environ.get('FLASK_DEBUG') == '1':
    app.debug = True
    app.logger.setLevel(logging.DEBUG)
    stream_handler.setLevel(logging.DEBUG)
else:
    app.debug = False
    app.logger.setLevel(logging.INFO)
    stream_handler.setLevel(logging.INFO)
app.logger.info("アプリケーションのロギングが初期化されました。")
app.logger.info(f"FLASK_DEBUG: {os.environ.get('FLASK_DEBUG')}, app.debug: {app.debug}")
# ===== ロギング設定ここまで =====


# --- Airtable関連の設定や直接的な関数定義は airtable_service.py に移動したのでここからは削除 ---
# AIRTABLE_TOKEN = ... (削除)
# AIRTABLE_BASE_ID = ... (削除)
# HEADERS = ... (削除)
# def send_record_to_destination(...): (削除)
# def get_selected_month_records(...): (削除)

# --- UI関連のルート定義は blueprints/ui.py に移動したのでここからは削除 ---
# @app.route("/", methods=["GET", "POST"]) def index(): ... (削除)
# @app.route("/records") def records(...): ... (削除)
# @app.route("/delete_record/<record_id>", methods=["POST"]) def delete_record(...): ... (削除)
# @app.route("/edit_record/<record_id>", methods=["GET", "POST"]) def edit_record(...): ... (削除)


# --- Google Sheets関連のデータロード関数定義も data_services.py に移動済みなので削除 ---
# def load_personid_data(): ... (削除)
# def get_cached_personid_data(): ... (削除)
# (他のload_* get_cached_* も同様に削除)


# --- APIルート定義も blueprints/api.py に移動済みなので削除 ---
# @app.route("/get_worknames", methods=["GET"]) def get_worknames(): ... (削除)
# @app.route("/get_unitprice", methods=["GET"]) def get_unitprice(): ... (削除)


# Blueprint を登録
app.register_blueprint(api_bp)  # 既存のAPI Blueprint (通常 /api プレフィックス付き)
app.register_blueprint(ui_bp)   # 新しいUI Blueprint (プレフィックスなし)
app.register_blueprint(auth_bp) # ★★★ auth_bp を登録 ★★★

if __name__ == "__main__":
    app.logger.info("アプリケーション起動: 初期データキャッシュを開始します...")
    try:
        # Flask開発サーバーのリロード時に二重実行を防ぐための一般的なチェック
        # (本番環境のGunicorn/Waitressでは通常この環境変数は設定されません)
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            app.logger.info("メインプロセスでのみ初期データロードを実行します。")
            with app.app_context(): # アプリケーションコンテキスト内で実行
                load_personid_data()
                load_workcord_data()
                load_workprocess_data()
            app.logger.info("初期データキャッシュが完了しました。")
        else:
            # Werkzeugのリローダーの子プロセスの場合など
            app.logger.info("リローダープロセスまたは既にロード済みのため、初期データロードをスキップします。")

    except Exception as e:
        app.logger.critical(f"アプリケーション起動時の初期データロードに失敗しました: {e}", exc_info=True)
        # 状況に応じて exit(1) などで終了させることも検討

    from waitress import serve
    port = int(os.environ.get("PORT", 10000))
    app.logger.info(f"Waitressサーバをポート {port} で起動します...")
    serve(app, host="0.0.0.0", port=port)