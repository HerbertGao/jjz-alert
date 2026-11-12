"""对外查询令牌的匹配。

比较使用 SHA-256 摘要上的常数时间比较，避免令牌长度或前缀通过计时泄露。
本模块不记录令牌原文。
"""

import hashlib
import hmac
from typing import List, Optional

from jjz_alert.base.plate_utils import normalize_plate_number
from jjz_alert.config.config_models import ApiTokenConfig


def usable_api_tokens(tokens: Optional[List[ApiTokenConfig]]) -> List[ApiTokenConfig]:
    """丢掉空白令牌。配置里没有任何可用令牌时，查询接口必须拒绝全部请求。"""
    usable: List[ApiTokenConfig] = []
    for item in tokens or []:
        secret = (item.token or "").strip()
        if not secret:
            continue
        usable.append(item)
    return usable


def match_api_token(
    presented: str, tokens: Optional[List[ApiTokenConfig]]
) -> Optional[ApiTokenConfig]:
    """在已配置令牌中查找与 presented 相同的一项。

    空字符串不会命中。无论是否提前命中，都会把全部候选比较完。
    """
    presented = (presented or "").strip()
    candidates = usable_api_tokens(tokens)
    if not presented or not candidates:
        return None

    presented_digest = hashlib.sha256(presented.encode("utf-8")).digest()
    matched: Optional[ApiTokenConfig] = None
    for item in candidates:
        candidate_digest = hashlib.sha256(item.token.strip().encode("utf-8")).digest()
        if hmac.compare_digest(presented_digest, candidate_digest):
            matched = item
    return matched


def token_allows_plate(entry: ApiTokenConfig, plate: str) -> bool:
    """车牌是否落在该令牌的允许范围内。比较前按查询入口的规则规范化。"""
    normalized = normalize_plate_number(plate)
    if not normalized:
        return False
    allowed = {normalize_plate_number(item) for item in entry.plates if item}
    return normalized in allowed
