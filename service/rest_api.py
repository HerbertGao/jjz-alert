"""
RESTful API for querying JJZ status for a single plate and pushing notification.
该 API 受 `global.remind.enable` 和 `global.remind.api.enable` 双重控制；只有两者均为 true 时才会启动。

Endpoints
---------
GET /health              Health check
POST /query              Body: {"plate": "京A12345"}
                        Trigger a query for the specified plate and send Bark push
"""

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import utils.logger  # noqa: F401
from config.config import get_jjz_accounts, get_plate_configs, load_yaml_config
from service.jjz_checker import check_jjz_status
from service.push_utils import push_plate, select_record
from service.traffic_limiter import traffic_limiter
from utils.parse import parse_status

app = FastAPI(title="JJZ Alert API", version="1.0.0")


class QueryRequest(BaseModel):
    plates: List[str] = Field(..., min_items=1, description="车牌号列表，如 [\"京A12345\", \"津B67890\"]")


@app.get("/health")
def health() -> Dict[str, str]:
    """Health check endpoint"""
    return {"status": "ok"}


@app.post("/query")
def query_plates(request: QueryRequest):
    """Trigger query & push for one or multiple plate numbers"""
    input_plates = [p.strip().upper() for p in request.plates if p.strip()]
    if not input_plates:
        raise HTTPException(status_code=400, detail="plates 不能为空")

    # Check if API is enabled
    if not is_api_enabled():
        raise HTTPException(status_code=403, detail="REST API 已关闭，请在配置中启用后再试")

    jjz_accounts = get_jjz_accounts()
    if not jjz_accounts:
        raise HTTPException(status_code=500, detail="未配置任何进京证账户")

    plate_configs = get_plate_configs()
    plate_config_dict = {cfg["plate"].upper(): cfg for cfg in plate_configs}

    missing = [p for p in input_plates if p not in plate_config_dict]
    if missing:
        raise HTTPException(status_code=404, detail=f"未找到车牌配置: {', '.join(missing)}")

    # Preload traffic-limiter cache to speed up check
    traffic_limiter.preload_cache()

    # Collect all jjz data
    all_jjz_data: List[Dict[str, Any]] = []
    for account in jjz_accounts:
        data = check_jjz_status(account["jjz_url"], account["jjz_token"])
        if "error" in data:
            raise HTTPException(status_code=502, detail=f"账户 {account['name']} 查询失败: {data['error']}")
        status_data = parse_status(data)
        all_jjz_data.extend(status_data)

    response_data: Dict[str, Any] = {}

    for plate_number in input_plates:
        target_records = [info for info in all_jjz_data if info["plate"].upper() == plate_number]
        plate_cfg = plate_config_dict[plate_number]

        if not target_records:
            response_data[plate_number] = {"records": 0, "push_results": []}
            continue

        selected = select_record(target_records)
        logging.info(f"REST API 推送，车牌 {plate_number} 选中记录: {selected}")

        push_results = push_plate(selected, plate_cfg)

        response_data[plate_number] = {
            "records": len(target_records),
            "push_results": push_results,
        }

    return response_data


def is_api_enabled() -> bool:
    conf = load_yaml_config() or {}
    remind_conf = conf.get("global", {}).get("remind", {})
    if not remind_conf.get("enable", False):
        return False
    api_conf = remind_conf.get("api", {})
    return api_conf.get("enable", False)


def run_api(host: str | None = None, port: int | None = None):
    """启动 REST API。

    - 如未显式传入 host/port，则从配置文件 `global.remind.api` 中读取；
    - 在配置被禁用时直接返回。
    """
    if not is_api_enabled():
        logging.warning("REST API 接口在配置中被禁用，未启动服务")
        return

    # 从配置读取默认 host/port
    conf = load_yaml_config() or {}
    api_conf = conf.get("global", {}).get("remind", {}).get("api", {})
    host = host or api_conf.get("host", "0.0.0.0")
    port = port or api_conf.get("port", 8000)

    import uvicorn

    logging.info(f"REST API 服务开始监听 {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    # 尝试从配置文件读取host/port
    conf = load_yaml_config() or {}
    api_conf = conf.get("global", {}).get("remind", {}).get("api", {})
    run_api(
        host=api_conf.get("host", "0.0.0.0"),
        port=api_conf.get("port", 8000),
    )
