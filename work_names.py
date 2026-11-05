def normalize_workname(value: str | None) -> str:
    """品名の # 以降と前後の空白を除く。

    ただし先頭が # の品名（例: "#123 商品"）は # を品名の一部とみなし、
    前後の空白だけを除いてそのまま表示する。
    """
    text = str(value or "").strip()
    if text.startswith("#"):
        return text
    return text.split("#", 1)[0].strip()
