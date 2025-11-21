"""
Home Assistant MQTT Discovery 发布模块（最小可用）

功能：
- 通过 MQTT Discovery 自动注册传感器
- 发布合并传感器的 state 与 attributes
- 使用 retain + QoS 1，确保 HA 重启后能恢复
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from jjz_alert.config.config import get_homeassistant_config
from jjz_alert.base.plate_utils import (
    normalize_plate_for_ha_entity_id,
    extract_province_from_plate,
)
from jjz_alert.service.homeassistant.mqtt_config import MQTTConfig

# 尝试导入 gmqtt（推荐）或 asyncio-mqtt（备用）
try:
    import gmqtt
    from gmqtt import Client as GMQTTClient

    MQTT_AVAILABLE = True
    MQTT_LIB = "gmqtt"
except ImportError:
    try:
        from asyncio_mqtt import Client as AsyncMQTTClient, MqttError

        MQTT_AVAILABLE = True
        MQTT_LIB = "asyncio-mqtt"
    except ImportError:
        MQTT_AVAILABLE = False
        MQTT_LIB = None
        AsyncMQTTClient = None
        MqttError = Exception


def _get_mqtt_config() -> Optional[MQTTConfig]:
    cfg = get_homeassistant_config()
    # 仅当 integration_mode == 'mqtt' 时启用
    mode = getattr(cfg, "integration_mode", "rest").lower()
    if mode != "mqtt":
        return None
    return MQTTConfig(
        host=cfg.mqtt_host,
        port=cfg.mqtt_port,
        username=cfg.mqtt_username,
        password=cfg.mqtt_password,
        client_id=cfg.mqtt_client_id,
        discovery_prefix=cfg.mqtt_discovery_prefix or "homeassistant",
        base_topic=cfg.mqtt_base_topic or "jjz_alert",
        qos=cfg.mqtt_qos if isinstance(cfg.mqtt_qos, int) else 1,
        retain=bool(cfg.mqtt_retain),
    )


class HAMQTTPublisher:
    def __init__(self):
        self._cfg = _get_mqtt_config()
        self._client = None
        self._connecting: bool = False

    def enabled(self) -> bool:
        return self._cfg is not None and MQTT_AVAILABLE

    def _log_debug(self, message: str, **kwargs):
        """输出 debug 级别日志（同步函数）"""
        extra_data = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        logging.debug(f"[MQTT] {message} {extra_data}".strip())

    async def _ensure_client(self):
        if not self.enabled():
            self._log_debug("MQTT 未启用或依赖缺失")
            return None
        if self._client:
            return self._client
        if self._connecting:
            # 另一个协程在连接，稍等
            for _ in range(20):
                await asyncio.sleep(0.05)
                if self._client:
                    return self._client
            return None
        try:
            self._connecting = True
            self._log_debug(
                "创建新的 MQTT 客户端连接",
                host=self._cfg.host,
                port=self._cfg.port,
                client_id=self._cfg.client_id,
                lib=MQTT_LIB,
            )

            if MQTT_LIB == "gmqtt":
                # 使用 gmqtt
                client = GMQTTClient(self._cfg.client_id)
                if self._cfg.username:
                    client.set_auth_credentials(self._cfg.username, self._cfg.password)
                await client.connect(self._cfg.host, self._cfg.port)
            else:
                # 使用 asyncio-mqtt
                client = AsyncMQTTClient(
                    hostname=self._cfg.host,
                    port=self._cfg.port,
                    username=self._cfg.username,
                    password=self._cfg.password,
                    client_id=self._cfg.client_id,
                )
                await client.connect()

            self._client = client
            self._log_debug("MQTT 客户端连接成功")
            await self._publish_availability("online")
            self._log_debug("发布在线状态")
            return self._client
        except Exception as e:
            logging.error(f"MQTT连接失败: {e}")
            self._log_debug("MQTT 连接失败", error=str(e))
            self._client = None
            return None
        finally:
            self._connecting = False

    async def close(self):
        try:
            if self._client:
                self._log_debug("关闭 MQTT 客户端连接")
                try:
                    # 先发布离线状态，但不等待结果
                    await self._publish_availability("offline")
                    self._log_debug("发布离线状态")
                except Exception as e:
                    self._log_debug("发布离线状态失败", error=str(e))

                try:
                    if MQTT_LIB == "gmqtt":
                        # 对于 gmqtt，确保正确断开连接
                        if hasattr(self._client, "disconnect"):
                            await self._client.disconnect()
                        # 清理内部状态
                        if hasattr(self._client, "_cleanup"):
                            self._client._cleanup()
                    else:
                        await self._client.disconnect()
                except Exception as e:
                    self._log_debug("断开 MQTT 连接时出错", error=str(e))
                finally:
                    self._client = None
                    self._log_debug("MQTT 客户端已关闭")
        except Exception as e:
            self._log_debug("关闭 MQTT 客户端时出错", error=str(e))
            # 确保客户端被重置
            self._client = None

    async def _publish(
        self,
        topic: str,
        payload: Any,
        qos: Optional[int] = None,
        retain: Optional[bool] = None,
    ):
        client = await self._ensure_client()
        if not client:
            self._log_debug("无法获取 MQTT 客户端，跳过发布", topic=topic)
            return False

        # 检查连接状态（仅对 gmqtt）
        if (
            MQTT_LIB == "gmqtt"
            and hasattr(client, "is_connected")
            and not client.is_connected
        ):
            self._log_debug("MQTT 连接已断开，重置客户端", topic=topic)
            self._client = None
            client = await self._ensure_client()
            if not client:
                self._log_debug("重新连接失败，跳过发布", topic=topic)
                return False

        qos_val = self._cfg.qos if qos is None else qos
        retain_val = self._cfg.retain if retain is None else retain
        try:
            if not isinstance(payload, (str, bytes)):
                payload = json.dumps(payload, ensure_ascii=False)
            self._log_debug(
                "发布 MQTT 消息",
                topic=topic,
                qos=qos_val,
                retain=retain_val,
                payload_length=len(str(payload)),
            )

            if MQTT_LIB == "gmqtt":
                client.publish(topic, payload, qos=qos_val, retain=retain_val)
            else:
                await client.publish(topic, payload, qos=qos_val, retain=retain_val)

            self._log_debug("MQTT 消息发布成功", topic=topic)
            return True
        except Exception as e:
            logging.error(f"MQTT发布失败 {topic}: {e}")
            self._log_debug("MQTT 消息发布失败", topic=topic, error=str(e))
            # 如果是连接相关错误，重置客户端
            if "socket" in str(e).lower() or "connection" in str(e).lower():
                self._log_debug("检测到连接错误，重置 MQTT 客户端")
                self._client = None
            return False

    async def _publish_availability(self, status: str):
        topic = f"{self._cfg.base_topic}/status"
        self._log_debug("发布可用性状态", topic=topic, status=status)
        await self._publish(topic, status, qos=1, retain=True)

    def _topics_for_plate(self, plate_number: str, display_name: str) -> Dict[str, str]:
        province_cn, province_py = extract_province_from_plate(plate_number)
        normalized_plate = normalize_plate_for_ha_entity_id(plate_number)
        object_id = (
            f"{province_py}_{normalized_plate[len(province_py):]}"
            if province_py
            else normalized_plate
        )
        object_id = object_id.strip("_")

        # entity_id 与 object_id 保持一致的小写风格
        entity_id = f"sensor.{self._cfg.base_topic}_{object_id}"

        # Discovery config 主题
        config_topic = f"{self._cfg.discovery_prefix}/sensor/{self._cfg.base_topic}_{object_id}/config"
        # 状态与属性主题
        state_topic = f"{self._cfg.base_topic}/sensor/{object_id}/state"
        attr_topic = f"{self._cfg.base_topic}/sensor/{object_id}/attributes"

        self._log_debug(
            "生成车牌主题", plate=plate_number, object_id=object_id, entity_id=entity_id
        )

        return {
            "entity_id": entity_id,
            "config": config_topic,
            "state": state_topic,
            "attr": attr_topic,
            "object_id": object_id,
            "province_cn": province_cn,
            "province_py": province_py,
            "normalized_plate": normalized_plate,
            "display_name": display_name,
        }

    async def publish_discovery_and_state(
        self,
        plate_number: str,
        display_name: str,
        state: str,
        attributes: Dict[str, Any],
    ):
        if not self.enabled():
            self._log_debug("MQTT 未启用，跳过发布", plate=plate_number)
            return False

        topics = self._topics_for_plate(plate_number, display_name)
        self._log_debug(
            "开始发布车牌 Discovery 与状态",
            plate=plate_number,
            display_name=display_name,
            state=state,
        )

        # Discovery 配置
        device_info = {
            "identifiers": [f"jjz_alert_{topics['normalized_plate']}"],
            "name": f"进京证监控 {display_name}",
            "model": "Beijing Vehicle",
            "manufacturer": "JJZ Alert",
            "sw_version": "2.0",
        }

        config_payload = {
            "name": f"进京证与限行状态 - {display_name}",
            "object_id": f"{self._cfg.base_topic}_{topics['object_id']}",
            "unique_id": f"{self._cfg.base_topic}_{topics['object_id']}",
            "state_topic": topics["state"],
            "json_attributes_topic": topics["attr"],
            "availability_topic": f"{self._cfg.base_topic}/status",
            "icon": "mdi:car",
            "device": device_info,
        }

        self._log_debug(
            "发布 Discovery 配置",
            topic=topics["config"],
            unique_id=config_payload["unique_id"],
        )
        # 先发布 discovery 配置（retain）
        ok_cfg = await self._publish(
            topics["config"], config_payload, qos=1, retain=True
        )
        if not ok_cfg:
            return False

        # 格式化属性中的有效期日期（使用 utils.jjz_utils.format_valid_dates）
        try:
            from jjz_alert.service.jjz.jjz_utils import format_valid_dates

            s = attributes.get("jjz_valid_start")
            e = attributes.get("jjz_valid_end")
            fs, fe = format_valid_dates(s, e)
            attributes["jjz_valid_start"], attributes["jjz_valid_end"] = fs, fe
        except Exception:
            pass

        self._log_debug(
            "发布属性", topic=topics["attr"], attributes_count=len(attributes)
        )
        ok_attr = await self._publish(topics["attr"], attributes, qos=1, retain=True)
        if not ok_attr:
            return False

        self._log_debug("发布状态", topic=topics["state"], state=state)
        ok_state = await self._publish(topics["state"], state, qos=1, retain=True)
        if not ok_state:
            return False

        self._log_debug("车牌 MQTT 发布完成", plate=plate_number)
        return True


# 全局实例
ha_mqtt_publisher = HAMQTTPublisher()
