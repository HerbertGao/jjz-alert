"""
MQTT配置数据模型
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MQTTConfig:
    """MQTT配置"""

    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    client_id: str
    discovery_prefix: str
    base_topic: str
    qos: int
    retain: bool

