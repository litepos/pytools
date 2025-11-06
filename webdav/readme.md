下面是为你生成的 **README.md 模板**，专门配合你这版 GUI 程序使用。内容包含：

* 环境准备
* WinFsp 安装说明（特别强调）
* 首次配置与使用步骤
* 开机自动挂载说明
* 常见问题

---

```markdown
# 🧭 Rclone 挂载助手 (Rclone Mount GUI)

一个基于 **Python + Tkinter** 开发的轻量级图形工具，用于将 **AList 的 WebDAV 服务** 挂载为 Windows 本地磁盘或网络驱动器。

---

## 📦 一、运行环境

- **Windows 10 / 11**
- **Python 3.8+**（若已打包成 EXE 可直接双击运行）
- **rclone.exe** （放在同目录或系统 PATH 中）

---

## ⚙️ 二、⚠️ 必须先安装 WinFsp

Rclone 在 Windows 上挂载盘符依赖 **WinFsp 驱动**。  
如未安装，挂载后会出现 “已启动但盘符未就绪” 的提示。

1. 访问官网：<https://winfsp.dev/>  
2. 下载并安装最新版（推荐 2.1 稳定版或以上）  
3. 安装完成后，CMD 中执行以下命令验证：
   ```bash
   sc query WinFsp
```

若显示 `RUNNING` 即表示安装并运行成功。

---

## 🧩 三、首次配置步骤

1. 选择 `rclone.exe` 路径
2. 保持默认配置项：
   * WebDAV URL：`https://sdumba.cn:5243`
   * 用户名：`admin`
   * 密码：输入你的 AList 登录密码
   * 勾选 `--vfs-cache-mode=writes` 与 `--links`
   * （默认不勾选 `--network-mode`，表示本地盘模式速度更快）
3. 点击 **【写入/更新 rclone 配置】**
   * 程序会自动执行 `rclone obscure` 混淆密码并写入到
     `%APPDATA%\rclone\rclone.conf`
   * 若显示验证成功，说明配置完成。
4. 点击 **【挂载（后台）】**
   * 等待 2 \~ 3 秒后盘符出现（默认 Z: 或 W:）
   * 关闭窗口不影响挂载进程。
5. 点击 **【卸载】** 可立即解除挂载。

---

## 🚀 四、开机自动挂载

1. 在 GUI 中点击 **【创建登录自启任务】**
   * 程序会创建一个计划任务
     名称：`RcloneMountGUI-Mount`
   * 登录系统时自动后台挂载。
2. 若想取消自动挂载
   点击 **【删除自启任务】** 即可。

---

## 🧠 五、常见问题


| 问题                             | 原因与解决办法                                                   |
| -------------------------------- | ---------------------------------------------------------------- |
| `405 Method Not Allowed`         | WebDAV 路径不正确，请将 URL 改为`https://sdumba.cn:5243/dav`     |
| 挂载后提示“已启动但盘符未就绪” | WinFsp 未安装或服务未启动，请安装并重启                          |
| 无法验证 rclone                  | 确认`rclone.exe`可用，建议执行`rclone version`检查               |
| 想让磁盘显示为“网络位置”       | 勾选`--network-mode`后再挂载                                     |
| 想限制缓存大小                   | 后续版本可自定义`--vfs-cache-max-size`/`--vfs-cache-max-age`参数 |

---

## 📁 六、配置文件位置

* GUI 配置：
  `%APPDATA%\RcloneMountGUI\config.json`
* rclone 配置：
  `%APPDATA%\rclone\rclone.conf`

可用记事本打开查看。

---

## ✨ 七、作者说明

* 作者：litepos
* 版本：2025.11
* 功能：AList WebDAV → Rclone → Windows 挂载
* 技术：Python 3.11 + Tkinter + WinFsp + Rclone CLI

---

> ✅ 提示：安装 WinFsp 后即可正常使用所有功能；
> 建议首选“本地磁盘模式”，若需网络盘外观再勾选 `--network-mode`。


## 打包成 EXE（可选）

有 Python 环境时运行即可；如果需要独立分发：

<pre class="overflow-visible!" data-start="12608" data-end="12681"><div class="contain-inline-size rounded-2xl relative bg-token-sidebar-surface-primary"><div class="sticky top-9"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-bash"><span><span>pip install pyinstaller
pyinstaller -F -w rclone_mount_gui.py
</span></span></code></div></div></pre>

* `-F` 单文件
* `-w` 无控制台（GUI 程序）
  生成的 EXE 在 `dist/` 目录。
