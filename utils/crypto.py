import tempfile
import subprocess
import json

def encrypt_body(payload_dict, key, iv):
    json_str = json.dumps(payload_dict, ensure_ascii=False, separators=(',', ':'))
    key_hex = key.encode().hex()
    iv_hex = iv.encode().hex()
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(json_str.encode())
        tf.flush()
        cmd = [
            'openssl', 'enc', '-aes-128-cbc', '-K', key_hex, '-iv', iv_hex, '-nosalt', '-base64', '-A', '-in', tf.name
        ]
        ciphertext = subprocess.check_output(cmd).decode()
    return ciphertext 