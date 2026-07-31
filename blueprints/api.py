from flask import Blueprint, jsonify, request, current_app # current_app をインポート
# data_services.py から必要な関数をインポート
# `your_flask_app` は実際のプロジェクトルートフォルダ名に置き換えてください
# もし `blueprints` フォルダが `data_services.py` と同じ階層の `your_flask_app` 内にある場合
from data_services import (
    get_cached_workcord_data,
    get_cached_workprocess_data,
    get_workcord_load_error,
    normalize_workcord,
)

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

@api_bp.route("/get_worknames", methods=["GET"])
def get_worknames():
    data = get_cached_workcord_data()
    workcd = request.args.get("workcd", "").strip()
    results = []

    if not workcd:
        return jsonify({"worknames": results, "error": ""})

    try:
        # 先頭の0を落とす（マスタ側も数値化して保持しているため）
        workcd = str(int(normalize_workcord(workcd)))
    except ValueError:
        current_app.logger.warning(f"/api/get_worknames - 無効なWorkCDが指定されました: {workcd}")
        return jsonify({"worknames": [], "error": "WorkCDは数値で入力してください"})

    # ★ 品番マスタ自体が読めていない場合は「該当なし」ではなくエラーとして返す
    #   （原因不明のまま「該当する品名がありません」と表示されるのを防ぐ）
    load_error = get_workcord_load_error()
    if load_error and not data:
        current_app.logger.error(f"/api/get_worknames - 品番マスタが読み込めていません: {load_error}")
        return jsonify({
            "worknames": [],
            "error": "品番マスタ(Google Sheets)を読み込めていません。管理者に連絡してください。"
        })

    # 部分一致検索ロジック
    if len(workcd) >= 3:
        # 完全一致を優先
        if workcd in data:
            for item in data[workcd]:
                results.append({
                    "code": workcd,
                    "workname": item["workname"],
                    "bookname": item["bookname"]
                })
        
        # 部分一致検索（前方一致）
        for key in data.keys():
            if key.startswith(workcd) and key != workcd: # 完全一致の結果と重複しないように
                for item in data[key]:
                    results.append({
                        "code": key,
                        "workname": item["workname"],
                        "bookname": item["bookname"]
                    })
    
    current_app.logger.info(f"/api/get_worknames - WorkCD: {workcd}, Results: {len(results)}件")
    return jsonify({"worknames": results, "error": ""})


@api_bp.route("/get_unitprice", methods=["GET"])
def get_unitprice():
    workprocess = request.args.get("workprocess", "").strip()
    if not workprocess:
        current_app.logger.warning("/api/get_unitprice - WorkProcessが指定されていません。")
        return jsonify({"error": "WorkProcess が指定されていません"}), 400

    _, up_dict = get_cached_workprocess_data() # 第1返り値(リスト)は不要なので _ で受ける

    if workprocess not in up_dict:
        current_app.logger.warning(f"/api/get_unitprice - 該当するWorkProcessが見つかりません: {workprocess}")
        return jsonify({"error": "該当する WorkProcess が見つかりません"}), 404
    
    unitprice = up_dict[workprocess]
    current_app.logger.info(f"/api/get_unitprice - WorkProcess: {workprocess}, UnitPrice: {unitprice}")
    return jsonify({"unitprice": unitprice})