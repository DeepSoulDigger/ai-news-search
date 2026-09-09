# 人工智能报道检索平台(报纸AI主题报道 · 检索与阅研)

面向领导阅研的报纸人工智能主题报道检索工具,**完全离线、无需联网**,当前收录主库电子化文章 102 篇(含原版 PDF)。提供两种部署形态:

| 形态 | 适用 | 入口 |
|---|---|---|
| **服务器网页服务(推荐)** | Linux + Docker,内网多人访问 | `docker compose up -d --build`,详见 `deploy/部署说明.md` |
| Windows 单机离线版 | 单机阅研,双击即用 | 打包 `AI报纸检索.exe`,见下文"构建(Windows)" |
程序启动自动扫描数据目录加载文章，新增文章放入目录即可，**无需重新编译**。

## 目录结构

```
ai-news-search/
├─ AI报纸检索.exe      # 独立可执行程序（构建产出，位于 dist/）
├─ config.json         # 导航与标题配置（一级大类 + 二级子类，可手动维护）
├─ data/               # 文章数据目录（随用随增）
│  ├─ *.json           # 每篇报道一个 JSON
│  ├─ img/             # 配图
│  └─ pdf/             # 原始报纸版面 PDF
├─ docs/               # 操作使用手册（.md + 可打印 .html）
├─ src/                # 完整源代码
│  ├─ app.py           # 启动器：本地服务 + 打开浏览器 + 运行中窗口
│  ├─ server.py        # 本地检索服务（纯标准库：扫描/检索/接口/静态资源）
│  └─ index.html       # 前端单页（内联 CSS/JS，零外部依赖，离线）
├─ tools/
│  └─ make_samples.py  # 生成样例数据（演示用，可删除）
└─ README.md
```

## 运行（使用者）

将交付文件夹整体复制，双击 `AI报纸检索.exe` 即可。详见 `docs/使用手册.md`。

## 构建（Windows 单机版）

环境：Python 3.10+。使用受管/虚拟环境安装 PyInstaller：

```bash
python -m venv venv && venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed ^
  --name "AI报纸检索" ^
  --add-data "src\index.html;." ^
  --hidden-import server ^
  src\app.py
```

产出位于 `dist\AI报纸检索.exe`。将 `config.json`、`data\`、`docs\` 与之放在同一目录即为最终交付物。

## 数据格式

每篇报道一个 JSON，关键字段：`title`(必填)、`body`(必填)、`source`、`date`(YYYY-MM-DD)、
`category` / `subcategory`(须与 config.json 名称一致)、`author`、`summary`、
`image`(相对 data 目录路径)、`pdf`(相对 data 目录路径)、`id`(可选)。详见使用手册。

## 设计要点

- **纯标准库**：仅用 `http.server` / `tkinter` / `webbrowser`，无第三方运行依赖，便于离线打包。
- **外部配置 + 自动扫描**：分类在 `config.json` 维护（当前为 7 个一级 / 24 个二级标签体系），文章靠目录扫描加载，目录变化约 2 秒内自动重载，数据与程序解耦。
- **离线安全**：所有资源经本地 HTTP 服务（127.0.0.1）提供，含路径穿越防护与安全响应头；不发起任何网络请求。安全审查记录见 `docs/安全审查.md`。
- **适老化**：大字号、大按钮、两层导航、单篇直显，操作极简。
