"""GET /permit：按令牌绑定的车牌查询最新进京证。"""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import rest_api
from jjz_alert.config.api_tokens import match_api_token
from jjz_alert.config.config_models import ApiTokenConfig, AppConfig
from jjz_alert.service.jjz.jjz_service import jjz_service
from jjz_alert.service.jjz.jjz_status import JJZStatus
from jjz_alert.service.jjz.permit_lookup import is_permit_missing, to_permit_payload
from jjz_alert.service.traffic.traffic_models import PlateTrafficStatus, TrafficRule
from jjz_alert.service.traffic.traffic_service import traffic_service

TOKEN = "replace-with-your-api-token"
OTHER_TOKEN = "replace-with-another-api-token"
PLATE = "京A00000"
OTHER_PLATE = "京B00000"


def _config_with_tokens(tokens):
    config = AppConfig()
    config.global_config.remind.enable = True
    config.global_config.remind.api.enable = True
    config.global_config.remind.api.tokens = tokens
    return config


def _status(**overrides):
    payload = dict(
        plate=PLATE,
        status="valid",
        valid_start="2026-11-01",
        valid_end="2026-11-20",
        days_remaining=8,
        jjzzlmc="进京证(六环内)",
        blztmc="审核通过(生效中)",
    )
    payload.update(overrides)
    return JJZStatus(**payload)


@pytest.fixture
def client():
    with TestClient(rest_api.app) as test_client:
        yield test_client


def _use_config(monkeypatch, tokens):
    config = _config_with_tokens(tokens)
    monkeypatch.setattr(
        rest_api.config_manager, "load_config", lambda force_reload=False: config
    )
    return config


def _mock_lookup(monkeypatch, status):
    lookup = AsyncMock(return_value=status)
    monkeypatch.setattr(jjz_service, "get_jjz_status", lookup)
    return lookup


def _traffic_status(*, is_limited=False, error_message=None, with_rule=True):
    rule = None
    if with_rule and not error_message:
        rule = TrafficRule(
            date=date(2026, 11, 12),
            limited_numbers="1和6" if is_limited else "不限行",
            limited_time="2026年11月12日",
            is_limited=is_limited,
        )
    return PlateTrafficStatus(
        plate=PLATE,
        date=date(2026, 11, 12),
        is_limited=is_limited,
        tail_number="0",
        rule=rule,
        error_message=error_message,
    )


@pytest.fixture(autouse=True)
def traffic_lookup(monkeypatch):
    lookup = AsyncMock(return_value=_traffic_status(is_limited=False))
    monkeypatch.setattr(traffic_service, "check_plate_limited", lookup)
    return lookup


