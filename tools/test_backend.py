#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端自测：启动服务并用 urllib 验证各接口。仅用于开发期验证，不参与交付。"""
import sys, os, json, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 让 server 以项目根目录为 BASE（模拟 exe 与 config/data 同目录）
sys.argv[0] = os.path.join(ROOT, "AI报纸检索.exe")

import importlib.util
spec = importlib.util.spec_from_file_location("server", os.path.join(ROOT, "src", "server.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

PORT = 8799
port = server.run_server(start_port=PORT)
base = "http://127.0.0.1:%d" % port

def get(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))

def raw(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.headers, r.read()

ok = True
def check(name, cond, extra=""):
    global ok
    print(("✅" if cond else "❌") + " " + name + (("  -> " + extra) if extra else ""))
    if not cond: ok = False

# 1. config
cfg = get("/api/config")
check("config 返回 7 个大类", len(cfg.get("categories", [])) == 7, str(len(cfg.get("categories", []))))
check("config 含动态来源", len(cfg.get("sources", [])) > 0, str(cfg.get("sources")))

# 2. articles
art = get("/api/articles")
check("扫描到 8 篇文章", art["count"] == 8, str(art["count"]))
check("文章已按日期倒序", all(art["items"][i]["date"] >= art["items"][i+1]["date"] for i in range(len(art["items"])-1)))

# 3. search 全文
r1 = get("/api/search?q=" + urllib.parse.quote("大模型"))
check("检索 '大模型' 有结果", r1["count"] >= 1, str(r1["count"]))
r2 = get("/api/search?q=" + urllib.parse.quote("大模型 政务"))
check("多关键词 AND 命中减少", r2["count"] <= r1["count"], "%d <= %d" % (r2["count"], r1["count"]))

# 4. 单篇直显逻辑：找一个唯一关键词
uniq = get("/api/search?q=" + urllib.parse.quote("智能政务助手上线"))
check("唯一标题检索 count==1", uniq["count"] == 1, str(uniq["count"]))

# 5. 来源筛选
src = cfg["sources"][0]
rs = get("/api/search?source=" + urllib.parse.quote(src))
check("来源筛选仅返回该来源", all(i["source"] == src for i in rs["items"]), src)

# 6. 日期区间筛选
rd = get("/api/search?from=2024-03-01&to=2024-05-31")
check("日期区间筛选", all("2024-03-01" <= i["date"] <= "2024-05-31" for i in rd["items"]), str(rd["count"]))

# 7. 栏目浏览
rb = get("/api/articles?category=" + urllib.parse.quote("政策解读"))
check("栏目浏览按 category 过滤", all(i["category"] == "政策解读" for i in rb["items"]), str(rb["count"]))

# 8. article 详情（含配图/PDF）
aid = art["items"][0]["id"]
det = get("/api/article?id=" + urllib.parse.quote(aid))
check("详情返回 body", bool(det.get("body")))
check("详情返回 image_urls 或为空列表", isinstance(det.get("image_urls"), list))

# 9. 静态资源：图片与 PDF
img_item = next((i for i in art["items"] if i["has_image"]), None)
if img_item:
    st, hd, _ = raw("/data/img/" + img_item["id"] + ".png")
    check("配图可访问(200,image)", st == 200 and "image" in hd.get("Content-Type",""), str(st))
pdf_item = next((i for i in art["items"] if i["has_pdf"]), None)
if pdf_item:
    st, hd, _ = raw("/data/pdf/" + pdf_item["id"] + ".pdf")
    check("PDF 可访问(200,application/pdf)", st == 200 and "pdf" in hd.get("Content-Type",""), str(st))

# 10. 路径穿越防护
try:
    raw("/data/../config.json")
    check("路径穿越被拦截", False)
except urllib.error.HTTPError as e:
    check("路径穿越被拦截(403/404)", e.code in (403, 404), str(e.code))

# 11. 不存在文章
try:
    get("/api/article?id=not-exist")
    check("不存在文章返回 404", False)
except urllib.error.HTTPError as e:
    check("不存在文章返回 404", e.code == 404, str(e.code))

server.stop_server()
print("\n结果：", "全部通过 ✅" if ok else "存在失败 ❌")
sys.exit(0 if ok else 1)
