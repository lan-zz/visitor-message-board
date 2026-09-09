import os
import sqlite3
import uuid
import time
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

from push import send_push, get_config, save_config, test_push

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', BASE_DIR / 'uploads'))
DATA_DIR   = Path(os.environ.get('DATA_DIR',   BASE_DIR / 'data'))
DB_PATH    = DATA_DIR / 'board.db'
CONFIG_FILE = DATA_DIR / 'config.json'
LEASE_FILE  = os.environ.get('LEASE_FILE', '/tmp/dhcp.leases')

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB    = int(os.environ.get('MAX_UPLOAD_MB', '500'))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CLEANUP_DAYS     = int(os.environ.get('CLEANUP_DAYS', '30'))
ADMIN_SUBNET     = os.environ.get('ADMIN_SUBNET', '192.168.2.')

ALLOWED_EXT = {
    'image': {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'},
    'video': {'mp4', 'webm', 'mov', 'avi', 'mkv'},
    'audio': {'mp3', 'wav', 'ogg', 'm4a', 'aac', 'webm'},
}
ALL_ALLOWED = set()
for exts in ALLOWED_EXT.values():
    ALL_ALLOWED |= exts

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES

_db_lock = threading.Lock()


# ─── 数据库 ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    with _db_lock, get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id         TEXT PRIMARY KEY,
                name       TEXT,
                content    TEXT,
                media_type TEXT,
                media_path TEXT,
                media_size INTEGER,
                created_at REAL NOT NULL,
                ip         TEXT,
                mac        TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_created ON messages(created_at)')
        try:
            conn.execute('ALTER TABLE messages ADD COLUMN mac TEXT')
        except Exception:
            pass


# ─── 客户端身份 ───────────────────────────────────────────────────────────────

def resolve_mac(ip):
    """通过 dnsmasq 租约文件把 IP 解析为 MAC（用于区分访客身份）"""
    try:
        with open(LEASE_FILE) as f:
            for line in f:
                p = line.split()
                if len(p) >= 3 and p[2] == ip:
                    return p[1].upper()
    except Exception:
        pass
    return None


def get_viewer():
    ip = request.remote_addr or ''
    if ip.startswith(ADMIN_SUBNET):
        return {'ip': ip, 'is_admin': True, 'mac': None}
    return {'ip': ip, 'is_admin': False, 'mac': resolve_mac(ip)}


# ─── 媒体类型 ────────────────────────────────────────────────────────────────

def detect_media_type(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    for mtype, exts in ALLOWED_EXT.items():
        if ext in exts:
            return mtype, ext
    return None, ext


# ─── 清理旧留言 ───────────────────────────────────────────────────────────────

def cleanup_old_messages():
    cutoff = time.time() - CLEANUP_DAYS * 86400
    with _db_lock, get_db() as conn:
        rows = conn.execute(
            'SELECT id, media_path FROM messages WHERE created_at < ?', (cutoff,)
        ).fetchall()
        for r in rows:
            if r['media_path']:
                fp = UPLOAD_DIR / r['media_path']
                if fp.exists():
                    try:
                        fp.unlink()
                    except Exception:
                        pass
            conn.execute('DELETE FROM messages WHERE id = ?', (r['id'],))
        conn.commit()
    if rows:
        print(f'[cleanup] removed {len(rows)} messages older than {CLEANUP_DAYS}d', flush=True)


@app.before_request
def _cleanup_check():
    if getattr(app, '_req_count', 0) % 100 == 0:
        try:
            cleanup_old_messages()
        except Exception as e:
            print(f'[cleanup] error: {e}', flush=True)
    app._req_count = getattr(app, '_req_count', 0) + 1


# ─── 路由 ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', max_upload_mb=MAX_UPLOAD_MB)


@app.route('/admin')
def admin_page():
    """管理后台：推送配置"""
    return render_template('admin.html', max_upload_mb=MAX_UPLOAD_MB)


# ── 留言 API ─────────────────────────────────────────────────────────────────

@app.route('/api/messages')
def list_messages():
    viewer = get_viewer()
    with get_db() as conn:
        if viewer['is_admin']:
            rows = conn.execute(
                'SELECT * FROM messages ORDER BY created_at DESC'
            ).fetchall()
        else:
            mac = viewer['mac']
            ip  = viewer['ip']
            if mac:
                rows = conn.execute(
                    'SELECT * FROM messages WHERE mac=? AND mac IS NOT NULL '
                    'OR (mac IS NULL AND ip=?) ORDER BY created_at DESC',
                    (mac, ip)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM messages WHERE ip=? ORDER BY created_at DESC',
                    (ip,)
                ).fetchall()
    return jsonify({
        'identity': {
            'is_admin': viewer['is_admin'],
            'viewer_mac': viewer['mac'],
            'viewer_ip': viewer['ip'],
        },
        'total': len(rows),
        'messages': [dict(r) for r in rows],
    })


@app.route('/api/upload', methods=['POST'])
def upload_message():
    viewer = get_viewer()
    # 超大文件在解析请求体之前提前拒绝
    if request.content_length and request.content_length > MAX_UPLOAD_BYTES:
        return jsonify({'error': f'文件超过 {MAX_UPLOAD_MB}MB 限制'}), 400

    name    = (request.form.get('name')    or '').strip()[:50] or '匿名访客'
    content = (request.form.get('content') or '').strip()[:2000]
    file    = request.files.get('file')

    if not content and not file:
        return jsonify({'error': '留言内容和文件至少需要一项'}), 400

    media_type = None
    media_path = None
    media_size = 0

    if file and file.filename:
        original = secure_filename(file.filename) or 'file'
        mtype, ext = detect_media_type(original)
        if mtype is None:
            return jsonify({'error': f'不支持的文件类型: .{ext}'}), 400
        media_type = mtype
        stored_name = f'{uuid.uuid4().hex}.{ext}'
        save_path = UPLOAD_DIR / stored_name
        try:
            file.save(str(save_path))
        except Exception as e:
            return jsonify({'error': f'保存文件失败: {e}'}), 500
        media_size = save_path.stat().st_size
        if media_size > MAX_UPLOAD_BYTES:
            save_path.unlink(missing_ok=True)
            return jsonify({'error': f'文件超过 {MAX_UPLOAD_MB}MB 限制'}), 400
        media_path = stored_name

    msg_id  = uuid.uuid4().hex
    created = time.time()
    ip      = viewer['ip']
    mac     = viewer['mac']

    with _db_lock, get_db() as conn:
        conn.execute(
            'INSERT INTO messages (id,name,content,media_type,media_path,media_size,created_at,ip,mac) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (msg_id, name, content, media_type, media_path, media_size, created, ip, mac)
        )
        conn.commit()

    # 推送通知（非阻塞）
    tag = '[管理员] ' if viewer['is_admin'] else ''
    title = f'📢 新留言 · {name}'
    body  = content if content else f'[{media_type or "文件"}]'
    if len(body) > 100:
        body = body[:100] + '...'
    send_push(title, tag + body)

    return jsonify({'ok': True, 'id': msg_id})


@app.route('/api/messages/<mid>', methods=['DELETE'])
def delete_message(mid):
    if not get_viewer()['is_admin']:
        return jsonify({'error': '仅管理员可删除'}), 403
    with _db_lock, get_db() as conn:
        row = conn.execute(
            'SELECT media_path FROM messages WHERE id=?', (mid,)
        ).fetchone()
        if not row:
            return jsonify({'error': '未找到该留言'}), 404
        if row['media_path']:
            fp = UPLOAD_DIR / row['media_path']
            if fp.exists():
                try:
                    fp.unlink()
                except Exception:
                    pass
        conn.execute('DELETE FROM messages WHERE id=?', (mid,))
        conn.commit()
    return jsonify({'ok': True})


# ── 推送配置 API ─────────────────────────────────────────────────────────────

@app.route('/api/config', methods=['GET'])
def api_get_config():
    if not get_viewer()['is_admin']:
        return jsonify({'error': '仅管理员可访问'}), 403
    return jsonify({'config': get_config()})


@app.route('/api/config', methods=['PUT', 'POST'])
def api_save_config():
    if not get_viewer()['is_admin']:
        return jsonify({'error': '仅管理员可访问'}), 403
    try:
        new_cfg = request.get_json(force=True)
    except Exception:
        return jsonify({'error': '无效的 JSON'}), 400
    ok, msg = save_config(new_cfg)
    if ok:
        return jsonify({'ok': True, 'message': msg})
    return jsonify({'error': msg}), 500


@app.route('/api/config/test', methods=['POST'])
def api_test_push():
    """测试推送（不依赖当前配置，可单独提交测试参数）"""
    if not get_viewer()['is_admin']:
        return jsonify({'error': '仅管理员可访问'}), 403
    try:
        test_cfg = request.get_json(force=True)
        platform = test_cfg.get('platform', 'bark')
    except Exception:
        test_cfg = None
        platform = 'unknown'

    # 合并：优先用提交的配置，否则用已保存的
    if test_cfg:
        from push import _load_config
        base = _load_config()
        base.update(test_cfg)
        ok, msg = test_push(base)
    else:
        ok, msg = test_push()

    return jsonify({'ok': ok, 'message': msg, 'platform': platform})


# ── 静态文件 / 探针 / 兜底 ─────────────────────────────────────────────────

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@app.route('/health')
def health():
    return jsonify({'ok': True, 'time': datetime.now().isoformat()})


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/generate_204')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
@app.route('/hotspot-detect.html')
@app.route('/redirect')
def captive_probe():
    return render_template('index.html', max_upload_mb=MAX_UPLOAD_MB)


@app.route('/<path:path>')
def catch_all(path):
    return render_template('index.html', max_upload_mb=MAX_UPLOAD_MB)


# ─── 启动 ───────────────────────────────────────────────────────────────────

init_db()
print(f'Board started. MAX_UPLOAD={MAX_UPLOAD_MB}MB  CLEANUP={CLEANUP_DAYS}d  ADMIN={ADMIN_SUBNET}', flush=True)
