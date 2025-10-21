# -*- coding: utf-8 -*-
"""
Capslock+ QRun Helper — FINAL
(INI-Key Safe + Group Dedup + Prefer x64 + Always Replace Existing)
-------------------------------------------------------------------
策略：
1) 递归扫描 .exe / .lnk
2) 键名(=左)仅允许 A-Z/a-z/0-9/_，且不以数字开头（自动规范化）
3) 同名分组：Everything、Everything_2、Everything_x64、Everything32 等归为一组
4) 分组内“优先使用 x64”（文件名/键名中包含 x64 即视为 x64），其次取首个
5) 若 INI 中该组已存在：直接用“现有主键名”进行替换（覆盖/同值判断），并清理同组冗余键
6) 写入路径统一加双引号；UTF-16；CRLF
"""
import os
import re
import unicodedata
import re
import unicodedata
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SECTION = "QRun"
CRLF = "\r\n"

# ---------------- INI 键名规范化 & 分组 ----------------
def sanitize_key(raw_name: str) -> str:
    if raw_name is None:
        raw_name = ""
    norm = unicodedata.normalize("NFKD", raw_name)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9_]", "_", ascii_only)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe or not re.match(r"[A-Za-z_]", safe[0]):
        safe = ("APP_" + safe) if safe else "APP"
    return safe

# 合并 _2/_3、x64/x86/64/32 等后缀到同一“组”
_group_suffix_re = re.compile(r"(?:_\d+|(?:_?x64|_?x86|64|32))$", re.IGNORECASE)

def key_group(name: str) -> str:
    if not name:
        return ""
    base = _group_suffix_re.sub("", name)
    return base.lower()

def is_x64_key_or_path(key: str, path: str) -> bool:
    key_l = (key or "").lower()
    p_l = os.path.basename(path or "").lower()
    return ("x64" in key_l) or ("x64" in p_l)

# ---------------- I/O ----------------
def read_utf16(path):
    with open(path, "r", encoding="utf-16") as f:
        return f.read()

def write_utf16(path, text):
    with open(path, "w", encoding="utf-16") as f:
        f.write(text)

# ---------------- INI 结构解析 ----------------
def _strip_bom(s: str) -> str:
    return s.lstrip("\ufeff").lstrip("\ufffe").lstrip("\ufeff")

def get_qrun_bounds(text, section=SECTION):
    lines = text.splitlines(keepends=True)
    head = f"[{section}]"
    start = None
    for i, ln in enumerate(lines):
        cmp = _strip_bom(ln).strip().lower()
        if cmp == head.lower():
            start = i
            break
    if start is None:
        return lines, None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        token = lines[j].lstrip()
        if token.startswith("[") and "]" in token:
            end = j
            break
    return lines, start, end

def parse_section_as_dict(section_lines):
    d = {}
    for ln in section_lines:
        raw = _strip_bom(ln)
        s = raw.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        if "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        d[k] = v
    return d

def normalize_path(p):
    p = p.replace("/", "\\").strip()
    if not (p.startswith('"') and p.endswith('"')):
        p = f'"{p}"'
    return p

def rebuild_section_text(section_dict, section=SECTION):
    out = [f"[{section}]{CRLF}"]
    for k in sorted(section_dict.keys()):
        v = section_dict[k]
        out.append(f"{k}={v}{CRLF}")
    return "".join(out)

# ---------------- 扫描 ----------------
def scan_executables(root_dir):
    """
    返回 [(safe_key, full_path, raw_key)]
    键名规范化 + 同名避免（_2, _3…）
    """
    results = []
    used = set()
    for r, _, files in os.walk(root_dir):
        for n in files:
            ext = os.path.splitext(n)[1].lower()
            if ext in (".exe", ".lnk"):
                raw_key = os.path.splitext(n)[0]
                base = sanitize_key(raw_key)
                key = base
                idx = 2
                while key in used:
                    key = f"{base}_{idx}"
                    idx += 1
                used.add(key)
                full = os.path.join(r, n)
                results.append((key, full, raw_key))
    return results

# ---------------- 写入（含清理重复组）----------------
def upsert_entries_and_clean(text, items, section=SECTION):
    """
    - items: [(key_to_write, path)]
    - 将 items 写入后，清理与每个主键同组的其它键（如 *_2、*_3、*_x64 等），仅保留主键
    """
    lines, s, e = get_qrun_bounds(text, section)

    if s is None:
        pre = lines
        section_lines = []
        post = []
        s = len(lines)
        e = s
    else:
        pre = lines[:s]
        section_lines = lines[s+1:e]
        post = lines[e:]

    d = parse_section_as_dict(section_lines)

    # 写入/覆盖
    for k, v in items:
        d[k] = normalize_path(v)

    # 清理：仅保留本次 items 中的主键
    keep_keys = set(k for k, _ in items)
    keep_groups = {key_group(k): k for k in keep_keys}

    for k in list(d.keys()):
        g = key_group(k)
        if g in keep_groups and k != keep_groups[g]:
            del d[k]

    new_section_text = rebuild_section_text(d, section)
    return "".join(pre + [new_section_text] + post)

