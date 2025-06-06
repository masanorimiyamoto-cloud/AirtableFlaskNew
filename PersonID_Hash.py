# このコードをローカルで実行してハッシュ値を生成します
from werkzeug.security import generate_password_hash

pin_to_hash = '1111'  # ここに実際のPINコードを入力
hashed_pin = generate_password_hash(pin_to_hash)
print(f"PIN '{pin_to_hash}' のハッシュ値: {hashed_pin}")