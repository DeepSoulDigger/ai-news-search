#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地离线检索服务(纯标准库,无需联网)
- 启动时扫描 data 目录下的全部 *.json,建立内存索引(含预计算的检索文本)
- 提供导航配置、文章列表、检索、详情、静态资源等接口
- 数据目录或 config.json 变化时自动重载(节流检查),无需重启程序
重构要点(2026-09):
- /api/articles 复用统一检索函数,消除重复过滤逻辑
- 扫描时预计算小写检索文本与 id 索引,详情查询 O(1)
- 日期归一化(支持 YYYY-MM-DD 与 YYYY年M月D日)
- /data/ 静态服务:百分号解码 + commonpath 穿越校验 + 响应头注入防护
- 统一安全响应头(nosniff / SAMEORIGIN / Referrer-Policy)
- 支持 HEAD 请求;配置接口附带分类计数
"""
import os
import sys
import json
import re
import mimetypes
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# 外部目录定位:始终相对于"被启动的程序本体"所在目录,
# 这样打包成 exe 后,config.json 与 data/ 放在 exe 同目录即可,无需重新编译。
# ---------------------------------------------------------------------------
def app_base_dir():
    """定位程序所在目录。
    - exe 运行:取 exe 所在目录(交付结构:data/ 与 config.json 与 exe 同级);
    - 源码运行:依次尝试脚本目录、脚本上级(项目根),取首个含 data/ 或 config.json 者。
    """
    cands = [os.path.dirname(os.path.abspath(sys.argv[0]))]
    if not getattr(sys, "frozen", False):
        here = os.path.dirname(os.path.abspath(__file__))
        cands.append(os.path.dirname(here))  # python src/server.py -> 项目根
        cands.append(here)                   # python server.py(根目录布局) -> 脚本目录
    for c in cands:
        if os.path.isdir(os.path.join(c, "data")) or os.path.isfile(os.path.join(c, "config.json")):
            return c
    return cands[0]

BASE = app_base_dir()
CONFIG_PATH = os.path.join(BASE, "config.json")
DATA_DIR = os.path.join(BASE, "data")

# ---------------------------------------------------------------------------
# 索引状态:_articles(列表,按日期倒序) 与 _by_id 同步整体替换,读侧无锁安全。
# ---------------------------------------------------------------------------
_articles = []
_by_id = {}
_state_lock = threading.Lock()
_scan_lock = threading.Lock()
_last_scan = 0.0
_watched_mtimes = ()

RE_ISO_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
RE_CN_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

DEFAULT_CONFIG = {
    "app_title": "人工智能报道检索平台",
    "org": "××单位",
    "categories": [
        {"name": "政策解读", "sub": ["国家战略", "规划文件", "地方实践"]},
        {"name": "技术创新", "sub": ["大模型", "算力芯片", "前沿算法"]},
        {"name": "产业应用", "sub": ["智能制造", "智慧医疗", "智慧交通"]},
        {"name": "社会治理", "sub": ["政务服务", "城市治理", "公共安全"]},
        {"name": "国际视野", "sub": ["域外动态", "国际合作", "比较研究"]},
        {"name": "人才培养", "sub": ["学科建设", "产教融合", "科普教育"]},
        {"name": "伦理安全", "sub": ["伦理规范", "数据安全", "风险治理"]},
    ],
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def norm_date(raw):
    """把各类日期写法归一为 YYYY-MM-DD;无法识别返回空串。"""
    s = str(raw or "").strip()
    m = RE_ISO_DATE.search(s) or RE_CN_DATE.search(s)
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return "%04d-%02d-%02d" % (y, mo, d)


def _safe_relpath(rel):
    """清洗相对路径:解码百分号、统一分隔符、拒绝盘符与绝对路径。"""
    rel = urllib.parse.unquote(rel)
    rel = rel.replace("\\", "/")
    if not rel or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        return None
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


# ---------------------------------------------------------------------------
# 扫描与归一化
# ---------------------------------------------------------------------------
def normalize(data, path):
    """把单篇原始 JSON 整理为统一结构;非法条目返回 None。"""
    if not isinstance(data, dict):
        return None
    title = str(data.get("title", "")).strip()
    if not title:
        return None
    aid = str(data.get("id") or os.path.splitext(os.path.basename(path))[0]).strip()
    source = str(data.get("source", "")).strip()
    date = norm_date(data.get("date"))
    category = str(data.get("category", "")).strip()
    subcategory = str(data.get("subcategory", "")).strip()
    author = str(data.get("author", "")).strip()
    summary = str(data.get("summary", "")).strip()

    body = data.get("body", "")
    if isinstance(body, list):
        body = "\n\n".join(str(p) for p in body)
    body = str(body).strip()

    def asset_url(rel_raw, kind_dir):
        rel = _safe_relpath(str(rel_raw).strip())
        if not rel:
            return None
        full = os.path.normpath(os.path.join(DATA_DIR, rel))
        if os.path.isfile(full):
            return "/data/" + rel
        return None

    # 配图:支持字符串或列表,均为相对 data 目录的路径
    image_urls = []
    image = data.get("image")
    if image:
        for rel in (image if isinstance(image, list) else [image]):
            u = asset_url(rel, "img")
            if u:
                image_urls.append(u)

    pdf_url = asset_url(data.get("pdf") or "", "pdf")

    # 预计算检索文本(小写),避免每次检索重复拼接
    haystack = " \n".join([title, source, date, category, subcategory,
                           author, summary, body]).lower()

    return {
        "id": aid, "title": title, "source": source, "date": date,
        "category": category, "subcategory": subcategory, "author": author,
        "summary": summary, "body": body,
        "image_urls": image_urls, "pdf_url": pdf_url,
        "has_image": len(image_urls) > 0, "has_pdf": pdf_url is not None,
        "_haystack": haystack,
    }


def _iter_json_files():
    if not os.path.isdir(DATA_DIR):
        return []
    out = []
    for root, _dirs, files in os.walk(DATA_DIR):
        for fn in files:
            if fn.lower().endswith(".json"):
                out.append(os.path.join(root, fn))
    return out


def scan_articles(force=False):
    """扫描 data 目录,重建内存索引(线程安全,可重入)。"""
    with _scan_lock:
        articles = []
        seen_ids = set()
        for path in _iter_json_files():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                m = normalize(item, path)
                if not m:
                    continue
                if m["id"] in seen_ids:  # id 冲突时保留后扫描的会被跳过
                    continue
                seen_ids.add(m["id"])
                articles.append(m)
        # 按刊发日期倒序,无日期的排最后
        articles.sort(key=lambda a: a["date"] or "", reverse=True)
        by_id = {a["id"]: a for a in articles}
        global _articles, _by_id, _last_scan, _watched_mtimes
        with _state_lock:
            _articles, _by_id = articles, by_id
            _last_scan = time.time()
            _watched_mtimes = _snapshot_mtimes()
        return articles


def _snapshot_mtimes():
    """数据目录与配置文件的修改时间快照,用于自动重载判断。"""
    mt = []
    try:
        st = os.stat(DATA_DIR)
        mt.append(("data", st.st_mtime))
    except OSError:
        pass
    try:
        st = os.stat(CONFIG_PATH)
        mt.append(("cfg", st.st_mtime))
    except OSError:
        pass
    return tuple(mt)


def maybe_rescan(throttle_seconds=2.0):
    """目录内容变化时自动重建索引(节流,避免频繁全量扫描)。"""
    global _last_scan
    if time.time() - _last_scan < throttle_seconds:
        return
    if _snapshot_mtimes() != _watched_mtimes:
        scan_articles()


def meta_only(a):
    return {
        "id": a["id"], "title": a["title"], "source": a["source"],
        "date": a["date"], "category": a["category"], "subcategory": a["subcategory"],
        "author": a["author"], "summary": a["summary"],
        "has_image": a["has_image"], "has_pdf": a["has_pdf"],
    }


# ---------------------------------------------------------------------------
# 检索(统一入口:列表与搜索共用)
# ---------------------------------------------------------------------------
def search(q="", source="", date_from="", date_to="", category="", subcategory=""):
    q = (q or "").strip()
    kws = [k for k in re.split(r"\s+", q.lower()) if k] if q else []
    date_from = norm_date(date_from) or str(date_from or "").strip()
    date_to = norm_date(date_to) or str(date_to or "").strip()
    out = []
    for a in _articles:
        if category and a["category"] != category:
            continue
        if subcategory and a["subcategory"] != subcategory:
            continue
        if source and a["source"] != source:
            continue
        if date_from and a["date"] < date_from:
            continue
        if date_to and a["date"] > date_to:
            continue
        if kws and not all(k in a["_haystack"] for k in kws):
            continue
        out.append(a)
    return out


def get_article(aid):
    return _by_id.get(aid)


# ---------------------------------------------------------------------------
# 配置(附带各分类文章计数)
# ---------------------------------------------------------------------------
def get_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if k == "categories":
                    if v:
                        cfg["categories"] = v
                else:
                    cfg[k] = v
        except Exception:
            pass
    # 来源与分类计数从数据动态生成
    sources = sorted({a["source"] for a in _articles if a["source"]})
    count_cat, count_sub = {}, {}
    for a in _articles:
        if a["category"]:
            count_cat[a["category"]] = count_cat.get(a["category"], 0) + 1
            if a["subcategory"]:
                key = (a["category"], a["subcategory"])
                count_sub[key] = count_sub.get(key, 0) + 1
    cfg["sources"] = sources
    cfg["counts"] = {"total": len(_articles), "category": count_cat,
                     "subcategory": {"%s/%s" % k: v for k, v in count_sub.items()}}
    return cfg


# ---------------------------------------------------------------------------
# HTML 页面(内联在前端 index.html,打包时一并带入)
# ---------------------------------------------------------------------------
def load_index_html():
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, "index.html"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))
    candidates.append(os.path.join(BASE, "index.html"))
    for c in candidates:
        if os.path.isfile(c):
            with open(c, "r", encoding="utf-8") as f:
                return f.read()
    return "<!doctype html><html><body>未找到前端页面 index.html</body></html>"


INDEX_HTML = load_index_html()

# 安全响应头(静态资源与页面统一附加;CSP 允许内联样式/脚本,单文件离线应用所需)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'self'"
    ),
}


# ---------------------------------------------------------------------------
# HTTP 处理器
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "LocalNewsSearch/2.0"

    def log_message(self, *args):  # 静默访问日志,避免控制台刷屏
        pass

    # ---- 基础发送 ----
    def _send(self, code, body, content_type, extra_headers=None, head_only=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def send_html(self, html, head_only=False):
        self._send(200, html, "text/html; charset=utf-8", head_only=head_only)

    def send_json(self, obj, code=200, head_only=False):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8", head_only=head_only)

    # ---- 请求分发 ----
    def do_HEAD(self):
        self._route(head_only=True)

    def do_GET(self):
        self._route(head_only=False)

    def _route(self, head_only):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self.send_html(INDEX_HTML, head_only)
        if path == "/favicon.ico":
            return self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon", head_only=head_only)

        if path == "/api/config":
            maybe_rescan()
            return self.send_json(get_config(), head_only=head_only)
        if path == "/api/articles":
            if qs.get("reload", ["0"])[0] == "1":
                scan_articles(True)
            else:
                maybe_rescan()
            res = search(category=qs.get("category", [""])[0],
                         subcategory=qs.get("subcategory", [""])[0])
            items = [meta_only(a) for a in res]
            return self.send_json({"count": len(items), "items": items}, head_only=head_only)
        if path == "/api/search":
            maybe_rescan()
            res = search(q=qs.get("q", [""])[0],
                         source=qs.get("source", [""])[0],
                         date_from=qs.get("from", [""])[0],
                         date_to=qs.get("to", [""])[0],
                         category=qs.get("category", [""])[0],
                         subcategory=qs.get("subcategory", [""])[0])
            items = [meta_only(a) for a in res]
            return self.send_json({"count": len(items), "items": items}, head_only=head_only)
        if path == "/api/article":
            maybe_rescan()
            a = get_article(qs.get("id", [""])[0])
            if not a:
                return self.send_json({"error": "未找到该文章"}, 404, head_only=head_only)
            return self.send_json(a, head_only=head_only)

        if path.startswith("/data/"):
            return self.serve_data(path[len("/data/"):], head_only)

        return self.send_json({"error": "接口不存在"}, 404, head_only=head_only)

    # ---- 静态资源(路径穿越防护) ----
    def serve_data(self, rel_raw, head_only=False):
        rel = _safe_relpath(rel_raw)
        if rel is None:
            return self.send_json({"error": "非法路径"}, 403, head_only=head_only)
        full = os.path.normpath(os.path.join(DATA_DIR, rel.replace("/", os.sep)))
        base = os.path.normpath(DATA_DIR)
        try:
            if os.path.commonpath([base, full]) != base:
                return self.send_json({"error": "非法路径"}, 403, head_only=head_only)
        except ValueError:  # 跨盘等异常
            return self.send_json({"error": "非法路径"}, 403, head_only=head_only)
        if not os.path.isfile(full):
            return self.send_json({"error": "文件不存在"}, 404, head_only=head_only)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            return self.send_json({"error": "读取失败"}, 500, head_only=head_only)
        extra = {}
        if ctype == "application/pdf":
            # 文件名做响应头注入清洗 + RFC 5987 编码
            fname = os.path.basename(full)
            safe = re.sub(r'[\r\n\"\\]+', "_", fname)
            extra["Content-Disposition"] = (
                "inline; filename=\"%s\"; filename*=UTF-8''%s" %
                (safe, urllib.parse.quote(fname))
            )
        self._send(200, data, ctype, extra, head_only=head_only)


# ---------------------------------------------------------------------------
# 服务启停
# ---------------------------------------------------------------------------
_server = None


def run_server(host="127.0.0.1", start_port=8765):
    global _server
    scan_articles()
    port = start_port
    while True:
        try:
            s = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            port += 1
            if port > start_port + 200:
                raise RuntimeError("无可用的本地端口")
    _server = s
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return port


def stop_server():
    if _server:
        try:
            _server.shutdown()
            _server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    p = run_server()
    print("服务已启动: http://127.0.0.1:%d/" % p)
    try:
        import time as _t
        while True:
            _t.sleep(1)
    except KeyboardInterrupt:
        stop_server()
