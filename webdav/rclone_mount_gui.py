import os
import sys
import json
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser

APP_NAME = "RcloneMountGUI"

# —— 默认配置（含推荐参数）——
DEFAULTS = {
    "rclone_path": "",
    "remote": "alist:",
    "drive": "W:",
    # 基础开关
    "vfs_writes": True,                 # 勾选启用 VFS 缓存参数
    "links": True,                      # 保留硬/符号链接元信息
    "network_mode": False,              # 默认不勾选
    "volname": "AList",
    # WebDAV 远端
    "webdav_url": "https://sdumba.cn:5243/dav",
    "webdav_user": "admin",
    "webdav_pass": "",
    # 高级参数（刷新/缓存）
    "vfs_cache_mode": "full",           # full / writes / minimal / off
    "dir_cache_time": "30s",            # 目录列表缓存时长
    "poll_interval": "15s",             # 轮询变更间隔
    "vfs_cache_max_age": "30m",         # VFS 文件缓存寿命
    "attr_timeout": "10s",              # 文件属性缓存时长
    "cache_dir": r"C:\rclone-cache"     # 本地缓存目录
}

# ----------------- 基础工具函数 -----------------
def appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d

def cfg_path():
    return os.path.join(appdata_dir(), "config.json")

def load_cfg():
    if os.path.exists(cfg_path()):
        try:
            with open(cfg_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                out = DEFAULTS.copy()
                out.update(data)
                return out
        except Exception:
            pass
    return DEFAULTS.copy()

def save_cfg(cfg):
    with open(cfg_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def is_drive_ready(letter):
    if not letter:
        return False
    drv = letter if letter.endswith("\\") else letter + "\\"
    return os.path.exists(os.path.join(drv, "NUL"))

def run_hidden(cmd, cwd=None):
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        cmd, cwd=cwd, startupinfo=si, creationflags=creationflags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def run_capture(cmd, cwd=None, timeout=15):
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        p.kill()
        return -1, "Timeout"

def clean_old_mounts(drive):
    cmds = [
        ["cmd", "/c", f"net use {drive} /delete /y"],
        ["cmd", "/c", f"subst {drive} /D"],
        ["cmd", "/c", f"mountvol {drive} /D"],
        ["cmd", "/c", "taskkill /f /im rclone.exe"]
    ]
    for c in cmds:
        try:
            subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def rclone_guess_from_gui(cfg):
    p = cfg.get("rclone_path", "").strip()
    if p and os.path.isfile(p):
        return p
    return "rclone"

def rclone_conf_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    conf_dir = os.path.join(base, "rclone")
    os.makedirs(conf_dir, exist_ok=True)
    return os.path.join(conf_dir, "rclone.conf")

def obscure_with_rclone(rclone_exe, plaintext):
    code, out = run_capture([rclone_exe, "obscure", plaintext], timeout=10)
    if code != 0:
        raise RuntimeError(out or "rclone obscure failed")
    return out.strip()

def write_remote_to_conf(conf_file, name, url, user, pass_obscured):
    cfg = configparser.ConfigParser()
    if os.path.exists(conf_file):
        cfg.read(conf_file, encoding="utf-8")
    if name not in cfg:
        cfg.add_section(name)
    s = cfg[name]
    s["type"] = "webdav"
    s["url"] = url
    s["vendor"] = "other"
    s["user"] = user
    s["pass"] = pass_obscured
    with open(conf_file, "w", encoding="utf-8") as f:
        cfg.write(f)

def verify_remote(rclone_exe, name):
    return run_capture([rclone_exe, "lsd", f"{name}:"], timeout=15)

import ctypes, getpass, os

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def create_login_task():
    workdir = os.path.dirname(os.path.abspath(sys.argv[0]))
    script  = os.path.abspath(sys.argv[0])
    py      = sys.executable or "python"
    action  = f'/c cd /d "{workdir}" && "{py}" "{script}" --auto'
    task_name = f"{APP_NAME}-Mount"

    # 关键：不要用 /RL HIGHEST；一定要 /RL LIMITED + /IT（交互式）
    #      并明确 /RU 为当前用户名，使其跑在用户会话中，盘符就和手动双击一致可见
    cmd = [
        "schtasks", "/Create",
        "/TN", task_name,
        "/TR", f'cmd {action}',
        "/SC", "ONLOGON",
        "/RL", "LIMITED",        # ← 低权限（等价“不要最高权限运行”）
        "/IT",                   # ← 仅当用户登录并在交互会话中运行
        "/RU", getpass.getuser(),# ← 当前用户
        "/F"
    ]
    return run_capture(cmd, timeout=10) + (task_name,)


def delete_login_task():
    task_name = f"{APP_NAME}-Mount"
    cmd = ["schtasks","/Delete","/TN",task_name,"/F"]
    return run_capture(cmd, timeout=10) + (task_name,)

# ----------------- 构建挂载参数 -----------------
def build_mount_args(cfg):
    args = ["mount", cfg["remote"], cfg["drive"]]

    if cfg.get("vfs_writes", True):
        mode = (cfg.get("vfs_cache_mode") or "full").strip().lower()
        args += [f"--vfs-cache-mode={mode}"]

    if cfg.get("links", True):
        args += ["--links"]

    dct = (cfg.get("dir_cache_time") or "30s").strip()
    pit = (cfg.get("poll_interval") or "15s").strip()
    vma = (cfg.get("vfs_cache_max_age") or "30m").strip()
    ato = (cfg.get("attr_timeout") or "10s").strip()
    cdir = (cfg.get("cache_dir") or r"C:\rclone-cache").strip()

    args += ["--dir-cache-time", dct]
    args += ["--poll-interval", pit]
    args += ["--vfs-cache-max-age", vma]
    args += ["--attr-timeout", ato]
    if cdir:
        args += ["--cache-dir", cdir]

    if cfg.get("network_mode", False):
        args += ["--network-mode"]

    args += ["--volname", cfg.get("volname") or "Rclone"]
    return args

# ----------------- 主界面 -----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rclone 挂载助手")
        # 支持缩放/最大化
        self.minsize(900, 620)
        self.resizable(True, True)

        self.cfg = load_cfg()
        self._build_ui()
        self._refresh_status_async()

    # 小工具：为需要换行的控件设置 wraplength（像素）
    def _wrap(self, widget, px=260):
        try:
            widget.configure(wraplength=px, justify="left")
        except tk.TclError:
            pass

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # rclone.exe 路径
        row0 = ttk.Frame(self); row0.pack(fill="x", expand=False, **pad)
        lbl = ttk.Label(row0, text="rclone.exe 路径（程序位置）：")
        self._wrap(lbl, 250); lbl.pack(side="left")
        self.ent_rclone = ttk.Entry(row0)
        self.ent_rclone.insert(0, self.cfg["rclone_path"])
        self.ent_rclone.pack(side="left", fill="x", expand=True, padx=(6,6))
        ttk.Button(row0, text="浏览…", command=self.pick_rclone).pack(side="left")

        # 远端/盘符/卷名
        row1 = ttk.Frame(self); row1.pack(fill="x", expand=False, **pad)
        lbl = ttk.Label(row1, text="远端名 remote（rclone 远端）：")
        self._wrap(lbl, 240); lbl.pack(side="left")
        self.ent_remote = ttk.Entry(row1, width=16); self.ent_remote.insert(0, self.cfg["remote"]); self.ent_remote.pack(side="left", padx=(6,12))

        lbl = ttk.Label(row1, text="盘符（本地挂载盘）：")
        self._wrap(lbl, 180); lbl.pack(side="left")
        self.ent_drive  = ttk.Entry(row1, width=6);  self.ent_drive.insert(0, self.cfg["drive"]);  self.ent_drive.pack(side="left", padx=(6,12))

        lbl = ttk.Label(row1, text="卷名（资源管理器显示名）：")
        self._wrap(lbl, 220); lbl.pack(side="left")
        self.ent_vol    = ttk.Entry(row1); self.ent_vol.insert(0, self.cfg["volname"]); self.ent_vol.pack(side="left", fill="x", expand=True, padx=(6,0))

        # WebDAV 参数（用于写入 rclone.conf）
        rowW = ttk.LabelFrame(self, text="一键写入 rclone 配置（WebDAV）"); rowW.pack(fill="x", expand=False, **pad)
        lbl = ttk.Label(rowW, text="URL（服务地址）："); self._wrap(lbl, 170)
        lbl.grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.ent_url = ttk.Entry(rowW); self.ent_url.insert(0, self.cfg["webdav_url"])
        self.ent_url.grid(row=0, column=1, sticky="we", padx=6)
        rowW.columnconfigure(1, weight=1)

        lbl = ttk.Label(rowW, text="用户名（登录账户）："); self._wrap(lbl, 170)
        lbl.grid(row=0, column=2, sticky="e", padx=6)
        self.ent_user = ttk.Entry(rowW, width=16); self.ent_user.insert(0, self.cfg["webdav_user"])
        self.ent_user.grid(row=0, column=3, sticky="w", padx=6)

        lbl = ttk.Label(rowW, text="密码（登录密码）："); self._wrap(lbl, 170)
        lbl.grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.ent_pass = ttk.Entry(rowW, show="*", width=24); self.ent_pass.insert(0, self.cfg["webdav_pass"])
        self.ent_pass.grid(row=1, column=1, sticky="we", padx=6)
        ttk.Button(rowW, text="写入/更新 rclone 配置", command=self.write_rclone_config).grid(row=1, column=3, sticky="w", padx=6)

        # 基础选项（Checkbutton 也支持 wraplength）
        row2 = ttk.Frame(self); row2.pack(fill="x", expand=False, **pad)
        self.var_vfs = tk.BooleanVar(value=self.cfg["vfs_writes"])
        self.var_links = tk.BooleanVar(value=self.cfg["links"])
        self.var_net = tk.BooleanVar(value=self.cfg["network_mode"])

        cb1 = ttk.Checkbutton(row2, text="启用 VFS 缓存（--vfs-cache-mode=…：读写走缓存/提升兼容性）", variable=self.var_vfs)
        cb2 = ttk.Checkbutton(row2, text="--links（保留硬/符号链接元信息）", variable=self.var_links)
        cb3 = ttk.Checkbutton(row2, text="--network-mode（以网络盘方式挂载/改善刷新）", variable=self.var_net)
        for cb in (cb1, cb2, cb3):
            try: cb.configure(wraplength=360, justify="left")
            except tk.TclError: pass
            cb.pack(side="left", padx=(0,12))

        # —— 高级参数（可伸缩网格） —— #
        adv = ttk.LabelFrame(self, text="高级参数"); adv.pack(fill="x", expand=False, **pad)
        for i in range(6):
            adv.columnconfigure(i, weight=1)

        # 第 0 行：vfs-cache-mode | dir-cache-time | poll-interval
        lbl = ttk.Label(adv, text="vfs-cache-mode（VFS 缓存级别）："); self._wrap(lbl, 220)
        lbl.grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.cmb_mode = ttk.Combobox(adv, values=["full","writes","minimal","off"], width=12, state="readonly")
        self.cmb_mode.set(self.cfg.get("vfs_cache_mode","full"))
        self.cmb_mode.grid(row=0, column=1, sticky="w", padx=4)

        lbl = ttk.Label(adv, text="dir-cache-time（目录列表缓存时长）："); self._wrap(lbl, 220)
        lbl.grid(row=0, column=2, sticky="e", padx=6)
        self.ent_dct = ttk.Entry(adv)
        self.ent_dct.insert(0, self.cfg.get("dir_cache_time","30s"))
        self.ent_dct.grid(row=0, column=3, sticky="we", padx=4)

        lbl = ttk.Label(adv, text="poll-interval（轮询变更间隔）："); self._wrap(lbl, 220)
        lbl.grid(row=0, column=4, sticky="e", padx=6)
        self.ent_pit = ttk.Entry(adv)
        self.ent_pit.insert(0, self.cfg.get("poll_interval","15s"))
        self.ent_pit.grid(row=0, column=5, sticky="we", padx=4)

        # 第 1 行：vfs-cache-max-age | attr-timeout
        lbl = ttk.Label(adv, text="vfs-cache-max-age（VFS 文件缓存寿命）："); self._wrap(lbl, 220)
        lbl.grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self.ent_vma = ttk.Entry(adv)
        self.ent_vma.insert(0, self.cfg.get("vfs_cache_max_age","30m"))
        self.ent_vma.grid(row=1, column=1, sticky="we", padx=4)

        lbl = ttk.Label(adv, text="attr-timeout（文件属性缓存时长）："); self._wrap(lbl, 220)
        lbl.grid(row=1, column=2, sticky="e", padx=6)
        self.ent_ato = ttk.Entry(adv)
        self.ent_ato.insert(0, self.cfg.get("attr_timeout","10s"))
        self.ent_ato.grid(row=1, column=3, sticky="we", padx=4)

        # 第 2 行：cache-dir（整行）
        lbl = ttk.Label(adv, text="cache-dir（本地缓存目录）："); self._wrap(lbl, 220)
        lbl.grid(row=2, column=0, sticky="e", padx=6, pady=4)
        self.ent_cdir = ttk.Entry(adv)
        self.ent_cdir.insert(0, self.cfg.get("cache_dir", r"C:\rclone-cache"))
        self.ent_cdir.grid(row=2, column=1, columnspan=4, sticky="we", padx=4)
        ttk.Button(adv, text="选择…", command=self.pick_cache_dir).grid(row=2, column=5, sticky="w", padx=6)

        # 操作按钮
        row3 = ttk.Frame(self); row3.pack(fill="x", expand=False, **pad)
        ttk.Button(row3, text="挂载（后台）", command=self.mount_bg).pack(side="left")
        ttk.Button(row3, text="卸载", command=self.unmount).pack(side="left", padx=(8,0))
        ttk.Button(row3, text="保存配置", command=self.save_config).pack(side="left", padx=(16,0))
        ttk.Button(row3, text="测试 rclone", command=self.test_rclone).pack(side="left", padx=(8,0))
        ttk.Button(row3, text="创建登录自启任务", command=self.create_task).pack(side="left", padx=(16,0))
        ttk.Button(row3, text="删除自启任务", command=self.delete_task).pack(side="left", padx=(8,0))

        # 状态与日志（可随窗口扩展）
        box = ttk.LabelFrame(self, text="状态"); box.pack(fill="both", expand=True, **pad)
        self.lbl = ttk.Label(box, text="当前状态：未挂载")
        self.lbl.pack(anchor="w", padx=8, pady=6)
        self.txt = tk.Text(box)
        self.txt.pack(fill="both", expand=True, padx=8, pady=(0,8))

    # ------- UI helpers -------
    def append_log(self, s):
        self.txt.insert("end", s + "\n")
        self.txt.see("end")

    def pick_rclone(self):
        p = filedialog.askopenfilename(title="选择 rclone.exe",
                                       filetypes=[("rclone", "rclone.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if p:
            self.ent_rclone.delete(0, "end"); self.ent_rclone.insert(0, p)

    def pick_cache_dir(self):
        p = filedialog.askdirectory(title="选择 rclone 缓存目录")
        if p:
            self.ent_cdir.delete(0, "end"); self.ent_cdir.insert(0, p)

    def collect_cfg(self):
        c = {
            "rclone_path": self.ent_rclone.get().strip(),
            "remote": self.ent_remote.get().strip(),
            "drive": self.ent_drive.get().strip().rstrip("\\"),
            "vfs_writes": bool(self.var_vfs.get()),
            "links": bool(self.var_links.get()),
            "network_mode": bool(self.var_net.get()),
            "volname": self.ent_vol.get().strip() or "Rclone",
            "webdav_url": self.ent_url.get().strip(),
            "webdav_user": self.ent_user.get().strip(),
            "webdav_pass": self.ent_pass.get().strip(),
            "vfs_cache_mode": self.cmb_mode.get().strip().lower(),
            "dir_cache_time": self.ent_dct.get().strip(),
            "poll_interval": self.ent_pit.get().strip(),
            "vfs_cache_max_age": self.ent_vma.get().strip(),
            "attr_timeout": self.ent_ato.get().strip(),
            "cache_dir": self.ent_cdir.get().strip(),
        }
        return c

    # ------- 操作 -------
    def save_config(self):
        c = self.collect_cfg()
        save_cfg(c)
        messagebox.showinfo("保存成功", f"配置已保存：\n{cfg_path()}")

    def test_rclone(self):
        c = self.collect_cfg()
        rclone = rclone_guess_from_gui(c)
        if rclone == "rclone" and not c["rclone_path"]:
            messagebox.showwarning("提示", "未选择 rclone.exe，将使用 PATH 上的 rclone。")
        code, out = run_capture([rclone, "version"])
        self.append_log(out.strip())
        messagebox.showinfo("rclone 检测", "OK" if code == 0 else "异常，详见日志")

    def write_rclone_config(self):
        c = self.collect_cfg()
        if not c["webdav_url"]:
            messagebox.showerror("错误", "请填写 WebDAV URL"); return
        if not c["webdav_user"]:
            messagebox.showerror("错误", "请填写用户名"); return
        if not c["webdav_pass"]:
            messagebox.showerror("错误", "请填写密码"); return

        rclone = rclone_guess_from_gui(c)
        try:
            obs = obscure_with_rclone(rclone, c["webdav_pass"])
            conf = rclone_conf_path()
            name = (c["remote"].rstrip(":") or "alist")
            write_remote_to_conf(conf, name, c["webdav_url"], c["webdav_user"], obs)
            save_cfg(c)
            code, out = verify_remote(rclone, name)
            self.append_log(f"[conf] {conf}\n" + (out or ""))
            if code == 0:
                messagebox.showinfo("完成", f"已写入并验证远端：{name}:")
            else:
                messagebox.showwarning("注意", "已写入配置，但验证失败，请检查 URL/证书/防火墙。")
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def mount_bg(self):
        c = self.collect_cfg()
        if not c["remote"].endswith(":"):
            messagebox.showerror("错误", "远端名必须以冒号结尾，例如 alist:")
            return
        rclone_exe = rclone_guess_from_gui(c)
        if rclone_exe == "rclone" and not c["rclone_path"]:
            messagebox.showwarning("提示", "未选择 rclone.exe，将使用 PATH 上的 rclone。")

        save_cfg(c)
        self.append_log(f"[CLEAN] {c['drive']} …")
        clean_old_mounts(c["drive"])

        args = [rclone_exe] + build_mount_args(c)
        self.append_log("[MOUNT] " + " ".join(args))
        try:
            run_hidden(args, cwd=os.path.dirname(c.get("rclone_path") or ""))
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            return

        def wait_ready():
            for _ in range(15):
                if is_drive_ready(c["drive"]):
                    self.append_log(f"[READY] {c['drive']} 就绪")
                    self.lbl.config(text=f"✅ 已挂载到 {c['drive']}（{c['volname']}）")
                    messagebox.showinfo("挂载成功", f"已挂载到 {c['drive']}")
                    return
                time.sleep(1)
            self.append_log("[WARN] 已启动，但盘符未就绪（网络/证书/权限？）")
            self.lbl.config(text="⚠️ 已启动，但盘符未就绪（稍后刷新“此电脑”）")
            messagebox.showwarning("提示", "已启动挂载，但盘符未就绪。")

        threading.Thread(target=wait_ready, daemon=True).start()

    def unmount(self):
        c = self.collect_cfg()
        self.append_log(f"[UNMOUNT] 清理 {c['drive']} …")
        clean_old_mounts(c["drive"])
        self.lbl.config(text="已卸载")
        messagebox.showinfo("完成", "已卸载/清理")

    def create_task(self):
        code, out, name = create_login_task()
        self.append_log(out.strip())
        messagebox.showinfo("计划任务", ("已创建：" + name) if code == 0 else ("创建失败：\n" + out))

    def delete_task(self):
        code, out, name = delete_login_task()
        self.append_log(out.strip())
        messagebox.showinfo("计划任务", ("已删除：" + name) if code == 0 else ("删除失败：\n" + out))

    def _refresh_status_async(self):
        def _t():
            ready = is_drive_ready(self.ent_drive.get().strip())
            self.lbl.config(text=f"当前状态：{'✅ 就绪' if ready else '未挂载'}")
        self.after(1200, self._refresh_status_async)
        self.after(10, _t)

# ----------------- 自启静默模式 -----------------
def auto_mode():
    c = load_cfg()
    rclone = rclone_guess_from_gui(c)
    clean_old_mounts(c["drive"])
    args = [rclone] + build_mount_args(c)
    try:
        run_hidden(args, cwd=os.path.dirname(c.get("rclone_path") or ""))
    except Exception:
        pass

# ----------------- 入口 -----------------
if __name__ == "__main__":
    if "--auto" in sys.argv:
        auto_mode(); sys.exit(0)
    app = App(); app.mainloop()
