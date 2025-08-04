import json
import logging
import re
import time
from datetime import date, datetime
from typing import Dict, List, Optional

from utils.http import http_get


class TrafficLimiter:
    def __init__(self):
        self._cache = None
        self._cache_date = None
        self._cache_status = "uninitialized"  # uninitialized, loading, ready, error
        self._last_update_time = None
        self._retry_count = 0
        self._max_retries = 3
        self._limit_rules_url = "https://yw.jtgl.beijing.gov.cn/jgjxx/services/getRuleWithWeek"
    
    def _is_same_day(self, date1: date, date2: date) -> bool:
        """检查两个日期是否为同一天"""
        return date1 == date2
    
    def _get_plate_tail_number(self, plate: str) -> str:
        """获取车牌尾号，英文字母按0处理"""
        if not plate:
            return "0"
        
        # 获取最后一个字符
        tail = plate[-1]
        
        # 如果是英文字母，返回"0"
        if tail.isalpha():
            return "0"
        
        # 如果是数字，返回该数字
        if tail.isdigit():
            return tail
        
        # 其他情况返回"0"
        return "0"
    
    def _is_limited_today(self, plate: str) -> bool:
        """检查指定车牌今天是否限行"""
        if not self._cache or not self._cache_date:
            return False
        
        today = date.today()
        if not self._is_same_day(self._cache_date, today):
            return False
        
        # 获取今天的限行规则
        today_rule = None
        for rule in self._cache:
            rule_date = datetime.strptime(rule['limitedTime'], '%Y年%m月%d日').date()
            if self._is_same_day(rule_date, today):
                today_rule = rule
                break
        
        if not today_rule:
            return False
        
        # 如果是不限行，返回False
        if today_rule['limitedNumber'] == '不限行':
            return False
        
        # 获取车牌尾号
        tail_number = self._get_plate_tail_number(plate)
        
        # 检查尾号是否在限行范围内
        limited_numbers = today_rule['limitedNumber']
        
        # 解析限行号码（格式如："1和6"、"2和7"等）
        if '和' in limited_numbers:
            numbers = limited_numbers.split('和')
            return tail_number in numbers
        else:
            # 处理其他可能的格式
            return tail_number in limited_numbers
    
    def _fetch_limit_rules(self) -> Optional[List[Dict]]:
        """从API获取限行规则"""
        try:
            logging.info(f'正在获取限行规则... (重试次数: {self._retry_count})')
            resp = http_get(self._limit_rules_url, verify=False)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get('state') == 'success' and 'result' in data:
                logging.info(f'成功获取限行规则，共 {len(data["result"])} 条')
                return data['result']
            else:
                logging.error(f'获取限行规则失败: {data.get("resultMsg", "未知错误")}')
                return None
        except Exception as e:
            logging.error(f'获取限行规则异常: {e}')
            return None
    
    def _update_cache_if_needed(self):
        """如果需要，更新缓存"""
        today = date.today()
        
        # 如果缓存不存在或不是今天的，则更新缓存
        if not self._cache or not self._cache_date or not self._is_same_day(self._cache_date, today):
            self._update_cache()
    
    def _update_cache(self):
        """更新缓存"""
        self._cache_status = "loading"
        self._retry_count = 0
        
        while self._retry_count < self._max_retries:
            try:
                rules = self._fetch_limit_rules()
                if rules:
                    self._cache = rules
                    self._cache_date = date.today()
                    self._last_update_time = time.time()
                    self._cache_status = "ready"
                    logging.info(f'成功缓存 {len(rules)} 条限行规则')
                    return
                else:
                    self._retry_count += 1
                    if self._retry_count < self._max_retries:
                        logging.warning(f'获取限行规则失败，{self._retry_count}/{self._max_retries} 次重试')
                        time.sleep(2)  # 等待2秒后重试
                    else:
                        logging.error('获取限行规则失败，已达到最大重试次数')
                        self._cache_status = "error"
                        # 使用空缓存，避免程序崩溃
                        self._cache = []
                        self._cache_date = date.today()
                        self._last_update_time = time.time()
            except Exception as e:
                self._retry_count += 1
                logging.error(f'更新缓存异常: {e}')
                if self._retry_count < self._max_retries:
                    logging.warning(f'准备第 {self._retry_count}/{self._max_retries} 次重试')
                    time.sleep(2)
                else:
                    logging.error('更新缓存失败，已达到最大重试次数')
                    self._cache_status = "error"
                    # 使用空缓存，避免程序崩溃
                    self._cache = []
                    self._cache_date = date.today()
                    self._last_update_time = time.time()
    
    def preload_cache(self):
        """预加载缓存"""
        """预加载缓存 - 在程序启动时主动加载限行规则"""
        logging.info('开始预加载尾号限行规则缓存')
        self._update_cache()
        
        if self._cache_status == "ready":
            logging.info('尾号限行规则缓存预加载成功')
        else:
            logging.warning('尾号限行规则缓存预加载失败，将在使用时重试')
    
    def get_cache_status(self) -> Dict:
        """获取缓存状态信息"""
        return {
            'status': self._cache_status,
            'cache_date': self._cache_date.isoformat() if self._cache_date else None,
            'cache_count': len(self._cache) if self._cache else 0,
            'last_update': self._last_update_time,
            'retry_count': self._retry_count
        }
    
    def check_plate_limited(self, plate: str) -> bool:
        """检查车牌是否限行（仅今日）"""
        self._update_cache_if_needed()
        return self._is_limited_today(plate)

    def check_plate_limited_on(self, plate: str, target: date) -> bool:
        """检查车牌在指定日期是否限行

        如果缓存中找不到对应日期的规则，返回 False。
        """
        self._update_cache_if_needed()
        if not self._cache:
            return False

        # 查找目标日期对应的限行规则
        rule_for_day = None
        from datetime import datetime as _dt
        for rule in self._cache:
            try:
                rule_date = _dt.strptime(rule['limitedTime'], '%Y年%m月%d日').date()
            except Exception:
                continue
            if self._is_same_day(rule_date, target):
                rule_for_day = rule
                break

        if not rule_for_day or rule_for_day.get('limitedNumber') == '不限行':
            return False

        tail_number = self._get_plate_tail_number(plate)
        limited_numbers = rule_for_day['limitedNumber']
        if '和' in limited_numbers:
            numbers = limited_numbers.split('和')
            return tail_number in numbers
        else:
            return tail_number in limited_numbers
    
    def get_today_limit_info(self) -> Optional[Dict]:
        """获取今天的限行信息"""
        self._update_cache_if_needed()
        
        if not self._cache:
            return None
        
        today = date.today()
        for rule in self._cache:
            rule_date = datetime.strptime(rule['limitedTime'], '%Y年%m月%d日').date()
            if self._is_same_day(rule_date, today):
                return rule
        
        return None

# 全局实例
traffic_limiter = TrafficLimiter() 