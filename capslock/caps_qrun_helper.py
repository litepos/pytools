# -*- coding: utf-8 -*-
"""
Capslock+ QRun Helper — FINAL
--------------------------------
脚本编码：UTF-8
目标配置：按 UTF-16 读取/写入 Capslock+settings.ini

规则：
1) 递归扫描所选根目录下的 .exe / .lnk
2) 写入时路径一律加双引号（Windows 路径更稳）
3) [QRun] 内若已存在同名键：直接覆盖（不再追加重复行）
4) 使用真实 CRLF 换行
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SECTION = "QRun"
CRLF = "\r\n"

def scan_executables(root_dir):
    results = []
    for r, _, files in os.walk(root_dir):
        for n in files:
            ext = os.path.splitext(n)[1].lower()
            if ext in (".exe", ".lnk"):
                key = os.path.splitext(n)[0]
                full = os.path.join(r, n)
                results.append((key, full))
    return results

def read_utf16(path):
    with open(path, "r", encoding="utf-16") as f:
        return f.read()

def write_utf16(path, text):
    with open(path, "w", encoding="utf-16") as f:
        f.write(text)

def get_qrun_bounds(text, section=SECTION):
    lines = text.splitlines(keepends=True)
    head = f"[{section}]"
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == head.lower():
            start = i
            break
    if start is None:
        return lines, None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("[") and "]" in lines[j]:
            end = j
            break
    return lines, start, end

def parse_section_as_dict(section_lines):
    d = {}
    for ln in section_lines:
        s = ln.lstrip()
        if not s or s.startswith(";"):  # 注释/空行
            continue
        if "=" in ln:
            k, v = ln.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def normalize_path(p):
    # 统一使用反斜杠，包裹双引号（无论是否存在空格）
    p = p.replace("/", "\\")
    p = p.strip()
    if not (p.startswith('"') and p.endswith('"')):
        p = f'"{p}"'
    return p

def rebuild_section_text(section_dict, section=SECTION):
    out = [f"[{section}]{CRLF}"]
    for k in sorted(section_dict.keys()):
        v = section_dict[k]
        # 确保每一项独立一行
        out.append(f"{k}={v}{CRLF}")
    return "".join(out)

def upsert_entries(text, items, section=SECTION):
    """
    覆盖更新：将 items 中的 (k, v) 全量写入 [section]，
    - 已存在键：覆盖 value
    - 不存在键：新增
    - 其它段保持不变
    """
    lines, s, e = get_qrun_bounds(text, section)
    # 没有该段，直接新建
    if s is None:
        new_lines = []
        new_lines.append(f"[{section}]{CRLF}")
        # ALWAYS quote paths
        for k, v in items:
            v = normalize_path(v)
            new_lines.append(f"{k}={v}{CRLF}")
        # 末尾拼接
        if lines and not (lines[-1].endswith("\n") or lines[-1].endswith("\r")):
            lines[-1] += CRLF
        return "".join(lines + new_lines)

    # 解析原有字典
    section_lines = lines[s+1:e]
    d = parse_section_as_dict(section_lines)

    # 覆盖/新增
    for k, v in items:
        d[k] = normalize_path(v)

    # 重建该段文本
    new_section_text = rebuild_section_text(d, section)

    # 拼回整体
    return "".join(lines[:s] + [new_section_text] + lines[e:])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Capslock+ QRun Helper (Final, UTF-8 script / UTF-16 INI)")
        self.geometry("820x520")

        self.var_dir = tk.StringVar()
        self.var_ini = tk.StringVar()

        self._build_ui()

        self.candidates = []  # [(key, path)]
        self.items_for_write = []  # [(key, path)]
        self.existing_map = {}

    def _build_ui(self):
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        ttk.Label(top, text="扫描根目录：").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.var_dir, width=70).grid(row=0, column=1, padx=5, sticky="we")
        ttk.Button(top, text="选择…", command=self.pick_dir).grid(row=0, column=2)

        ttk.Label(top, text="settings.ini（UTF-16）：").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(top, textvariable=self.var_ini, width=70).grid(row=1, column=1, padx=5, sticky="we", pady=(6,0))
        ttk.Button(top, text="选择…", command=self.pick_ini).grid(row=1, column=2, pady=(6,0))

        btns = ttk.Frame(self, padding=(10,0)); btns.pack(fill="x")
        ttk.Button(btns, text="扫描（递归）", command=self.on_scan).pack(side="left")
        ttk.Button(btns, text="写入（覆盖/新增）", command=self.on_write).pack(side="left", padx=8)

        mid = ttk.Frame(self, padding=10); mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("k","p","s"), show="headings", height=14)
        self.tree.heading("k", text="键名")
        self.tree.heading("p", text="路径（写入时自动加双引号）")
        self.tree.heading("s", text="状态")
        self.tree.column("k", width=180, anchor="w")
        self.tree.column("p", width=560, anchor="w")
        self.tree.column("s", width=70, anchor="center")
        self.tree.pack(fill="both", expand=True)

        self.log = tk.Text(self, height=6); self.log.pack(fill="both", padx=10, pady=(0,10))

    def log_append(self, s):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def pick_dir(self):
        d = filedialog.askdirectory(title="选择根目录（将递归子目录）")
        if d: self.var_dir.set(d)

    def pick_ini(self):
        f = filedialog.askopenfilename(title="选择 Capslock+settings.ini（UTF-16）",
                                       filetypes=[("INI","*.ini"), ("All files","*.*")])
        if f: self.var_ini.set(f)

    def on_scan(self):
        root = self.var_dir.get().strip()
        ini = self.var_ini.get().strip()
        if not os.path.isdir(root):
            messagebox.showerror("错误", "请选择有效的根目录"); return
        if not os.path.isfile(ini):
            messagebox.showerror("错误", "请选择有效的 settings.ini"); return

        # 清空表格
        for i in self.tree.get_children():
            self.tree.delete(i)

        self.candidates = scan_executables(root)

        # 读取现有 [QRun] 键集
        try:
            text = read_utf16(ini)
        except UnicodeError:
            messagebox.showerror("编码错误", "settings.ini 不是 UTF-16 或已损坏。"); return

        # 建立已有键 => 值 映射
        lines, s, e = get_qrun_bounds(text, SECTION)
        self.existing_map = {}
        if s is not None:
            self.existing_map = parse_section_as_dict(lines[s+1:e])

        # 本次写入集合（去重，以最后一次出现为准）
        latest = {}
        for k, p in self.candidates:
            latest[k] = p  # 同名键以最后一个为准

        self.items_for_write = []
        for k, p in latest.items():
            # 状态：已有且相同 -> 已有(同值)；已有但不同 -> 覆盖；不存在 -> 新增
            new_v = normalize_path(p)
            old_v = self.existing_map.get(k)
            status = "新增"
            if old_v is not None:
                # old_v 可能未带引号/斜杠方向不同，这里只做字符串比较；实际写入会规范化
                status = "已有(同值)" if old_v == new_v else "覆盖"
            self.items_for_write.append((k, p))
            self.tree.insert("", "end", values=(k, p, status))

        self.log_append(f"扫描完成：候选 {len(self.candidates)}，实际写入项 {len(self.items_for_write)}（同名自动后者覆盖）。")

    def on_write(self):
        ini = self.var_ini.get().strip()
        if not os.path.isfile(ini):
            messagebox.showerror("错误", "settings.ini 无效。"); return
        if not self.items_for_write:
            messagebox.showinfo("提示", "没有可写入的条目，请先扫描。"); return

        try:
            text = read_utf16(ini)
            # 备份
            import shutil, datetime
            bak = ini + ".bak_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copyfile(ini, bak)

            # 覆盖/新增写入
            new_text = upsert_entries(text, self.items_for_write, SECTION)
            write_utf16(ini, new_text)
        except Exception as e:
            messagebox.showerror("失败", str(e)); return

        self.log_append(f"写入完成：处理 {len(self.items_for_write)} 项（已创建备份：{os.path.basename(bak)}）。")
        messagebox.showinfo("完成", "写入成功。\n提示：重启 Capslock+ 或在程序内重载配置以生效。")

if __name__ == "__main__":
    app = App()
    app.mainloop()