# ---------------- GUI ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Capslock+ QRun Helper (Prefer x64 + Always Replace)")
        self.geometry("1000x620")

        # 默认路径
        self.var_dir = tk.StringVar(value=r"D:/Software/Software Green")
        self.var_ini = tk.StringVar(value=r"D:/Software/Software Green/Capslock+_v3.3.0/CapsLock+settings.ini")

        self._build_ui()

        self.candidates = []       # [(safe_key, path, raw_key)]
        self.items_for_write = []  # [(final_key, path)]
        self.existing_map = {}

    def _build_ui(self):
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        ttk.Label(top, text="扫描根目录：").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.var_dir, width=92).grid(row=0, column=1, padx=5, sticky="we")
        ttk.Button(top, text="选择…", command=self.pick_dir).grid(row=0, column=2)

        ttk.Label(top, text="settings.ini（UTF-16）：").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(top, textvariable=self.var_ini, width=92).grid(row=1, column=1, padx=5, sticky="we", pady=(6,0))
        ttk.Button(top, text="选择…", command=self.pick_ini).grid(row=1, column=2, pady=(6,0))

        btns = ttk.Frame(self, padding=(10,6)); btns.pack(fill="x")
        ttk.Button(btns, text="扫描（递归）", command=self.on_scan).pack(side="left")
        ttk.Button(btns, text="写入（覆盖/清理重复）", command=self.on_write).pack(side="left", padx=8)

        mid = ttk.Frame(self, padding=10); mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("k","p","s"), show="headings", height=16)
        self.tree.heading("k", text="键名（最终写入主键）")
        self.tree.heading("p", text="路径（写入时自动加双引号）")
        self.tree.heading("s", text="状态")
        self.tree.column("k", width=320, anchor="w")
        self.tree.column("p", width=600, anchor="w")
        self.tree.column("s", width=120, anchor="center")
        self.tree.pack(fill="both", expand=True)

        self.log = tk.Text(self, height=8); self.log.pack(fill="both", padx=10, pady=(0,10))

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

        for i in self.tree.get_children():
            self.tree.delete(i)

        # 扫描候选
        self.candidates = scan_executables(root)

        # 读取现有 [QRun]
        try:
            text = read_utf16(ini)
        except UnicodeError:
            messagebox.showerror("编码错误", "settings.ini 不是 UTF-16 或已损坏。"); return

        lines, s, e = get_qrun_bounds(text, SECTION)
        self.existing_map = {}
        if s is not None:
            self.existing_map = parse_section_as_dict(lines[s+1:e])

        # 既有组（来自 INI）：group -> existing_key（用于“直接替换”）
        existing_groups = {key_group(k): k for k in self.existing_map.keys()}

        # 将扫描结果按组聚合，并在每组内“优先 x64”
        grouped = {}   # g -> [(safe_key, path, raw_key, is_x64)]
        for safe_key, p, raw_key in self.candidates:
            g = key_group(safe_key)
            grouped.setdefault(g, []).append((safe_key, p, raw_key, is_x64_key_or_path(safe_key, p)))

        # 选择每组的主候选（x64 优先）
        chosen = {}    # g -> (chosen_key, chosen_path)
        extras = []    # 其他被淘汰项用于 UI 展示
        for g, items in grouped.items():
            # 先找 x64
            x64_items = [it for it in items if it[3]]
            if x64_items:
                c = x64_items[0]
            else:
                c = items[0]
            chosen[g] = (c[0], c[1])  # (key, path)
            # 其余入 extras
            for it in items:
                if it[0] != c[0] or it[1] != c[1]:
                    extras.append((g, it[0], it[1]))

        # 生成写入计划（始终：若 INI 已有该组 -> 直接替换用“已有主键名”；否则用本次选择的键名）
        self.items_for_write = []
        kept, skipped = 0, 0
        cnt_new, cnt_cover, cnt_same = 0, 0, 0

        for g, (c_key, c_path) in chosen.items():
            target_key = existing_groups.get(g, c_key)  # 有则用已有主键名，无则用选中键名
            new_v = normalize_path(c_path)
            old_v = self.existing_map.get(target_key)
            if old_v is None:
                status = "新增"
                cnt_new += 1
            else:
                status = "已有(同值)" if old_v == new_v else "替换(覆盖)"
                if status == "已有(同值)": cnt_same += 1
                else: cnt_cover += 1

            self.items_for_write.append((target_key, c_path))
            self.tree.insert("", "end", values=(target_key, c_path, status))
            kept += 1

        # 展示被淘汰项（仅 UI，不写入）
        for g, k, p in extras:
            self.tree.insert("", "end", values=(k, p, "跳过(同组劣选)"))
            skipped += 1

        self.log_append(
            f"扫描完成：分组 {len(chosen)}，保留主候选 {kept}（x64 优先），跳过同组劣选 {skipped}。"
        )
        self.log_append(f"统计：新增 {cnt_new}，替换(覆盖) {cnt_cover}，已有(同值) {cnt_same}。")
        self.log_append("提示：写入阶段将清理同组冗余键（如 *_2、*_3、*_x64 等），仅保留主键。")

    def on_write(self):
        ini = self.var_ini.get().strip()
        if not os.path.isfile(ini):
            messagebox.showerror("错误", "settings.ini 无效。"); return
        if not self.items_for_write:
            messagebox.showinfo("提示", "没有可写入的条目，请先扫描。"); return

        try:
            text = read_utf16(ini)
            import shutil, datetime
            bak = ini + ".bak_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copyfile(ini, bak)

            # 覆盖/新增 + 清理重复组
            new_text = upsert_entries_and_clean(text, self.items_for_write, SECTION)
            write_utf16(ini, new_text)
        except Exception as e:
            messagebox.showerror("失败", str(e)); return

        self.log_append(f"写入完成：处理 {len(self.items_for_write)} 项（已创建备份：{os.path.basename(bak)}）。")
        self.log_append("已清理与主键同组的冗余键（如 *_2、*_3、*_x64 等）。")
        messagebox.showinfo("完成", "写入成功。\n提示：重启 Capslock+ 或在程序内重载配置以生效。")

if __name__ == "__main__":
    app = App()
    app.mainloop()
