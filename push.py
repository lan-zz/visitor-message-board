"""
访客留言板 · 多推送后端

支持的平台：Bark / 飞书 Webhook / 企业微信 Webhook / 钉钉 Webhook
配置由 config.json 管理（通过后台管理页面读写）

config.json 格式：
{
  "enabled": true,
  "platform": "bark",          // bark | feishu | wecom | dingtalk
  "bark": {
    "key": "your-bark-key"
  },
  "feishu": {
    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
  },
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  },
  "dingtalk": {
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
    "secret":  "SEC...xxx"     // 加签密钥（可选）
  }
}
"""

import os
import json
import hashlib
import hmac
import base64
import time
import threading
import requests
from pathlib import Path

CONFIG_FILE = Path(os.environ.get('CONFIG_FILE', '/data/config.json'))


def _load_config():
    """读取配置（容错：文件不存在或损坏时返回默认空配置）"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except Exception as e:
        print(f'[push] config load error: {e}', flush=True)
    return {'enabled': False, 'platform': 'bark'}


def _save_config(cfg):
    """保存配置到文件"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True, '保存成功'
    except Exception as e:
        return False, f'保存失败: {e}'


# ─── 各平台推送实现 ──────────────────────────────────────────────────────────

def _push_bark(cfg, title, body, url=None):
    key = cfg.get('bark', {}).get('key', '').strip()
    if not key:
        return False, 'Bark Key 未配置'
    try:
        payload = {'title': title, 'body': body, 'sound': 'bell', 'group': '访客留言'}
        if url:
            payload['url'] = url
        r = requests.post(f'https://api.day.app/{key}', json=payload, timeout=10)
        if r.status_code == 200:
            return True, '发送成功'
        return False, f'HTTP {r.status_code}: {r.text[:100]}'
    except Exception as e:
        return False, str(e)


def _push_feishu(cfg, title, body, url=None):
    webhook = cfg.get('feishu', {}).get('webhook', '').strip()
    if not webhook:
        return False, '飞书 Webhook 未配置'
    try:
        content = f'{title}\n{body}'
        payload = {
            'msg_type': 'text',
            'content': {'text': content}
        }
        r = requests.post(webhook, json=payload, timeout=10)
        if r.status_code == 200:
            resp = r.json()
            if resp.get('code') == 0 or resp.get('StatusCode') == 0:
                return True, '发送成功'
            return False, f'错误码: {resp}'
        return False, f'HTTP {r.status_code}'
    except Exception as e:
        return False, str(e)


def _push_wecom(cfg, title, body, url=None):
    webhook = cfg.get('wecom', {}).get('webhook', '').strip()
    if not webhook:
        return False, '企业微信 Webhook 未配置'
    try:
        content = f'{title}\n{body}'
        payload = {
            'msgtype': 'text',
            'text': {'content': content}
        }
        r = requests.post(webhook, json=payload, timeout=10)
        if r.status_code == 200:
            resp = r.json()
            if resp.get('errcode') == 0:
                return True, '发送成功'
            return False, f'错误码 {resp.get("errcode")}: {resp.get("errmsg")}'
        return False, f'HTTP {r.status_code}'
    except Exception as e:
        return False, str(e)


def _push_dingtalk(cfg, title, body, url=None):
    webhook = cfg.get('dingtalk', {}).get('webhook', '').strip()
    secret  = cfg.get('dingtalk', {}).get('secret', '').strip()
    if not webhook:
        return False, '钉钉 Webhook 未配置'

    # 加签（可选）
    timestamp = str(round(time.time() * 1000))
    sign = ''
    if secret:
        sign_input = (timestamp + '\n' + secret).encode('utf-8')
        sign = base64.b64encode(
            hmac.new(secret.encode('utf-8'), sign_input, hashlib.sha256).digest()
        ).decode('utf-8')
        sep = '&' if '?' in webhook else '?'
        webhook += f'{sep}timestamp={timestamp}&sign={sign}'

    try:
        content = f'{title}\n{body}'
        payload = {
            'msgtype': 'text',
            'text': {'content': content}
        }
        r = requests.post(webhook, json=payload, timeout=10)
        if r.status_code == 200:
            resp = r.json()
            if resp.get('errcode') == 0:
                return True, '发送成功'
            return False, f'错误码 {resp.get("errcode")}: {resp.get("errmsg")}'
        return False, f'HTTP {r.status_code}'
    except Exception as e:
        return False, str(e)


# ─── 主推送函数 ───────────────────────────────────────────────────────────────

def send_push(title, body, url=None):
    """
    向已配置的平台发送推送。非阻塞（后台线程）。
    配置未启用或推送失败不抛异常，仅打印日志。
    """
    cfg = _load_config()
    if not cfg.get('enabled', False):
        return  # 未启用，不推送

    platform = cfg.get('platform', 'bark')

    def _worker():
        try:
            if platform == 'bark':
                ok, msg = _push_bark(cfg, title, body, url)
            elif platform == 'feishu':
                ok, msg = _push_feishu(cfg, title, body, url)
            elif platform == 'wecom':
                ok, msg = _push_wecom(cfg, title, body, url)
            elif platform == 'dingtalk':
                ok, msg = _push_dingtalk(cfg, title, body, url)
            else:
                print(f'[push] unknown platform: {platform}', flush=True)
                return
            status = '✓' if ok else '✗'
            print(f'[push][{platform}] {status} {msg}', flush=True)
        except Exception as e:
            print(f'[push][{platform}] error: {e}', flush=True)

    threading.Thread(target=_worker, daemon=True).start()


# ─── 管理接口 ─────────────────────────────────────────────────────────────────

def get_config():
    """返回配置（隐藏密钥后缀，只显示是否已配置）"""
    cfg = _load_config()
    # 脱敏：Bark key 只显示后 6 位；webhook URL 只显示域名
    def mask(cfg):
        result = {}
        for k, v in cfg.items():
            if isinstance(v, dict):
                result[k] = {kk: _mask_value(kk, vv) for kk, vv in v.items()}
            else:
                result[k] = v
        return result
    return mask(cfg)


def _mask_value(key, val):
    if not val or not isinstance(val, str):
        return val
    if key == 'key':
        return '****' + val[-6:] if len(val) >= 6 else '****'
    if key == 'webhook' and '://' in val:
        from urllib.parse import urlparse
        netloc = urlparse(val).netloc
        return val.replace(netloc, netloc[:10] + '***')
    if key == 'secret':
        return '****' + val[-4:] if len(val) >= 4 else '****'
    return val


def save_config(new_cfg):
    """保存新配置"""
    # 允许只提交部分字段（前台表单）
    cfg = _load_config()
    cfg.update(new_cfg)
    return _save_config(cfg)


def test_push(cfg=None):
    """发送测试推送"""
    if cfg is None:
        cfg = _load_config()
    platform = cfg.get('platform', 'bark')
    title = '🪄 推送测试'
    body  = '访客留言板推送通道测试成功！如果看到这条消息，说明推送配置正确。'

    try:
        if platform == 'bark':
            ok, msg = _push_bark(cfg, title, body)
        elif platform == 'feishu':
            ok, msg = _push_feishu(cfg, title, body)
        elif platform == 'wecom':
            ok, msg = _push_wecom(cfg, title, body)
        elif platform == 'dingtalk':
            ok, msg = _push_dingtalk(cfg, title, body)
        else:
            return False, f'未知平台: {platform}'
        return ok, msg
    except Exception as e:
        return False, str(e)
