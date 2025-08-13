import json
import subprocess
import tempfile
import hashlib


def encrypt_body(
    payload_dict,
    key: str,
    iv: str | None,
    algorithm: str = "AES128",
    mode: str = "CBC",
    padding: str = "pkcs7",
):
    """将 payload_dict 加密并返回 Base64 字符串

    参数说明：
    1. algorithm: AES128 / AES192 / AES256，默认 AES128
    2. mode: CBC / ECB / GCM，默认 CBC
    3. padding: 目前仅支持 pkcs7，占位参数，保留扩展
    """

    # 构造 openssl cipher 名称，例如 aes-128-cbc
    # 若调用方传入 None，则使用默认值
    if not algorithm:
        algorithm = "AES128"
    if not mode:
        mode = "CBC"
    if not padding:
        padding = "pkcs7"

    alg = algorithm.upper()
    mode_u = mode.upper()

    if alg not in {"AES128", "AES192", "AES256"}:
        raise ValueError(f"不支持的算法: {algorithm}")
    if mode_u not in {"CBC", "ECB", "GCM"}:
        raise ValueError(f"不支持的工作模式: {mode}")
    if padding.lower() != "pkcs7":
        raise ValueError(f"暂不支持的填充方式: {padding}")

    key_bits = alg.replace("AES", "")  # 128 / 192 / 256

    cipher_name = f"-aes-{key_bits}-{mode.lower()}"

    json_str = json.dumps(payload_dict, ensure_ascii=False, separators=(",", ":"))
    key_hex = key.encode().hex()
    iv_hex = (iv.encode().hex() if iv else "")

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(json_str.encode())
        tf.flush()
        cmd = ["openssl", "enc", cipher_name, "-K", key_hex, "-nosalt", "-base64", "-A", "-in", tf.name]
        # 无论 ECB 与否，只要提供了 IV 就带上；若算法需要但未提供则报错
        if iv_hex:
            cmd.extend(["-iv", iv_hex])
        elif mode_u != "ECB":
            raise ValueError("当前模式需要 iv，但未提供")
        ciphertext = subprocess.check_output(cmd).decode()
    return ciphertext


def generate_md5(text: str) -> str:
    """生成字符串的MD5值
    
    Args:
        text: 要计算MD5的字符串
        
    Returns:
        MD5哈希值的十六进制字符串
    """
    return hashlib.md5(text.encode('utf-8')).hexdigest() 