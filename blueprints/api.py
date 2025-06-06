from flask import Blueprint, jsonify, request, current_app # current_app をインポート
# data_services.py から必要な関数をインポート
# `your_flask_app` は実際のプロジェクトルートフォルダ名に置き換えてください
# もし `blueprints` フォルダが `data_services.py` と同じ階層の `your_flask_app` 内にある場合
from data_services import get_cached_workcord_data, get_cached_workprocess_data

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

@api_bp.route("/get_worknames", methods=["GET"])
def get_worknames():
    data = get_cached_workcord_data()
    workcd = request.args.get("workcd", "").strip()
    results = []

    if not workcd:
        return jsonify({"worknames": results, "error": ""})

    try:
        workcd_num = int(workcd)
        workcd = str(workcd_num) # 文字列として保持
    except ValueError:
        current_app.logger.warning(f"/api/get_worknames - 無効なWorkCDが指定されました: {workcd}")
        return jsonify({"worknames": [], "error": "WorkCDは数値で入力してください"})

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