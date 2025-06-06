# blueprints/auth.py
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, session, current_app
)
from functools import wraps
from werkzeug.security import check_password_hash # PINのハッシュ比較に使用

# data_services.py から PersonID とPINハッシュ情報を取得する関数をインポート
from data_services import get_cached_personid_data

auth_bp = Blueprint(
    'auth_bp', __name__,
    url_prefix='/auth', # 認証関連のルートは /auth で始まるようにする
    template_folder='../templates' # templatesフォルダはプロジェクトルートにあるものを参照
)

def login_required(f):
    """
    ログインが必要なルートに適用するデコレータ。
    未ログインの場合はログインページにリダイレクトする。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in_personid' not in session:
            flash("このページにアクセスするにはログインが必要です。", "warning")
            # nextパラメータで行こうとしていたURLを記憶し、ログイン後にそこにリダイレクトする (オプション)
            return redirect(url_for('auth_bp.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        person_id_str = request.form.get('personid')
        pin_entered = request.form.get('pin')
        next_url = request.form.get('next_url', url_for('ui_bp.index')) # ログイン後のリダイレクト先

        if not person_id_str or not pin_entered:
            flash("PersonIDとPINの両方を入力してください。", "error")
            return redirect(url_for('.login')) # エラー時は再度ログインページへ

        try:
            person_id = int(person_id_str)
        except ValueError:
            flash("無効なPersonID形式です。", "error")
            return redirect(url_for('.login'))

        person_data_dict, _ = get_cached_personid_data() # PERSON_ID_DICT を取得
        user_account_info = person_data_dict.get(person_id)

        if user_account_info and user_account_info.get('pin_hash'):
            # PINハッシュを比較
            if check_password_hash(user_account_info['pin_hash'], pin_entered):
                session['logged_in_personid'] = person_id
                session['logged_in_personname'] = user_account_info['name']
                session.permanent = True # セッションを持続させる場合（設定による）
                
                current_app.logger.info(f"ログイン成功: PersonID={person_id}, Name={user_account_info['name']}")
                flash(f"{user_account_info['name']}さん、ようこそ！", "success")
                
                # "next" パラメータがあればそこにリダイレクト、なければデフォルトのページへ
                # 安全なリダイレクトのためには is_safe_url のようなチェックを挟むのが望ましい
                if next_url and next_url.startswith('/'): # 簡単なチェック
                     return redirect(next_url)
                return redirect(url_for('ui_bp.index')) # デフォルトはメインページへ
            else:
                current_app.logger.warning(f"PIN不一致: PersonID={person_id}")
                flash("PersonIDまたはPINが間違っています。", "error")
        else:
            current_app.logger.warning(f"アカウント情報またはPINハッシュが見つかりません: PersonID={person_id}")
            flash("PersonIDまたはPINが間違っています。", "error")
        
        # 認証失敗時は再度ログインページを表示（エラーメッセージはflashで表示される）
        # personid_dictを再度渡す必要がある
        personid_dict_for_template, _ = get_cached_personid_data() 
        return render_template('login.html', personid_dict=personid_dict_for_template, next_url=next_url)


    # GETリクエストの場合
    if 'logged_in_personid' in session: # 既にログイン済みならメインページへ
        return redirect(url_for('ui_bp.index'))
        
    personid_dict_for_template, _ = get_cached_personid_data()
    next_url_from_query = request.args.get('next', '') # リダイレクト元から渡されたnext URLを取得

    # blueprints/auth.py の login 関数のGETリクエスト処理の最後
    # return render_template('login.html', ...) の直前に追加
    current_app.logger.debug(f"login.htmlへ渡す personid_dict: {personid_dict_for_template}") # personid_dict_for_template は実際に渡す変数名
    
    return render_template('login.html', personid_dict=personid_dict_for_template, next_url=next_url_from_query)


@auth_bp.route('/logout')
@login_required # ログアウト操作はログインしているユーザーのみが行える
def logout():
    logged_out_name = session.pop('logged_in_personname', 'ゲスト') # 名前を先に取得
    session.pop('logged_in_personid', None)
    
    current_app.logger.info(f"ログアウト: Name={logged_out_name}")
    flash(f"{logged_out_name}さん、ログアウトしました。", "info")
    return redirect(url_for('.login')) # ログインページへリダイレクト