@pytest.mark.unit
class TestPermitLookupApi:
    def test_success_for_plate_in_token_scope(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(
            monkeypatch,
            [ApiTokenConfig(token=TOKEN, plates=[PLATE, OTHER_PLATE])],
        )
        lookup = _mock_lookup(
            monkeypatch,
            _status(sycs="6", reject_reason=""),
        )
        traffic_lookup.return_value = _traffic_status(is_limited=True)

        response = client.get(
            "/permit",
            params={"plate": "  京a00000  "},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "plate": PLATE,
            "type": "六环内",
            "type_name": "进京证(六环内)",
            "status": "valid",
            "status_name": "审核通过(生效中)",
            "valid_from": "2026-11-01",
            "valid_until": "2026-11-20",
            "days_remaining": 8,
            "remaining_count": 6,
            "reject_reason": None,
            "traffic_limited_today": True,
        }
        lookup.assert_awaited_once_with(PLATE)
        traffic_lookup.assert_awaited_once_with(PLATE)
        assert TOKEN not in response.text

    def test_nullable_fields_stay_null(self):
        payload = to_permit_payload(
            JJZStatus(plate=PLATE, status="pending", blztmc="审核中"),
            PLATE,
        )

        assert payload["type"] is None
        assert payload["type_name"] is None
        assert payload["status"] == "pending"
        assert payload["status_name"] == "审核中"
        assert payload["valid_from"] is None
        assert payload["valid_until"] is None
        assert payload["days_remaining"] is None
        assert payload["remaining_count"] is None
        assert payload["reject_reason"] is None
        assert payload["traffic_limited_today"] is None

    def test_401_does_not_log_the_plate(self, client, monkeypatch, traffic_lookup):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(rest_api.structured_logger, "log_api_call", capture_call)

        response = client.get("/permit", params={"plate": PLATE})

        assert response.status_code == 401
        assert captured["extra_data"]["query_params"]["plate"] == "<redacted>"
        assert PLATE not in str(captured)
        traffic_lookup.assert_not_awaited()

    def test_error_status_with_missing_message_is_not_404(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        collided = JJZStatus(
            plate=PLATE,
            status="error",
            error_message="未找到进京证记录",
        )
        assert is_permit_missing(collided) is False
        _mock_lookup(monkeypatch, collided)

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "进京证查询暂时不可用"
        traffic_lookup.assert_not_awaited()

    def test_401_when_token_missing(self, client, monkeypatch, traffic_lookup):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        lookup = _mock_lookup(monkeypatch, _status())

        response = client.get("/permit", params={"plate": PLATE})

        assert response.status_code == 401
        assert response.json()["detail"] == "缺少访问令牌"
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()

    def test_401_when_token_wrong(self, client, monkeypatch, traffic_lookup):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        lookup = _mock_lookup(monkeypatch, _status())

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": "Bearer not-the-configured-token"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "访问令牌无效"
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()
        assert "not-the-configured-token" not in response.text

    def test_401_when_bearer_token_empty(self, client, monkeypatch, traffic_lookup):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        lookup = _mock_lookup(monkeypatch, _status())

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": "Bearer    "},
        )

        assert response.status_code == 401
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()

    def test_401_when_configured_token_is_empty(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(
            monkeypatch,
            [ApiTokenConfig(token="   ", plates=[PLATE])],
        )
        lookup = _mock_lookup(monkeypatch, _status())

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 401
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()

    def test_401_when_no_tokens_configured(self, client, monkeypatch, traffic_lookup):
        _use_config(monkeypatch, [])
        lookup = _mock_lookup(monkeypatch, _status())

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 401
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()

    def test_403_when_plate_is_outside_token_scope(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(
            monkeypatch,
            [
                ApiTokenConfig(token=TOKEN, plates=[PLATE]),
                ApiTokenConfig(token=OTHER_TOKEN, plates=[OTHER_PLATE]),
            ],
        )
        # 即使另一辆车有记录，范围外的请求也不能拿到它，也不能因此走查询。
        lookup = _mock_lookup(
            monkeypatch,
            _status(
                plate=OTHER_PLATE, jjzzlmc="进京证(六环外)", blztmc="审核通过(生效中)"
            ),
        )

        response = client.get(
            "/permit",
            params={"plate": OTHER_PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "无权查询该车牌"}
        body = response.text
        assert "六环外" not in body
        assert "valid_from" not in body
        assert "remaining_count" not in body
        assert "reject_reason" not in body
        assert "traffic_limited_today" not in body
        assert PLATE not in body
        lookup.assert_not_awaited()
        traffic_lookup.assert_not_awaited()

    def test_404_when_plate_in_scope_has_no_permit(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        lookup = _mock_lookup(
            monkeypatch,
            JJZStatus(
                plate=PLATE,
                status="invalid",
                error_message="未找到匹配车牌的记录",
            ),
        )

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "未找到该车牌的进京证记录"
        assert OTHER_PLATE not in response.text
        lookup.assert_awaited_once_with(PLATE)
        traffic_lookup.assert_not_awaited()

    def test_lookup_failure_does_not_leak_upstream_detail(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        _mock_lookup(
            monkeypatch,
            JJZStatus(
                plate=PLATE,
                status="error",
                error_message="upstream token rejected",
            ),
        )

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "进京证查询暂时不可用"
        assert "upstream" not in response.text
        assert TOKEN not in response.text
        traffic_lookup.assert_not_awaited()

    def test_openapi_lists_contract_fields(self, client):
        schema = client.get("/openapi.json").json()
        properties = schema["components"]["schemas"]["PermitResponse"]["properties"]

        assert set(properties) == {
            "plate",
            "type",
            "type_name",
            "status",
            "status_name",
            "valid_from",
            "valid_until",
            "days_remaining",
            "remaining_count",
            "reject_reason",
            "traffic_limited_today",
        }
        assert properties["type"]["description"] == "进京证类型"
        assert properties["type_name"]["description"] == "中文名称"
        assert properties["status"]["description"] == "当前状态"
        assert properties["status_name"]["description"] == "中文状态"
        assert properties["valid_from"]["description"] == "有效期起始日期"
        assert properties["valid_until"]["description"] == "有效期截止日期"
        assert properties["days_remaining"]["description"] == "剩余有效日历天数"
        assert properties["remaining_count"]["description"] == "六环内进京证剩余次数"
        assert properties["reject_reason"]["description"] == "审核不通过原因"
        assert properties["traffic_limited_today"]["description"] == "当日是否限行"
        assert {"type": "integer"} in properties["days_remaining"]["anyOf"]
        assert {"type": "integer"} in properties["remaining_count"]["anyOf"]
        assert {"type": "boolean"} in properties["traffic_limited_today"]["anyOf"]
        assert {"type": "null"} in properties["type"]["anyOf"]
        assert {"type": "null"} in properties["reject_reason"]["anyOf"]
        assert {"type": "null"} in properties["traffic_limited_today"]["anyOf"]
        assert properties["status"]["type"] == "string"

    def test_rejected_permit_is_not_a_missing_record(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        traffic_lookup.return_value = _traffic_status(is_limited=False)
        _mock_lookup(
            monkeypatch,
            _status(
                status="invalid",
                jjzzlmc="进京证(六环外)",
                blztmc="失败(审核不通过)",
                valid_start="",
                valid_end="",
                days_remaining=None,
                sycs="0",
                reject_reason="审核未通过",
            ),
        )

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "invalid"
        assert body["status_name"] == "失败(审核不通过)"
        assert body["type"] == "六环外"
        assert body["type_name"] == "进京证(六环外)"
        assert body["valid_from"] is None
        assert body["days_remaining"] is None
        assert body["remaining_count"] == 0
        assert body["reject_reason"] == "审核未通过"
        assert body["traffic_limited_today"] is False

    def test_traffic_failure_keeps_permit_payload(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        _mock_lookup(monkeypatch, _status(sycs="3"))
        traffic_lookup.return_value = _traffic_status(
            is_limited=False,
            error_message="upstream traffic unavailable",
            with_rule=False,
        )

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "valid"
        assert body["days_remaining"] == 8
        assert body["remaining_count"] == 3
        assert body["traffic_limited_today"] is None
        assert "upstream" not in response.text
        assert "unavailable" not in response.text

    def test_traffic_exception_keeps_permit_payload(
        self, client, monkeypatch, traffic_lookup
    ):
        _use_config(monkeypatch, [ApiTokenConfig(token=TOKEN, plates=[PLATE])])
        _mock_lookup(monkeypatch, _status(sycs=None, reject_reason=None))
        traffic_lookup.side_effect = RuntimeError("traffic backend secret")

        response = client.get(
            "/permit",
            params={"plate": PLATE},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["remaining_count"] is None
        assert body["reject_reason"] is None
        assert body["traffic_limited_today"] is None
        assert body["type"] == "六环内"
        assert "secret" not in response.text
        assert "RuntimeError" not in response.text


@pytest.mark.unit
class TestApiTokenMatch:
    def test_matches_exact_token_only(self):
        tokens = [
            ApiTokenConfig(token=TOKEN, plates=[PLATE]),
            ApiTokenConfig(token=OTHER_TOKEN, plates=[OTHER_PLATE]),
        ]

        assert match_api_token(TOKEN, tokens).plates == [PLATE]
        assert match_api_token(TOKEN + "-extra", tokens) is None
        assert match_api_token("replace-with-your-api-toke", tokens) is None
        assert match_api_token("", tokens) is None
        assert match_api_token(TOKEN, []) is None
        assert (
            match_api_token(TOKEN, [ApiTokenConfig(token="", plates=[PLATE])]) is None
        )
