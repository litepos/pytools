```markdown
# 🧭 Auto Sort Softwares - 分类与整理工具

本工具用于自动扫描并分类本地软件安装包、绿色软件及企业内部工具。  
支持图形界面预览、规则匹配、按需移动、日志记录与空目录清理。  
适合企业环境中长期维护的软件仓库管理。

---

## 📁 推荐目录结构

在 `D:\Software\` 下统一存放各分类文件夹（脚本自动识别、按需创建）：

```

D:\\Software
│
├─ dev\_tools           # 开发工具类，如 IDEA / VSCode / Git / Node / Python
├─ db\_tools            # 数据库类工具，如 DBeaver / Toad / Navicat
├─ office\_tools        # 办公类，如 Office / WPS / PDF 工具
├─ design\_media        # 设计与多媒体类，如 Photoshop / Axure / Adobe 系列
├─ testing\_tools       # 测试与分析类，如 SoapUI / Postman / JMeter
├─ network\_tools       # 网络运维类，如 MobaXterm / XShell / FRP / Wireshark
├─ ai\_tools            # AI / 智能类，如 ChatGPT / Copilot / Dify / Windsurf
├─ system\_tools        # 系统维护与驱动类，如 驱动总裁 / L15150 打印机 / BIOS 更新
├─ cloud\_sync          # 云盘与同步类，如 百度网盘 / 115 / 阿里云盘 / Rclone
├─ communication       # 通讯协作类，如 WeChat / QQ / 钉钉 / RemoteDesktop
├─ enterprise\_ql       # 企业内部软件，如 齐鲁智见 / QL\_Portal / QiluSmartAgent
├─ software\_portable   # 绿色、免安装、便携软件（手工或规则识别）
└─ install\_misc        # 兜底分类（未命中规则、临时包）

```

---

## 🚀 使用说明

### 1. 运行环境
- 系统：Windows 10/11  
- Python：3.8+  
- 依赖：标准库（无需额外安装）

### 2. 文件放置
将以下文件放在同一目录（建议放 `D:\Software\Tools\AutoSort`）：
```

auto\_sort\_gui.py
category\_rules.txt

```

### 3. 运行方式
```bash
python auto_sort_gui.py
```

或直接双击运行。

---

## 🖥️ 功能说明


| 功能                 | 说明                                        |
| -------------------- | ------------------------------------------- |
| **选择目录**         | 选择要扫描的根目录（建议选择`D:\Software`） |
| **扫描分类**         | 按`category_rules.txt`匹配，生成分类预览表  |
| **预览汇总**         | 查看各分类数量；双击分类高亮主表对应项      |
| **执行移动**         | 按分类将文件移动至对应文件夹（自动建目录）  |
| **仅移动选中项**     | 仅移动当前选中的条目（多选支持 Ctrl/Shift） |
| **执行后删除空目录** | 清理根目录下一层未使用的空目录              |
| **清空结果**         | 清空主表、日志与进度条，重新开始操作        |
| **日志输出**         | 实时记录匹配与移动结果                      |
| **自适应拉伸**       | 主表与日志区随窗口调整自动伸缩              |

---

## 🧠 分类规则说明 (`category_rules.txt`)

规则文件定义匹配模式与分类目录，每块以 `# target_dir:` 开头。
示例片段：

```text
# target_dir: system_tools
driver|驱动|打印机|epson|bios|firmware|l15150|sysdiag|optimizer|windowscleaner
hp|lenovo|dell|thinkpad|intel|nvidia|amd|asus
```

可根据实际情况扩充。
所有匹配使用 **正则表达式**（不区分大小写），按顺序匹配，先命中先分类。

---

## ⚙️ 建议使用方式

1. 所有待整理的安装包、压缩包放在 `D:\Software\待分类` 目录。
2. 运行程序 → 选择 `D:\Software` 作为扫描根目录。
3. 扫描、预览、确认分类 → 执行移动。
4. 执行完成后，可选“删除空目录”清理环境。

---

## 🧩 附加说明

* 程序**不会修改文件名**，仅移动位置。
* 已存在同名文件会跳过（状态：已存在）。
* 绿色软件（portable）与企业内部软件（QL）会自动识别分类。
* 若扫描路径选错（如选到子目录），只会创建目录，不会误删文件。

---

## 📦 后续计划

* 增加分类过滤下拉框
* 导出当前预览结果为 CSV
* 支持递归扫描模式（可选）
* 支持配置文件持久化（记住上次选择目录）

---

**作者**：内部自动化项目组
**版本**：v5.0 GUI Release
**最后更新**：2025-10

```

---

是否希望我在这份 README 里，再自动生成一个可执行的 **初始化脚本（PowerShell）**，用于一次性创建所有分类目录？（适合你新电脑或同事部署）
```


pyinstaller -F -w caps_qrun_helper.py
