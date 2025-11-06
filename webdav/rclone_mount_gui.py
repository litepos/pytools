import os
import sys
import json
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "RcloneMountGUI"
DEFAULTS = {
    "rclone_path": "",
    "remote": "alist:",
    "drive": "Z:",
    "vfs_writes": True,
    "links": True,
    "network_mode": True,
    "volname": "AList WebDAV"
}

def appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d

def cfg_path():
    return os.path.join(appdata_dir(), "config.json")

def load_cfg():
    p = cfg_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
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
    # letter like 'Z:' or 'Z:\\'
    if not letter:
        return False
    drv = letter
    if not drv.endswith("\\"):
        drv += "\\"
    return os.path.exists(os.path.join(drv, "NUL"))

def run_hidden(cmd, cwd=None):
    """Run a process hidden (no new console window)."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(cmd, cwd=cwd, startupinfo=si,
                            creationflags=creationflags,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)

def run_capture(cmd, cwd=None, timeout=15):
    """Run and capture output (for quick checks)."""
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        p.kill()
        return -1, "Timeout"

def clean_old_mounts(drive):
    # safe to repeat
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

def build_mount_args(cfg):
    args = ["mount", cfg["remote"], cfg["drive"]]
    if cfg.get("vfs_writes", True):
        args += ["--vfs-cache-mode=writes"]
    if cfg.get("links", True):
        args += ["--links"]
    if cfg.get("network_mode", True):
        args += ["--network-mode"]
    vol = cfg.get("volname") or "Rclone"
    args += ["--volname", vol]
    return args

def create_login_task(cfg):
    # Create a login task that runs this script with --auto
    # Use cmd /c cd /d "<workdir>" && python rclone_mount_gui.py --auto
    workdir = os.path.dirname(os.path.abspath(sys.argv[0]))
    script = os.path.abspath(sys.argv[0])
    # Prefer pythonw.exe for no console if available
    py = sys.executable or "python"
    # Wrap with cmd to set working directory
    action = f'/c cd /d "{workdir}" && "{py}" "{script}" --auto'
    task_name = f"{APP_NAME}-Mount"
    cmd = [
        "schtasks", "/Create", "/TN", task_name,
        "/TR", f'cmd {action}',
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/F"
    ]
    code, out = run_capture(cmd, timeout=10)
    return code, out, task_name

def delete_login_task():
    task_name = f"{APP_NAME}-Mount"
    cmd = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    code, out = run_capture(cmd, timeout=10)
    return code, out, task_name

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rclone 挂载助手")
        self.geometry("640x420")
        self.resizable(False, False)
        self.cfg = load_cfg()
        self._build_ui()
        self._refresh_status_async()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # row 0: rclone.exe path
        frm0 = ttk.Frame(self)
        frm0.pack(fill="x", **pad)
        ttk.Label(frm0, text="rclone.exe 路径：").pack(side="left")
        self.ent_path = ttk.Entry(frm0)
        self.ent_path.insert(0, self.cfg["rclone_path"])
        self.ent_path.pack(side="left", fill="x", expand=True, padx=(6,6))
        ttk.Button(frm0, text="浏览…", command=self.pick_rclone).pack(side="left")

        # row 1: remote & drive
        frm1 = ttk.Frame(self)
        frm1.pack(fill="x", **pad)
        ttk.Label(frm1, text="远端名（remote）：").pack(side="left")
        self.ent_remote = ttk.Entry(frm1, width=16)
        self.ent_remote.insert(0, self.cfg["remote"])
        self.ent_remote.pack(side="left", padx=(6,18))
        ttk.Label(frm1, text="盘符：").pack(side="left")
        self.ent_drive = ttk.Entry(frm1, width=6)
        self.ent_drive.insert(0, self.cfg["drive"])
        self.ent_drive.pack(side="left", padx=(6,18))
        ttk.Label(frm1, text="卷名：").pack(side="left")
        self.ent_vol = ttk.Entry(frm1, width=20)
        self.ent_vol.insert(0, self.cfg["volname"])
        self.ent_vol.pack(side="left", padx=(6,0))

        # row 2: options
        frm2 = ttk.Frame(self)
        frm2.pack(fill="x", **pad)
        self.var_vfs = tk.BooleanVar(value=self.cfg["vfs_writes"])
        self.var_links = tk.BooleanVar(value=self.cfg["links"])
        self.var_net = tk.BooleanVar(value=self.cfg["network_mode"])
        ttk.Checkbutton(frm2, text="--vfs-cache-mode=writes", variable=self.var_vfs).pack(side="left")
        ttk.Checkbutton(frm2, text="--links", variable=self.var_links).pack(side="left", padx=(12,0))
        ttk.Checkbutton(frm2, text="--network-mode", variable=self.var_net).pack(side="left", padx=(12,0))

        # row 3: buttons
        frm3 = ttk.Frame(self)
        frm3.pack(fill="x", **pad)
        ttk.Button(frm3, text="挂载（后台）", command=self.mount_bg).pack(side="left")
        ttk.Button(frm3, text="卸载", command=self.unmount).pack(side="left", padx=(8,0))
        ttk.Button(frm3, text="保存配置", command=self.save_config).pack(side="left", padx=(16,0))
        ttk.Button(frm3, text="测试 rclone", command=self.test_rclone).pack(side="left", padx=(8,0))
        ttk.Button(frm3, text="创建登录自启任务", command=self.create_task).pack(side="left", padx=(16,0))
        ttk.Button(frm3, text="删除自启任务", command=self.delete_task).pack(side="left", padx=(8,0))

        # row 4: status + log
        frm4 = ttk.LabelFrame(self, text="状态")
        frm4.pack(fill="both", expand=True, **pad)
        self.lbl_status = ttk.Label(frm4, text="初始化…")
        self.lbl_status.pack(anchor="w", padx=8, pady=6)
        self.txt = tk.Text(frm4, height=10)
        self.txt.pack(fill="both", expand=True, padx=8, pady=(0,8))

    def append_log(self, s):
        self.txt.insert("end", s + "\n")
        self.txt.see("end")

    def pick_rclone(self):
        p = filedialog.askopenfilename(title="选择 rclone.exe", filetypes=[("rclone", "rclone.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if p:
            self.ent_path.delete(0, "end")
            self.ent_path.insert(0, p)

    def collect_cfg(self):
        c = {
            "rclone_path": self.ent_path.get().strip(),
            "remote": self.ent_remote.get().strip(),
            "drive": self.ent_drive.get().strip().rstrip("\\"),
            "vfs_writes": bool(self.var_vfs.get()),
            "links": bool(self.var_links.get()),
            "network_mode": bool(self.var_net.get()),
            "volname": self.ent_vol.get().strip() or "Rclone"
        }
        return c

    def save_config(self):
        c = self.collect_cfg()
        save_cfg(c)
        messagebox.showinfo("保存成功", f"配置已保存到：\n{cfg_path()}")

    def test_rclone(self):
        c = self.collect_cfg()
        if not os.path.isfile(c["rclone_path"]):
            messagebox.showerror("错误", "请先选择 rclone.exe")
            return
        code, out = run_capture([c["rclone_path"], "version"], cwd=os.path.dirname(c["rclone_path"]))
        self.append_log(out.strip())
        if code == 0:
            messagebox.showinfo("OK", "rclone 可用")
        else:
            messagebox.showwarning("注意", "rclone 检测异常，详见日志")

    def mount_bg(self):
        c = self.collect_cfg()
        if not os.path.isfile(c["rclone_path"]):
            messagebox.showerror("错误", "请先选择 rclone.exe")
            return
        if not c["remote"].endswith(":"):
            messagebox.showerror("错误", "远端名必须以冒号结尾，例如 alist:")
            return

        # 保存配置
        save_cfg(c)

        # 清理旧挂载
        self.append_log(f"[CLEAN] {c['drive']} …")
        clean_old_mounts(c["drive"])

        # 组装参数并后台隐藏启动
        args = [c["rclone_path"]] + build_mount_args(c)
        self.append_log("[MOUNT] " + " ".join(args))
        try:
            run_hidden(args, cwd=os.path.dirname(c["rclone_path"]))
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            return

        # 异步轮询就绪
        def wait_ready():
            for _ in range(15):
                if is_drive_ready(c["drive"]):
                    self.append_log(f"[READY] {c['drive']} 已就绪")
                    self.lbl_status.config(text=f"✅ 已挂载到 {c['drive']}（{c['volname']}）")
                    messagebox.showinfo("挂载成功", f"已挂载到 {c['drive']}")
                    return
                time.sleep(1)
            self.append_log("[WARN] 已启动，但盘符未就绪（网络/证书/权限？）")
            self.lbl_status.config(text="⚠️ 已启动，但盘符未就绪（稍后刷新“此电脑”）")
            messagebox.showwarning("提示", "已启动挂载，但盘符未就绪。稍后再试或检查日志。")

        threading.Thread(target=wait_ready, daemon=True).start()

    def unmount(self):
        c = self.collect_cfg()
        self.append_log(f"[UNMOUNT] 清理 {c['drive']} …")
        clean_old_mounts(c["drive"])
        if not is_drive_ready(c["drive"]):
            self.lbl_status.config(text="已卸载")
            messagebox.showinfo("完成", "已卸载/清理")
        else:
            messagebox.showwarning("注意", "尝试卸载后盘符仍存在，请稍后再试。")

    def create_task(self):
        # 计划任务：登录时，后台运行本程序 --auto
        code, out, name = create_login_task(self.collect_cfg())
        self.append_log(out.strip())
        if code == 0:
            messagebox.showinfo("完成", f"已创建计划任务：{name}\n（登录后自动后台挂载）")
        else:
            messagebox.showwarning("注意", f"创建失败：\n{out}")

    def delete_task(self):
        code, out, name = delete_login_task()
        self.append_log(out.strip())
        if code == 0:
            messagebox.showinfo("完成", f"已删除计划任务：{name}")
        else:
            messagebox.showwarning("注意", f"删除失败：\n{out}")

    def _refresh_status_async(self):
        def _t():
            c = self.collect_cfg()
            ready = is_drive_ready(c["drive"])
            s = f"当前状态：{'✅ 就绪' if ready else '未挂载'}"
            self.lbl_status.config(text=s)
        self.after(1200, self._refresh_status_async)
        self.after(10, _t)

def auto_mode():
    """--auto：给计划任务用，静默后台挂载，不弹框。"""
    cfg = load_cfg()
    if not os.path.isfile(cfg["rclone_path"]):
        return
    clean_old_mounts(cfg["drive"])
    args = [cfg["rclone_path"]] + build_mount_args(cfg)
    try:
        run_hidden(args, cwd=os.path.dirname(cfg["rclone_path"]))
    except Exception:
        pass
    # 无交互环境不弹窗；直接退出

if __name__ == "__main__":
    if "--auto" in sys.argv:
        auto_mode()
        sys.exit(0)
    app = App()
    app.mainloop()
