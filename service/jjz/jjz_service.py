"""
进京证业务服务模块

提供进京证查询、缓存管理和业务逻辑封装
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Any

from config.config_v2 import JJZAccount
from service.cache.cache_service import CacheService
from service.jjz.jjz_status import JJZStatusEnum
from utils.error_handler import (
    APIError, handle_critical_error,
    is_token_error, with_retry
)
from utils.http import http_post
from utils.logger import get_structured_logger, LogCategory


@dataclass
class JJZStatus:
    """进京证状态数据模型"""
    plate: str
    status: str  # 使用 JJZStatusEnum 的值
    apply_time: Optional[str] = None
    valid_start: Optional[str] = None
    valid_end: Optional[str] = None
    days_remaining: Optional[int] = None
    sycs: Optional[str] = None  # 六环内进京证剩余办理次数
    jjzzlmc: Optional[str] = None  # 进京证类型名称
    blztmc: Optional[str] = None  # 办理状态描述
    error_message: Optional[str] = None
    data_source: str = "api"  # api, cache
    cached_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 使用 jjz_utils 格式化进京证类型和状态描述
        from utils.jjz_utils import extract_jjz_type_from_jjzzlmc, extract_status_from_blztmc

        # 格式化进京证类型
        formatted_jjz_type = extract_jjz_type_from_jjzzlmc(self.jjzzlmc or "")

        # 格式化状态描述
        formatted_status_desc = extract_status_from_blztmc(self.blztmc or "未知", self.status)

        return {
            'plate': self.plate,
            'status': self.status,
            'apply_time': self.apply_time,
            'valid_start': self.valid_start,
            'valid_end': self.valid_end,
            'days_remaining': self.days_remaining,
            'sycs': self.sycs,
            'jjzzlmc': self.jjzzlmc,  # 保留原始值
            'jjz_type_formatted': formatted_jjz_type,  # 添加格式化后的类型
            'blztmc': self.blztmc,  # 保留原始值
            'status_desc_formatted': formatted_status_desc,  # 添加格式化后的状态描述
            'error_message': self.error_message,
            'data_source': self.data_source,
            'cached_at': self.cached_at
        }


class JJZService:
    """进京证业务服务"""

    def __init__(self, cache_service: Optional[CacheService] = None):
        self.cache_service = cache_service or CacheService()
        self._accounts: List[JJZAccount] = []
        self._last_config_load = None
        self.structured_logger = get_structured_logger("jjz_service")

    def _check_jjz_status(self, url: str, token: str) -> Dict[str, Any]:
        """查询进京证状态（原jjz_checker功能）"""
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            resp = http_post(url, headers=headers, json_data={})
            resp.raise_for_status()
            logging.debug(f"进京证状态查询成功: {resp.json()}")
            return resp.json()
        except Exception as e:
            error_msg = str(e)
            
            # 特殊处理系统级错误
            if ("TLS connect error" in error_msg or "OPENSSL_internal" in error_msg or 
                "curl: (35)" in error_msg or "Connection" in error_msg or
                "Session.request() got an unexpected keyword argument" in error_msg or
                "HTTP POST请求失败" in error_msg or "HTTP GET请求失败" in error_msg):
                
                error_type = "系统级错误"
                if "TLS" in error_msg or "SSL" in error_msg:
                    error_type = "TLS/SSL连接错误"
                elif "Session.request()" in error_msg:
                    error_type = "HTTP请求参数错误"
                elif "HTTP" in error_msg:
                    error_type = "HTTP请求失败"
                elif "Connection" in error_msg:
                    error_type = "网络连接错误"
                
                logging.error(f"{error_type}: {error_msg}")
                # 异步通知管理员（不等待结果）
                asyncio.create_task(self._notify_admin_system_error(error_type, error_msg))
                return {"error": f"{error_type}: {error_msg}"}
            else:
                logging.error(f"进京证查询失败: {error_msg}")
                return {"error": error_msg}

    def _load_accounts(self) -> List[JJZAccount]:
        """加载进京证账户配置"""
        try:
            current_time = datetime.now()

            # 缓存配置1分钟，避免频繁读取
            if (self._last_config_load is None or
                    (current_time - self._last_config_load).total_seconds() > 60):
                # 使用全局配置管理器实例，避免重复加载
                from config.config_v2 import config_manager
                app_config = config_manager.load_config()
                self._accounts = app_config.jjz_accounts
                self._last_config_load = current_time
                logging.debug(f"已加载 {len(self._accounts)} 个进京证账户配置")

            return self._accounts

        except Exception as e:
            logging.error(f"加载进京证账户配置失败: {e}")
            return []

    def _parse_all_jjz_records(self, response_data: Dict[str, Any]) -> List[JJZStatus]:
        """解析所有进京证记录（包括生效中和待生效的进京证）"""
        records = []

        try:
            if 'error' in response_data:
                logging.warning(f"API响应包含错误: {response_data['error']}")
                return records

            data = response_data.get('data', {})
            bzclxx = data.get('bzclxx', [])

            if not bzclxx:
                return records

            # 遍历所有车辆记录
            for vehicle in bzclxx:
                plate = vehicle.get('hphm', '')
                if not plate:
                    continue

                # 获取生效中的进京证记录
                bzxx = vehicle.get('bzxx', [])
                # 获取待生效的进京证记录
                ecbzxx = vehicle.get('ecbzxx', [])

                # 处理生效中的进京证
                for record in bzxx:
                    jjz_status = self._parse_single_jjz_record(plate, record, vehicle, 'active')
                    if jjz_status:
                        records.append(jjz_status)

                # 处理待生效的进京证
                for record in ecbzxx:
                    jjz_status = self._parse_single_jjz_record(plate, record, vehicle, 'pending')
                    if jjz_status:
                        records.append(jjz_status)

        except Exception as e:
            logging.error(f"解析所有进京证记录失败: {e}")

        return records

    def _parse_single_jjz_record(self, plate: str, record: Dict[str, Any], vehicle: Dict[str, Any], record_type: str) -> Optional[JJZStatus]:
        """解析单个进京证记录"""
        try:
            # 解析进京证状态
            blzt = record.get('blzt', '')  # 办理状态
            blztmc = record.get('blztmc', '')  # 办理状态描述
            sqsj = record.get('sqsj', '')  # 申请时间
            yxqs = record.get('yxqs', '')  # 有效期开始
            yxqz = record.get('yxqz', '')  # 有效期结束
            sxsyts = record.get('sxsyts', '')  # 剩余使用天数
            sycs = vehicle.get('sycs', '')  # 六环内进京证剩余办理次数
            jjzzlmc = record.get('jjzzlmc', '')  # 进京证类型名称

            # 计算状态
            status = self._determine_status_v2(blzt, blztmc, yxqz, yxqs)
            
            # 处理剩余天数
            days_remaining = None
            if sxsyts and sxsyts != '' and sxsyts is not None:
                try:
                    days_remaining = int(sxsyts)
                except (ValueError, TypeError):
                    days_remaining = None

            jjz_status = JJZStatus(
                plate=plate,
                status=status,
                apply_time=sqsj,
                valid_start=yxqs,
                valid_end=yxqz,
                days_remaining=days_remaining,
                sycs=sycs,
                jjzzlmc=jjzzlmc,
                blztmc=blztmc,
                data_source='api'
            )

            return jjz_status

        except Exception as e:
            logging.error(f"解析单个进京证记录失败: plate={plate}, record_type={record_type}, error={e}")
            return None

    def _parse_jjz_response(self, plate: str, response_data: Dict[str, Any]) -> JJZStatus:
        """解析进京证API响应数据"""
        try:
            if 'error' in response_data:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.ERROR.value,
                    error_message=response_data['error'],
                    data_source='api'
                )

            # 解析API响应结构 - 根据实际API响应调整
            data = response_data.get('data', {})
            bzclxx = data.get('bzclxx', [])

            if not bzclxx:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.INVALID.value,
                    error_message='未找到车辆信息',
                    data_source='api'
                )

            # 查找匹配车牌的车辆信息
            target_vehicle = None
            for vehicle in bzclxx:
                if vehicle.get('hphm') == plate:
                    target_vehicle = vehicle
                    break

            if not target_vehicle:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.INVALID.value,
                    error_message='未找到匹配车牌的记录',
                    data_source='api'
                )

            # 获取进京证记录
            bzxx = target_vehicle.get('bzxx', [])
            if not bzxx:
                return JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.INVALID.value,
                    error_message='未找到进京证记录',
                    data_source='api'
                )

            # 获取最新的进京证记录
            latest_record = bzxx[0]  # 假设第一条是最新的

            # 解析进京证状态
            blzt = latest_record.get('blzt', '')  # 办理状态
            blztmc = latest_record.get('blztmc', '')  # 办理状态描述
            sqsj = latest_record.get('sqsj', '')  # 申请时间
            yxqs = latest_record.get('yxqs', '')  # 有效期开始
            yxqz = latest_record.get('yxqz', '')  # 有效期结束
            sxsyts = latest_record.get('sxsyts', '')  # 剩余使用天数
            sycs = target_vehicle.get('sycs', '')  # 六环内进京证剩余办理次数
            jjzzlmc = latest_record.get('jjzzlmc', '')  # 进京证类型名称

            # 计算状态
            logging.debug(
                f"解析字段: blzt={blzt}, blztmc={blztmc}, yxqz={yxqz}, sxsyts={sxsyts}, sycs={sycs}, jjzzlmc={jjzzlmc}")
            status = self._determine_status_v2(blzt, blztmc, yxqz, yxqs)
            # 直接使用API返回的剩余天数
            days_remaining = int(sxsyts) if sxsyts and sxsyts != '' else None

            return JJZStatus(
                plate=plate,
                status=status,
                apply_time=sqsj,
                valid_start=yxqs,
                valid_end=yxqz,
                days_remaining=days_remaining,
                sycs=sycs,
                jjzzlmc=jjzzlmc,
                blztmc=blztmc,
                data_source='api'
            )

        except Exception as e:
            logging.error(f"解析进京证API响应失败: plate={plate}, error={e}")
            return JJZStatus(
                plate=plate,
                status='error',
                error_message=f'解析响应失败: {str(e)}',
                data_source='api'
            )

    def _determine_status(self, status_code: str, valid_end: str) -> str:
        """根据状态码和有效期确定进京证状态（兼容旧版本）"""
        try:
            if not valid_end:
                return JJZStatusEnum.INVALID.value

            # 解析有效期结束时间
            end_date = datetime.strptime(valid_end, '%Y-%m-%d %H:%M:%S').date()
            today = date.today()

            if end_date < today:
                return JJZStatusEnum.EXPIRED.value
            elif status_code in ['approved', 'valid', '1']:
                return JJZStatusEnum.VALID.value
            elif status_code in ['pending', 'reviewing', '0']:
                return JJZStatusEnum.PENDING.value
            else:
                return JJZStatusEnum.INVALID.value

        except Exception as e:
            logging.warning(f"确定进京证状态失败: {e}")
            return JJZStatusEnum.INVALID.value

    def _determine_status_v2(self, blzt: str, blztmc: str, yxqz: str, yxqs: str = None) -> str:
        """根据新API格式确定进京证状态"""
        try:
            logging.debug(f"状态判断参数: blzt={blzt}, blztmc={blztmc}, yxqz={yxqz}, yxqs={yxqs}")

            if not yxqz:
                return JJZStatusEnum.INVALID.value

            # 解析有效期结束时间 (格式: 2025-08-19)
            end_date = datetime.strptime(yxqz, '%Y-%m-%d').date()
            today = date.today()

            if end_date < today:
                return JJZStatusEnum.EXPIRED.value
            elif (blzt == '1' or blzt == 1) and '审核通过' in blztmc and '生效中' in blztmc:
                return JJZStatusEnum.VALID.value
            elif (blzt == '6' or blzt == 6) and '审核通过' in blztmc and '待生效' in blztmc:
                # 待生效状态，需要检查是否在有效期内
                if yxqs:
                    try:
                        start_date = datetime.strptime(yxqs, '%Y-%m-%d').date()
                        if start_date <= today <= end_date:
                            return JJZStatusEnum.VALID.value  # 待生效但在有效期内，视为有效
                        else:
                            return JJZStatusEnum.PENDING.value  # 待生效但还未到生效时间
                    except Exception:
                        return JJZStatusEnum.PENDING.value
                else:
                    return JJZStatusEnum.PENDING.value
            elif (blzt == '0' or blzt == 0) or '审核中' in blztmc:
                return JJZStatusEnum.PENDING.value
            else:
                return JJZStatusEnum.INVALID.value

        except Exception as e:
            logging.warning(f"确定进京证状态失败: {e}")
            return JJZStatusEnum.INVALID.value

    def _calculate_days_remaining(self, valid_end: str) -> Optional[int]:
        """计算剩余有效天数（兼容旧版本）"""
        try:
            if not valid_end:
                return None

            end_date = datetime.strptime(valid_end, '%Y-%m-%d %H:%M:%S').date()
            today = date.today()
            delta = end_date - today

            return max(0, delta.days)

        except Exception as e:
            logging.warning(f"计算剩余天数失败: {e}")
            return None

    def _calculate_days_remaining_v2(self, yxqz: str) -> Optional[int]:
        """计算剩余有效天数（新API格式）"""
        try:
            if not yxqz:
                return None

            # 解析有效期结束时间 (格式: 2025-08-19)
            end_date = datetime.strptime(yxqz, '%Y-%m-%d').date()
            today = date.today()
            delta = end_date - today

            return max(0, delta.days)

        except Exception as e:
            logging.warning(f"计算剩余天数失败: {e}")
            return None

    async def get_jjz_status(self, plate: str) -> JJZStatus:
        """获取进京证状态 - 每次运行主流程时都重新查询"""
        start_time = time.time()

        try:
            # 记录开始查询
            self.structured_logger.log_structured(
                level=logging.INFO,
                message=f"开始查询进京证状态",
                category=LogCategory.BUSINESS,
                plate_number=plate,
                operation="get_jjz_status"
            )

            # 每次运行主流程时都从API获取最新数据
            status = await self._fetch_from_api(plate)

            duration_ms = round((time.time() - start_time) * 1000, 2)
            success = status.status != JJZStatusEnum.ERROR.value

            # 查询成功后缓存数据，供推送和后续其他操作使用
            if success:
                await self._cache_status(status)

            # 记录业务操作结果
            self.structured_logger.log_business_operation(
                operation="get_jjz_status",
                plate_number=plate,
                success=success,
                duration_ms=duration_ms,
                extra_data={
                    "status": status.status,
                    "data_source": status.data_source,
                    "has_error": bool(status.error_message)
                }
            )

            return status

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # 记录失败的业务操作
            self.structured_logger.log_business_operation(
                operation="get_jjz_status",
                plate_number=plate,
                success=False,
                duration_ms=duration_ms,
                extra_data={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )

            logging.error(f"获取进京证状态失败: plate={plate}, error={e}")
            return JJZStatus(
                plate=plate,
                status='error',
                error_message=str(e),
                data_source='api'
            )

    async def get_multiple_status_optimized(self, plates: List[str]) -> Dict[str, JJZStatus]:
        """优化的批量获取多个车牌的进京证状态 - 减少API调用次数"""
        results = {plate: None for plate in plates}
        accounts = self._load_accounts()

        if not accounts:
            for plate in plates:
                results[plate] = JJZStatus(
                    plate=plate,
                    status='error',
                    error_message='未配置进京证账户',
                    data_source='api'
                )
            return results

        # 记录每个车牌找到的状态
        plate_statuses = {plate: [] for plate in plates}

        # 只遍历一次所有账户，为所有车牌收集数据
        for account in accounts:
            try:
                logging.debug(f"使用账户 {account.name} 查询所有进京证数据")

                response_data = self._check_jjz_status(account.jjz.url, account.jjz.token)
                if 'error' in response_data:
                    logging.warning(f"账户 {account.name} 查询失败: {response_data['error']}")
                    continue

                # 解析所有进京证数据
                all_records = self._parse_all_jjz_records(response_data)

                # 为所有车牌查找匹配的记录
                for record in all_records:
                    for plate in plates:
                        if record.plate.upper() == plate.upper():
                            plate_statuses[plate].append(record)

            except Exception as e:
                logging.warning(f"账户 {account.name} 查询失败: {e}")
                continue

        # 为每个车牌选择最新的状态并缓存
        for plate in plates:
            statuses = plate_statuses[plate]
            if statuses:
                # 按申请时间排序，选择最新的记录
                latest_status = max(statuses, key=lambda s: s.apply_time or '')
                results[plate] = latest_status

                # 缓存成功查询的结果
                if latest_status.status != JJZStatusEnum.ERROR.value:
                    await self._cache_status(latest_status)
            else:
                results[plate] = JJZStatus(
                    plate=plate,
                    status='invalid',
                    error_message='未找到匹配车牌的记录',
                    data_source='api'
                )

        return results

    @with_retry(max_attempts=3, delay=1.0)
    async def _fetch_from_api(self, plate: str) -> JJZStatus:
        """从API获取进京证状态"""
        accounts = self._load_accounts()

        if not accounts:
            error = APIError("未配置进京证账户", details={"plate": plate})
            await handle_critical_error(error, f"获取车牌{plate}的进京证状态")
            return JJZStatus(
                plate=plate,
                status='error',
                error_message='未配置进京证账户',
                data_source='api'
            )

        # 查询所有账户，收集所有数据
        all_statuses = []
        last_error = None
        all_accounts_failed = True

        for account in accounts:
            try:
                logging.debug(f"使用账户 {account.name} 查询所有进京证数据")

                response_data = self._check_jjz_status(account.jjz.url, account.jjz.token)
                if 'error' in response_data:
                    last_error = response_data['error']
                    error_msg = response_data['error']
                    logging.warning(f"账户 {account.name} 查询失败: {error_msg}")

                    # 检查是否为Token错误，需要通知管理员
                    if is_token_error(Exception(error_msg)):
                        token_error = APIError(
                            f"账户 {account.name} Token可能已失效: {error_msg}",
                            details={"account": account.name, "plate": plate}
                        )
                        await handle_critical_error(token_error, f"查询车牌{plate}进京证状态")
                    continue

                all_accounts_failed = False

                # 解析所有进京证数据
                all_records = self._parse_all_jjz_records(response_data)

                # 查找匹配的车牌
                for record in all_records:
                    if record.plate.upper() == plate.upper():
                        all_statuses.append(record)

            except Exception as e:
                last_error = str(e)
                logging.warning(f"账户 {account.name} 查询失败: {e}")
                continue

        # 如果找到了匹配的记录，返回最新的
        if all_statuses:
            # 按申请时间排序，返回最新的
            latest_status = max(all_statuses, key=lambda s: s.apply_time or '')
            return latest_status

        # 如果所有账户都失败了，返回错误状态
        if all_accounts_failed and last_error:
            return JJZStatus(
                plate=plate,
                status='error',
                error_message=last_error,
                data_source='api'
            )

        # 没有找到匹配的记录
        return JJZStatus(
            plate=plate,
            status='invalid',
            error_message='未找到匹配车牌的记录',
            data_source='api'
        )

    async def _cache_status(self, status: JJZStatus) -> bool:
        """缓存进京证状态"""
        try:
            cache_data = status.to_dict()
            cache_data['cached_at'] = datetime.now().isoformat()

            success = await self.cache_service.cache_jjz_data(status.plate, cache_data)
            return success

        except Exception as e:
            logging.error(f"缓存进京证状态失败: plate={status.plate}, error={e}")
            return False

    async def get_multiple_status(self, plates: List[str]) -> Dict[str, JJZStatus]:
        """批量获取多个车牌的进京证状态"""
        results = {}

        for plate in plates:
            try:
                status = await self.get_jjz_status(plate)
                results[plate] = status
            except Exception as e:
                logging.error(f"获取车牌 {plate} 状态失败: {e}")
                results[plate] = JJZStatus(
                    plate=plate,
                    status=JJZStatusEnum.ERROR.value,
                    error_message=str(e),
                    data_source='api'
                )

        return results

    async def refresh_cache(self, plate: str) -> JJZStatus:
        """强制刷新指定车牌的缓存"""
        try:
            # 先删除旧缓存
            await self.cache_service.delete_jjz_data(plate)

            # 重新获取
            return await self.get_jjz_status(plate)

        except Exception as e:
            logging.error(f"刷新缓存失败: plate={plate}, error={e}")
            return JJZStatus(
                plate=plate,
                status='error',
                error_message=str(e),
                data_source='api'
            )

    async def get_cached_plates(self) -> List[str]:
        """获取所有已缓存的车牌号"""
        try:
            return await self.cache_service.get_all_jjz_plates()
        except Exception as e:
            logging.error(f"获取缓存车牌列表失败: {e}")
            return []

    async def check_expiring_permits(self, days_threshold: int = 3) -> List[JJZStatus]:
        """检查即将过期的进京证"""
        try:
            cached_plates = await self.get_cached_plates()
            expiring_permits = []

            for plate in cached_plates:
                status = await self.get_jjz_status(plate)

                if (status.status == 'valid' and
                        status.days_remaining is not None and
                        status.days_remaining <= days_threshold):
                    expiring_permits.append(status)

            return expiring_permits

        except Exception as e:
            logging.error(f"检查即将过期的进京证失败: {e}")
            return []

    async def get_service_status(self) -> Dict[str, Any]:
        """获取JJZ服务状态"""
        try:
            accounts = self._load_accounts()
            cached_plates = await self.get_cached_plates()

            # 检查缓存统计
            cache_stats = await self.cache_service.get_cache_stats(days=1)
            jjz_stats = cache_stats.get('jjz', {})

            return {
                'service': 'JJZService',
                'status': 'healthy',
                'accounts_count': len(accounts),
                'cached_plates_count': len(cached_plates),
                'cached_plates': cached_plates,
                'cache_stats': {
                    'hits': jjz_stats.get('total_hits', 0),
                    'misses': jjz_stats.get('total_misses', 0),
                    'hit_rate': jjz_stats.get('hit_rate', 0.0)
                },
                'last_config_load': self._last_config_load.isoformat() if self._last_config_load else None
            }

        except Exception as e:
            logging.error(f"获取JJZ服务状态失败: {e}")
            return {
                'service': 'JJZService',
                'status': 'error',
                'error': str(e)
            }

    async def _notify_admin_system_error(self, error_type: str, error_msg: str):
        """
        通知管理员系统级错误
        
        Args:
            error_type: 错误类型
            error_msg: 错误信息
        """
        try:
            from service.notification.push_helpers import push_admin_notification
            from service.notification.adapter import PushPriority
            
            # 构建通知消息
            title = "🚨 进京证查询系统错误"
            message = f"""
🔧 服务: 进京证查询服务
❌ 错误类型: {error_type}
📝 错误详情: {error_msg}
⏰ 发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
💡 建议: 请检查系统配置和服务器状态
🔄 处理: 已跳过用户推送，仅通知管理员
            """.strip()
            
            # 直接使用全局管理员配置发送通知
            await push_admin_notification(
                title=title,
                message=message,
                priority=PushPriority.HIGH,
                category="system_error"
            )
            
            logging.info(f"已向管理员发送系统错误通知: {error_type}")
            
        except Exception as e:
            logging.error(f"发送管理员系统错误通知失败: {e}")

    async def _notify_admin_network_error(self, error_type: str, error_msg: str):
        """
        通知管理员网络错误（保留向后兼容）
        
        Args:
            error_type: 错误类型
            error_msg: 错误信息
        """
        # 调用系统错误通知函数
        await self._notify_admin_system_error(error_type, error_msg)


# 全局JJZ服务实例
jjz_service = JJZService()
