import json
import re
from datetime import datetime, date
from typing import Dict, List, Optional
from utils.http import http_get

class TrafficLimiter:
    def __init__(self):
        self._cache = None
        self._cache_date = None
        self._limit_rules_url = "https://yw.jtgl.beijing.gov.cn/jgjxx/services/getRuleWithWeek"
        self._headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'Cookie': "_yfx_session_10018414=%7B%22_yfx_firsttime%22%3A%221730079911306%22%2C%22_yfx_lasttime%22%3A%221746677494678%22%2C%22_yfx_visittime%22%3A%221746677494678%22%2C%22_yfx_lastvisittime%22%3A%221746677494678%22%2C%22_yfx_domidgroup%22%3A%221746677494678%22%2C%22_yfx_domallsize%22%3A%22100%22%2C%22_yfx_cookie%22%3A%2220241028094511308301592835466746%22%2C%22_yfx_returncount%22%3A%227%22%2C%22_yfx_searchid%22%3A%221731738394012910%22%7D; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%221983713a3004e5-0ee8477f7b2a568-7e433c49-2732424-1983713a301242b%22%7D; _abfpc=5127967bfcf3ae464885b1fdbc4eb03b9c673402_2.0; cna=9c3b19a172af5f7b88e48b51a7dd9df9; _yfx_session_sdzc=%7B%22_yfx_firsttime%22%3A%221753270687054%22%2C%22_yfx_lasttime%22%3A%221753771245282%22%2C%22_yfx_visittime%22%3A%221753771245282%22%2C%22_yfx_lastvisittime%22%3A%221753771245282%22%2C%22_yfx_domidgroup%22%3A%221753771245282%22%2C%22_yfx_domallsize%22%3A%22100%22%2C%22_yfx_cookie%22%3A%2220250723193807057354726895751186%22%2C%22_yfx_userid%22%3A%22868cc808-d2e5-11e9-a53f-24ddeafd3717%22%2C%22_yfx_returncount%22%3A%222%22%7D"
        }
    
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
            resp = http_get(self._limit_rules_url, verify=False, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get('state') == 'success' and 'result' in data:
                return data['result']
            else:
                print(f'[ERROR] 获取限行规则失败: {data.get("resultMsg", "未知错误")}')
                return None
        except Exception as e:
            print(f'[ERROR] 获取限行规则异常: {e}')
            return None
    

    
    def _update_cache_if_needed(self):
        """如果需要，更新缓存"""
        today = date.today()
        
        # 如果缓存不存在或不是今天的，则更新缓存
        if not self._cache or not self._cache_date or not self._is_same_day(self._cache_date, today):
            print('[INFO] 更新尾号限行规则缓存')
            rules = self._fetch_limit_rules()
            if rules:
                self._cache = rules
                self._cache_date = today
                print(f'[INFO] 成功缓存 {len(rules)} 条限行规则')
            else:
                print('[WARN] 获取限行规则失败，使用空缓存')
                self._cache = []
                self._cache_date = today
    
    def check_plate_limited(self, plate: str) -> bool:
        """检查车牌是否限行"""
        self._update_cache_if_needed()
        return self._is_limited_today(plate)
    
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