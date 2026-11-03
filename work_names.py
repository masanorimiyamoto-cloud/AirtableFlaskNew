def normalize_workname(value: str | None) -> str:
    """品名の最初の # 以降と前後の空白を除く。"""
    return str(value or "").split("#", 1)[0].strip()
