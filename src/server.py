#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地离线检索服务（纯标准库，无需联网）
- 启动时扫描 data 目录下的全部 *.json，建立内存索引
- 提供导航配置、文章列表、检索、详情、静态资源等接口
- 新增文章只需把 JSON / 配图 / PDF 放进 data 目录，重启程序即自动加载
"""
import os
import sys
import json
import re
import mimetypes
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# 外部目录定位：始终相对于"被启动的程序本体"所在目录，
# 这样打包成 exe 后，config.json 与 data/ 放在 exe 同目录即可，无需重新编译。
# ---------------------------------------------------------------------------
def app_base_dir():
    # sys.argv[0] 为用户实际启动的程序路径（onefile 模式下指向真实 exe 位置）
    return os.path.dirname(os.path.abspath(sys.argv[0]))

BASE = app_base_dir()
CONFIG_PATH = os.path.join(BASE, "config.json")
DATA_DIR = os.path.join(BASE, "data")

# 内存索引与锁
_articles = []
_lock = threading.Lock()

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
# 扫描与归一化
# ---------------------------------------------------------------------------
def normalize(data, path):
    """把单篇原始 JSON 整理为统一结构；非法条目返回 None。"""
    if not isinstance(data, dict):
        return None
    title = str(data.get("title", "")).strip()
    if not title:
        return None
    aid = str(data.get("id") or os.path.splitext(os.path.basename(path))[0]).strip()
    date = str(data.get("date", "")).strip()
    source = str(data.get("source", "")).strip()
    category = str(data.get("category", "")).strip()
    subcategory = str(data.get("subcategory", "")).strip()
    author = str(data.get("author", "")).strip()
    summary = str(data.get("summary", "")).strip()

    body = data.get("body", "")
    if isinstance(body, list):
        body = "\n\n".join(str(p) for p in body)
    body = str(body)

    # 配图：支持字符串或列表，均为相对 data 目录的路径
    image = data.get("image")
    image_urls = []
    if image:
        for rel in (image if isinstance(image, list) else [image]):
            rel = str(rel).strip().lstrip("/\\")
            if not rel:
                continue
            full = os.path.normpath(os.path.join(DATA_DIR, rel))
            if os.path.isfile(full):
                image_urls.append("/data/" + rel.replace("\\", "/"))

    # 原始 PDF
    pdf = data.get("pdf")
    pdf_url = None
    if pdf:
        rel = str(pdf).strip().lstrip("/\\")
        if rel:
            full = os.path.normpath(os.path.join(DATA_DIR, rel))
            if os.path.isfile(full):
                pdf_url = "/data/" + rel.replace("\\", "/")

    return {
        "id": aid,
        "title": title,
        "source": source,
        "date": date,
        "category": category,
        "subcategory": subcategory,
        "author": author,
        "summary": summary,
        "body": body,
        "image_urls": image_urls,
        "pdf_url": pdf_url,
        "has_image": len(image_urls) > 0,
        "has_pdf": pdf_url is not None,
    }


def scan_articles(force=False):
    """扫描 data 目录，重建内存索引。"""
    global _articles
    with _lock:
        articles = []
        if os.path.isdir(DATA_DIR):
            for root, _dirs, files in os.walk(DATA_DIR):
                for fn in files:
                    if not fn.lower().endswith(".json"):
                        continue
                    path = os.path.join(root, fn)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        continue
                    if isinstance(data, list):
                        for item in data:
                            m = normalize(item, path)
                            if m:
                                articles.append(m)
                    else:
                        m = normalize(data, path)
                        if m:
                            articles.append(m)
        # 按刊发日期倒序，无日期的排最后
        articles.sort(key=lambda a: a.get("date") or "", reverse=True)
        _articles = articles
    return _articles


def meta_only(a):
    return {
        "id": a["id"],
        "title": a["title"],
        "source": a["source"],
        "date": a["date"],
        "category": a["category"],
        "subcategory": a["subcategory"],
        "author": a["author"],
        "summary": a["summary"],
        "has_image": a["has_image"],
        "has_pdf": a["has_pdf"],
    }


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------
def search(q="", source="", date_from="", date_to="", category="", subcategory=""):
    q = (q or "").strip()
    kws = [k for k in re.split(r"\s+", q.lower()) if k] if q else []
    results = []
    for a in _articles:
        if category and a["category"] != category:
            continue
        if subcategory and a["subcategory"] != subcategory:
            continue
        if source and a["source"] != source:
            continue
        if date_from and (a["date"] < date_from):
            continue
        if date_to and (a["date"] > date_to):
            continue
        if kws:
            hay = (a["title"] + " " + a["summary"] + " " + a["body"] +
                   " " + a["author"] + " " + a["source"]).lower()
            if not all(k in hay for k in kws):
                continue
        results.append(a)
    return results


# ---------------------------------------------------------------------------
# 配置
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
    # 来源列表从数据动态生成，供前端下拉筛选
    srcs = sorted({a["source"] for a in _articles if a["source"]})
    cfg["sources"] = srcs
    return cfg


# ---------------------------------------------------------------------------
# HTML 页面（内联在前端 index.html，打包时一并带入）
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


# ---------------------------------------------------------------------------
# HTTP 处理器
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "LocalNewsSearch/1.0"

    def log_message(self, *args):  # 静默访问日志，避免控制台刷屏
        pass

    def _send(self, code, body, content_type, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        self._send(200, html, "text/html; charset=utf-8")

    def send_json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self.send_html(INDEX_HTML)
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")

        if path == "/api/config":
            return self.send_json(get_config())
        if path == "/api/articles":
            if qs.get("reload", ["0"])[0] == "1":
                scan_articles(True)
            cat = qs.get("category", [""])[0]
            sub = qs.get("subcategory", [""])[0]
            items = [meta_only(a) for a in _articles]
            if cat:
                items = [i for i in items if i["category"] == cat]
            if sub:
                items = [i for i in items if i["subcategory"] == sub]
            return self.send_json({"count": len(items), "items": items})
        if path == "/api/search":
            q = qs.get("q", [""])[0]
            source = qs.get("source", [""])[0]
            frm = qs.get("from", [""])[0]
            to = qs.get("to", [""])[0]
            cat = qs.get("category", [""])[0]
            sub = qs.get("subcategory", [""])[0]
            res = search(q, source, frm, to, cat, sub)
            items = [meta_only(a) for a in res]
            return self.send_json({"count": len(items), "items": items})
        if path == "/api/article":
            aid = qs.get("id", [""])[0]
            a = next((x for x in _articles if x["id"] == aid), None)
            if not a:
                return self.send_json({"error": "未找到该文章"}, 404)
            return self.send_json(a)

        if path.startswith("/data/"):
            return self.serve_data(path[len("/data/"):])

        return self.send_json({"error": "接口不存在"}, 404)

    def serve_data(self, rel):
        rel = rel.replace("\\", "/")
        # 路径穿越防护
        base = os.path.normpath(DATA_DIR)
        full = os.path.normpath(os.path.join(DATA_DIR, rel))
        if not full.startswith(base + os.sep) and full != base:
            return self.send_json({"error": "非法路径"}, 403)
        if not os.path.isfile(full):
            return self.send_json({"error": "文件不存在"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception:
            return self.send_json({"error": "读取失败"}, 500)
        extra = {}
        if ctype == "application/pdf":
            extra["Content-Disposition"] = 'inline; filename="' + os.path.basename(full) + '"'
        self._send(200, data, ctype, extra)


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
    print("服务已启动： http://127.0.0.1:%d/" % p)
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_server()
