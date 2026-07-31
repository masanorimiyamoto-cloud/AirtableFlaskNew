# tools/check_sheet.py
"""品番コード検索が「該当なし」になったときの原因切り分けスクリプト。

使い方（アプリと同じフォルダ・同じ認証ファイルがある場所で実行）:

    python tools/check_sheet.py            # 全体を点検
    python tools/check_sheet.py 1555       # 特定の品番コードを追跡

Google Sheets のどこが壊れているのか（共有設定 / シート名 / ヘッダー行 /
セルの表示形式）を順番に確認して表示する。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_services as ds


def _col_letter(n):
    """1 -> A, 17 -> Q, 33 -> AG"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 70)
    print("1) 認証ファイル")
    print(f"   SERVICE_ACCOUNT_FILE = {ds.SERVICE_ACCOUNT_FILE}")
    print(f"   存在するか           = {os.path.exists(ds.SERVICE_ACCOUNT_FILE)}")
    if not ds.client:
        print("   ❌ Google Sheets クライアントを初期化できていません。ここが原因です。")
        return 1
    print("   ✅ クライアント初期化 OK")

    print("=" * 70)
    print("2) スプレッドシートを開く")
    try:
        ss = ds.open_spreadsheet()
    except Exception as e:
        print(f"   ❌ 開けません: {type(e).__name__}: {e}")
        print("   → サービスアカウントへの共有が外れた / ファイル名が変わった 可能性が高い。")
        print(f"      サービスアカウントのメールアドレスに編集権限（最低でも閲覧）を付け直してください。")
        return 1
    print(f"   ✅ タイトル = {ss.title}")
    print(f"      キー     = {ss.id}")

    print("=" * 70)
    print("3) シート(タブ)一覧")
    titles = [ws.title for ws in ss.worksheets()]
    for t in titles:
        print(f"   - '{t}'")
    if ds.WORKSHEET_NAME not in titles:
        print(f"   ❌ '{ds.WORKSHEET_NAME}' がありません。タブ名が変更された可能性があります。")
        return 1
    print(f"   ✅ '{ds.WORKSHEET_NAME}' あり")

    ws = ss.worksheet(ds.WORKSHEET_NAME)

    print("=" * 70)
    print("4) ヘッダー行 (1行目)")
    header = ws.row_values(1)
    for i, h in enumerate(header, start=1):
        print(f"   列{i:>2}: '{h}'")
    for need in ds.WORKCORD_EXPECTED_HEADERS:
        mark = "✅" if need in header else "❌"
        print(f"   {mark} '{need}' 列")
    blanks = [i for i, h in enumerate(header, start=1) if not h.strip()]
    if blanks:
        print(f"   ⚠ 空欄のヘッダーがある列: {blanks}")

    print("=" * 70)
    print("5) ヘッダーより右にはみ出した値の検出  ★今回の原因になりやすい箇所")
    all_values = ws.get_all_values()
    width = max(len(r) for r in all_values) if all_values else 0
    print(f"   ヘッダーの列数 = {len(header)} / シートの最大列数 = {width}")
    if width > len(header):
        print(f"   ❌ ヘッダーのない列({_col_letter(len(header) + 1)}列以降)に値が入っています。")
        print("      gspread は空ヘッダーが重複するとエラーになり、品番マスタが1件も読めなくなります。")
        for row_no, row in enumerate(all_values, start=1):
            extra = [(i, v) for i, v in enumerate(row[len(header):], start=len(header) + 1) if str(v).strip()]
            if extra:
                cells = ", ".join(f"{_col_letter(i)}{row_no}='{v}'" for i, v in extra[:5])
                print(f"      行{row_no}: {cells}")
    else:
        print("   ✅ はみ出しなし")

    print("=" * 70)
    print("6) get_all_records() の実行")
    try:
        records = ws.get_all_records(
            expected_headers=ds.WORKCORD_EXPECTED_HEADERS,
            value_render_option=ds.UNFORMATTED,
        )
    except Exception as e:
        print(f"   ❌ 失敗: {type(e).__name__}: {e}")
        return 1
    print(f"   ✅ {len(records)} 行を読み込みました")

    print("=" * 70)
    print("7) アプリと同じ辞書を組み立てる")
    ds.load_workcord_data()
    err = ds.get_workcord_load_error()
    if err:
        print(f"   ❌ ロード失敗: {err}")
        return 1
    d = ds.get_cached_workcord_data()
    print(f"   ✅ 品番コード {len(d)} 種類 / 品名 {sum(len(v) for v in d.values())} 件")
    sample = list(d.items())[:5]
    for code, items in sample:
        print(f"      例: '{code}' -> {items[0]['workname']}")

    if target:
        print("=" * 70)
        print(f"8) 品番コード '{target}' を追跡")
        key = ds.normalize_workcord(target)
        raw_hits = [
            r for r in records
            if ds.normalize_workcord(r.get("WorkCord")) == key
        ]
        if raw_hits:
            for r in raw_hits:
                print(f"   シート上の生の値: WorkCord={r.get('WorkCord')!r} "
                      f"({type(r.get('WorkCord')).__name__}), "
                      f"WorkName={r.get('WorkName')!r}, BookName={r.get('BookName')!r}")
        else:
            print(f"   ❌ シート内に WorkCord={key} の行が見つかりません。")
            print("      → 行が消えた / 別のタブに移動した 可能性があります。")

        print(f"   完全一致(アプリの辞書): {d.get(key)}")
        prefix = key[:3]
        pref_hits = sorted(k for k in d if k.startswith(prefix))
        print(f"   前方一致 '{prefix}' の候補 {len(pref_hits)} 件: {pref_hits[:20]}")
        if not pref_hits:
            print("   ❌ 前方一致でも0件。画面では「該当する品名がありません」と表示されます。")

    print("=" * 70)
    print("点検完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
