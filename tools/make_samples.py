#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成样例数据：报纸人工智能主题报道 JSON + 占位配图(PNG) + 占位原始PDF。
仅用于演示自动扫描加载；用户可删除 data/ 下样例，放入自己的文章。"""
import os, json, zlib, struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
IMG = os.path.join(DATA, "img")
PDF = os.path.join(DATA, "pdf")
os.makedirs(IMG, exist_ok=True)
os.makedirs(PDF, exist_ok=True)


def write_png(path, w=640, h=360):
    """生成一张"照片占位"风格的 PNG（纯标准库绘制，可整体替换为真实配图）。"""
    buf = bytearray()
    for y in range(h):
        buf.append(0)  # filter type 0
        for x in range(w):
            # 天空渐变
            if y < h * 0.62:
                t = y / (h * 0.62)
                r = int(207 + (174 - 207) * t)
                g = int(224 + (200 - 224) * t)
                b = int(243 + (212 - 243) * t)
            else:  # 地面
                t = (y - h * 0.62) / (h * 0.38)
                r = int(214 + (188 - 214) * t)
                g = int(205 + (180 - 205) * t)
                b = int(180 + (156 - 180) * t)
            # 太阳
            sx, sy, sr = int(w * 0.78), int(h * 0.22), 30
            if (x - sx) ** 2 + (y - sy) ** 2 <= sr ** 2:
                r, g, b = 255, 214, 107
            # 远山（三角形）
            if y > h * 0.45 and y < h * 0.66:
                peak = int(w * 0.32)
                half = int((y - h * 0.45) / (h * 0.21) * (w * 0.30))
                if abs(x - peak) <= half:
                    r, g, b = 120, 150, 175
            buf += bytes((r, g, b))
    raw = bytes(buf)
    comp = zlib.compress(raw)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", comp))
        f.write(chunk(b"IEND", b""))


def build_pdf(lines, path):
    """生成最小可用的一页 PDF（占位用，内容为英文说明；可整体替换为真实报纸版面 PDF）。"""
    content = ["BT", "/F1 15 Tf", "60 770 Td", "22 TL"]
    for i, ln in enumerate(lines):
        safe = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content.append(('(' + safe + ') Tj') if i == 0 else ("(" + safe + ") '"))
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")

    objs = []
    objs.append(b"<</Type/Catalog/Pages 2 0 R>>")
    objs.append(b"<</Type/Pages/Kids[3 0 R]/Count 1>>")
    objs.append(b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>")
    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    objs.append(b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (b"trailer\n<</Size " + str(len(objs) + 1).encode() +
            b"/Root 1 0 R>>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    with open(path, "wb") as f:
        f.write(out)


ARTICLES = [
    {
        "id": "20240115-rmrb-001",
        "title": "人工智能成为新一轮科技革命和产业变革的重要驱动力量",
        "source": "人民日报",
        "date": "2024-01-15",
        "category": "政策解读",
        "subcategory": "国家战略",
        "author": "本报记者",
        "summary": "把握人工智能发展的战略机遇，推动经济社会高质量发展。",
        "body": "人工智能是新一轮科技革命和产业变革的重要驱动力量，加快发展新一代人工智能，是事关我国能否抓住新一轮科技革命和产业变革机遇的战略问题。\n\n近年来，我国人工智能技术快速发展，应用场景不断拓展，在智能制造、智慧城市、智慧医疗等领域取得积极成效，为经济社会发展注入了新动能。\n\n同时也要看到，人工智能发展仍面临基础理论、核心算法、关键部件等方面的短板。要坚持问题导向，加强基础研究，补齐短板弱项，推动人工智能朝着有益、安全、可控的方向发展。\n\n各地区各部门要立足自身实际，因地制宜探索人工智能与实体经济深度融合的路径，让人工智能更好赋能高质量发展。",
    },
    {
        "id": "20240220-gov-002",
        "title": "“十四五”规划明确人工智能发展路线图",
        "source": "经济日报",
        "date": "2024-02-20",
        "category": "政策解读",
        "subcategory": "规划文件",
        "author": "本报记者",
        "summary": "规划对人工智能基础理论研究、关键技术攻关和产业应用作出系统部署。",
        "body": "“十四五”规划纲要对人工智能发展作出专门部署，明确提出要瞄准人工智能前沿领域，集中优势资源攻关，在类脑智能、量子信息、集成电路等前沿方向取得突破。\n\n规划强调，要推动互联网、大数据、人工智能同实体经济深度融合，培育壮大人工智能产业，建设一批重要的人工智能创新平台。\n\n有关部门将围绕规划部署，进一步完善政策举措，优化产业生态，为人工智能健康发展提供坚实保障。",
    },
    {
        "id": "20240310-rmrb-003",
        "title": "国产大模型加速迭代 应用生态持续繁荣",
        "source": "人民日报",
        "date": "2024-03-10",
        "category": "技术创新",
        "subcategory": "大模型",
        "author": "本报记者",
        "summary": "国产大模型在中文理解与生成能力上稳步提升，行业应用加速落地。",
        "body": "近年来，国产大模型研发步伐明显加快，在中文理解、知识问答、文本生成等任务上的表现稳步提升，逐步构建起涵盖基础模型、工具平台和行业应用的完整生态。\n\n在办公、教育、医疗、政务等场景，大模型正从“尝鲜”走向“实用”，帮助一线人员提升效率、降低门槛。\n\n专家普遍认为，大模型的健康发展离不开高质量数据、可靠算力与规范治理的协同推进。",
    },
    {
        "id": "20240405-kejrb-004",
        "title": "自主算力芯片取得突破 支撑智能算力供给",
        "source": "科技日报",
        "date": "2024-04-05",
        "category": "技术创新",
        "subcategory": "算力芯片",
        "author": "本报记者",
        "summary": "面向人工智能训练的算力芯片加快研制，为模型训练提供底层支撑。",
        "body": "算力是人工智能发展的底座。近年来，我国企业在人工智能芯片架构、制程工艺和软件生态方面持续投入，部分产品已具备规模化应用能力。\n\n在数据中心和智算中心建设中，国产算力芯片的占比逐步提升，为大规模模型训练与推理提供了更加多元的供给选择。\n\n下一步，还需在软硬协同、 compilers 与开发框架适配等方面持续发力，真正把算力转化为产业竞争力。",
    },
    {
        "id": "20240512-rmrb-005",
        "title": "人工智能辅助诊疗在多家医院落地",
        "source": "人民日报",
        "date": "2024-05-12",
        "category": "产业应用",
        "subcategory": "智慧医疗",
        "author": "本报记者",
        "summary": "AI 辅助诊断系统帮助医生提升影像识别效率，惠及更多患者。",
        "body": "在多家三甲医院，人工智能辅助诊疗系统已投入日常使用，能够对医学影像进行快速初筛和提示，辅助医生提高诊断效率。\n\n临床实践表明，人工智能在肺结节筛查、眼底检查等场景中表现出较高的灵敏度，有助于疾病早发现、早干预。\n\n医疗机构强调，人工智能始终是医生的助手而非替代，最终诊断仍需由具备资质的医务人员作出。",
        "image": "img/20240512-rmrb-005.png",
        "pdf": "pdf/20240512-rmrb-005.pdf",
    },
    {
        "id": "20240618-zzw-006",
        "title": "智能政务助手上线 群众办事更便捷",
        "source": "中国新闻网",
        "date": "2024-06-18",
        "category": "社会治理",
        "subcategory": "政务服务",
        "author": "本报记者",
        "summary": "依托自然语言处理技术，政务助手可解答高频咨询、引导办事流程。",
        "body": "某地政务服务中心上线智能政务助手，依托自然语言处理技术，能够解答社保、医保、不动产登记等高频咨询，并引导群众完成线上办事流程。\n\n据中心负责人介绍，智能助手上线后，人工窗口的重复性咨询明显减少，群众平均等待时间显著缩短。\n\n相关负责人表示，将持续完善知识库，在确保安全合规的前提下，让数据多跑路、群众少跑腿。",
        "image": "img/20240618-zzw-006.png",
    },
    {
        "id": "20240722-gjx-007",
        "title": "全球主要经济体加快人工智能战略布局",
        "source": "参考消息",
        "date": "2024-07-22",
        "category": "国际视野",
        "subcategory": "域外动态",
        "author": "本报记者",
        "summary": "多国相继出台人工智能战略，围绕研发投人与治理规则展开竞争与合作。",
        "body": "近期，全球多个主要经济体相继出台或更新人工智能发展战略，围绕基础研究投入、产业培育和人才培养展开布局。\n\n在治理层面，各国围绕安全、伦理与跨境数据流动等议题加强对话，试图在促进创新与防范风险之间寻求平衡。\n\n分析人士指出，人工智能的全球治理仍处于起步阶段，国际社会需要更多协调与共识。",
    },
    {
        "id": "20240830-fzb-008",
        "title": "完善数据安全管理 护航人工智能健康发展",
        "source": "法制日报",
        "date": "2024-08-30",
        "category": "伦理安全",
        "subcategory": "数据安全",
        "author": "本报记者",
        "summary": "在释放数据价值的同时，须筑牢数据安全与个人信息保护防线。",
        "body": "人工智能的进步高度依赖数据，但数据的收集、存储与使用也必须纳入法治轨道。如何在释放数据价值与保护个人权益之间取得平衡，是摆在面前的现实课题。\n\n有关方面正加快推进数据分类分级保护，明确重要数据和核心数据的管理要求，压实处理者的安全义务。\n\n专家强调，只有把安全底座打牢，人工智能才能行稳致远，真正造福社会。",
        "pdf": "pdf/20240830-fzb-008.pdf",
    },
]


def main():
    for a in ARTICLES:
        with open(os.path.join(DATA, a["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=2)
        if a.get("image"):
            write_png(os.path.join(DATA, a["image"]))
        if a.get("pdf"):
            build_pdf([
                "AI NEWS RETRIEVAL - SAMPLE PDF",
                "",
                "This is a placeholder for the original",
                "newspaper page PDF.",
                "",
                "Replace it with the real scanned page.",
            ], os.path.join(DATA, a["pdf"]))
    print("样例数据已生成：%d 篇报道" % len(ARTICLES))


if __name__ == "__main__":
    main()
