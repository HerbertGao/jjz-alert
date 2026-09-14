from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest

from jjz_alert.service.traffic.traffic_service import TrafficService

PAGE_HTML = """
<html>
<script>
var Holiday = new Array("2025-10-1", "2025-10-4");
</script>
<table>
  <tr><td>轮换日期 / 星期</td><td>星期一</td><td>星期二</td><td>星期三</td><td>星期四</td><td>星期五</td></tr>
  <tr>
    <td>2025年09月29日至<br>2025年10月05日</td>
    <td>1 和 6</td><td>2 和 7</td><td>3 和 8</td><td>4 和 9</td><td>5 和 0</td>
  </tr>
</table>
"""


@pytest.fixture
def traffic_service():
    cache = Mock()
    cache.get_traffic_rule = AsyncMock()
    cache.get_traffic_rules_batch = AsyncMock()
    cache.cache_traffic_rules = AsyncMock()
    cache.get_cache_stats = AsyncMock()
    cache.get_cache_info = AsyncMock()
    return TrafficService(cache)


def test_parse_traffic_page_expands_ranges_and_holidays(traffic_service):
    rules = traffic_service._parse_traffic_page(PAGE_HTML)

    by_date = {rule.date: rule for rule in rules}
    assert len(rules) == 7
    assert by_date[date(2025, 9, 29)].limited_numbers == "1和6"
    assert by_date[date(2025, 9, 30)].limited_numbers == "2和7"
    assert by_date[date(2025, 10, 1)].limited_numbers == "不限行"
    assert by_date[date(2025, 10, 4)].limited_numbers == "不限行"
    assert by_date[date(2025, 10, 5)].limited_numbers == "不限行"
    assert by_date[date(2025, 9, 29)].data_source == "official_page"


def test_parse_traffic_page_rejects_invalid_table(traffic_service):
    invalid_html = "<table><tr><td>轮换日期 / 星期</td><td>星期一</td></tr></table>"

    assert traffic_service._parse_traffic_page(invalid_html) == []


@pytest.mark.asyncio
async def test_async_fetch_falls_back_to_official_page(traffic_service):
    api_failure = Mock()
    api_failure.raise_for_status.side_effect = RuntimeError("502")
    page_response = Mock()
    page_response.raise_for_status = Mock()
    page_response.text = PAGE_HTML

    with patch(
        "jjz_alert.service.traffic.traffic_service.http_get",
        side_effect=[api_failure, api_failure, api_failure, page_response],
    ) as mock_get, patch.object(
        traffic_service, "_cache_rules", new_callable=AsyncMock
    ) as mock_cache:
        rules = await traffic_service._fetch_rules_from_api()

    assert rules[0].data_source == "official_page"
    assert mock_get.call_args_list[0].args[0].endswith("getRuleWithWeek")
    assert mock_get.call_args_list[-1].args[0].endswith("660341/index.html")
    mock_cache.assert_awaited_once_with(rules)


def test_sync_fetch_falls_back_to_official_page(traffic_service):
    api_failure = Mock()
    api_failure.raise_for_status.side_effect = RuntimeError("502")
    page_response = Mock()
    page_response.raise_for_status = Mock()
    page_response.text = PAGE_HTML

    with patch(
        "jjz_alert.service.traffic.traffic_service.http_get",
        side_effect=[api_failure, page_response],
    ):
        rules = traffic_service._fetch_limit_rules_sync()

    assert rules[0]["limitedTime"] == "2025年09月29日"
    assert rules[0]["limitedNumber"] == "1和6"
    assert rules[0]["data_source"] == "official_page"


@pytest.mark.asyncio
async def test_service_status_exposes_fallback_url(traffic_service):
    traffic_service.cache_service.get_cache_stats.return_value = {
        "traffic": {"total_hits": 0, "total_misses": 0, "hit_rate": 0}
    }
    traffic_service.cache_service.get_cache_info.return_value = {
        "key_counts": {"traffic": 0}
    }

    with patch.object(traffic_service, "get_today_traffic_rule", return_value=None):
        status = await traffic_service.get_service_status()

    assert status["fallback_url"].endswith("660341/index.html")
