# -*- coding: utf-8 -*-
r"""
Auto Sort Softwares - GUI Version (No Rename)
- Choose root directory via GUI
- Load external regex rules from category_rules.txt (same folder as this script)
- Top-level scan (non-recursive), preview in table
- "预览汇总" dialog (counts by category; double-click to highlight rows in main table)
- "仅移动选中项" option
- Progress bar + real-time log
- Optional: remove empty top-level folders after move
- Skip if destination already has same-name entry
- Window is resizable (responsive)

Python 3.8+ / Windows (stdlib only)
"""

import re
import sys
import time
import queue
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Iterable

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------------ Rules ------------------

@dataclass
class RuleBlock:
    target_dir: str
    patterns: List[re.Pattern]

# 规则文件：与脚本同目录
RULE_FILE = Path(__file__).with_name("category_rules.txt")

# 顶层分类目录（与 category_rules.txt 的 # target_dir 保持一致）
DEFAULT_TARGET_DIRS = [
    "01_office","02_dev","03_database","04_network","05_system",
    "06_drivers","07_media","08_communication","09_os",
    "10_input","11_maps","12_enterprise","99_misc",
]

# Portable 索引目录（仅放 .url 与清单）
PORTABLE_INDEX_DIR = "90_portable"

# 兜底识别为“安装包/压缩包”的扩展名
INSTALL_EXT = {".exe", ".msi"}
ARCHIVE_EXT = {".zip", ".7z", ".rar"}

# --------- rules loader ---------
def load_rules(rule_file: Path) -> List[RuleBlock]:
    """从 category_rules.txt 读取规则块，按出现顺序作为优先级；每个块以 '# target_dir: <name>' 开头。"""
    if not rule_file.exists():
        raise FileNotFoundError(f"Rule file not found: {rule_file}")
    blocks: List[RuleBlock] = []
    current_target = None
    current_patterns: List[re.Pattern] = []
    with rule_file.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or (line.startswith("#") and not line.lower().startswith("# target_dir:")):
                continue
            if line.lower().startswith("# target_dir:"):
                if current_target is not None:
                    blocks.append(RuleBlock(current_target, current_patterns))
                current_target = line.split(":", 1)[1].strip()
                current_patterns = []
                continue
            try:
                current_patterns.append(re.compile(line, re.I))
            except re.error as e:
                raise ValueError(f"Invalid regex: {line} -> {e}")
    if current_target is not None:
        blocks.append(RuleBlock(current_target, current_patterns))
    return blocks

def load_portable_patterns(rule_file: Path) -> List[re.Pattern]:
    """
    从 category_rules.txt 读取 '# portable_mark' 段，作为便携识别用正则（不影响分类）。
    语法：
      # portable_mark
      <regex1>
      <regex2>
      ...
      # target_dir: 01_office   ← 碰到新块或文件结束即停止 portable 段
    """
    if not rule_file.exists():
        return []
    pats: List[re.Pattern] = []
    in_block = False
    with rule_file.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("# target_dir:"):
                if in_block:  # portable 段结束
                    break
                else:
                    continue
            if low.startswith("# portable_mark"):
                in_block = True
                continue
            if in_block:
                try:
                    pats.append(re.compile(line, re.I))
                except re.error as e:
                    raise ValueError(f"Invalid portable regex: {line} -> {e}")
    return pats

def is_portable(name: str, portable_patterns: Iterable[re.Pattern]) -> bool:
    nm = name.lower()
    for p in portable_patterns:
        if p.search(nm):
            return True
    return False

def choose_target(item: Path, blocks: List[RuleBlock]) -> Tuple[str, str]:
    """返回 (target_dir, reason)。按规则块先后匹配；无命中则兜底到 99_misc。"""
    name = item.name.lower()
    for blk in blocks:
        for pat in blk.patterns:
            if pat.search(name):
                return blk.target_dir, f"match:{blk.target_dir}:{pat.pattern}"
    suffix = item.suffix.lower()
    if suffix in INSTALL_EXT or suffix in ARCHIVE_EXT:
        return "99_misc", f"fallback:{suffix or 'archive'}"
    if item.is_dir():
        return "99_misc", "fallback:dir"
    return "99_misc", "fallback:other"


# ------------------ GUI ------------------

class AutoSortApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto Sort Softwares (GUI)")
        self.minsize(1000, 620)
        self.geometry("1200x720")
        self.configure(padx=8, pady=8)
        self._make_style()

        self.rule_blocks: List[RuleBlock] = []
        self.portable_patterns: List[re.Pattern] = []
        self.root_dir: Path = None
        self.plan: List[Dict] = []  # [{"path": Path, "target": str, "reason": str, "iid": str}]
        self.msg_queue = queue.Queue()

        # 顶部按钮区
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.columnconfigure(1, weight=1)  # 目录输入框伸缩

        self.btn_choose = ttk.Button(top, text="选择目录", command=self.choose_dir)
        self.btn_choose.grid(row=0, column=0, padx=(0, 6))

        self.entry_dir = ttk.Entry(top)
        self.entry_dir.grid(row=0, column=1, sticky="ew")

        self.btn_scan = ttk.Button(top, text="扫描分类", command=self.scan_dir)
        self.btn_scan.grid(row=0, column=2, padx=6)

        self.btn_summary = ttk.Button(top, text="预览汇总", command=self.show_summary)
        self.btn_summary.grid(row=0, column=3, padx=6)

        self.btn_move = ttk.Button(top, text="执行移动", command=self.exec_move)
        self.btn_move.grid(row=0, column=4, padx=6)

        self.btn_portable = ttk.Button(top, text="生成Portable索引", command=self.build_portable_index)
        self.btn_portable.grid(row=0, column=5, padx=6)

        self.btn_clear = ttk.Button(top, text="清空结果", command=self.clear_all)
        self.btn_clear.grid(row=0, column=6, padx=(6, 0))

        # 选项
        opt = ttk.Frame(self)
        opt.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.var_delete_empty = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="执行后删除空目录（仅根目录一层）", variable=self.var_delete_empty).pack(side="left")
        self.var_move_selected = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="仅移动选中项", variable=self.var_move_selected).pack(side="left", padx=(12, 0))

        # 主表（预览）
        mid = ttk.Frame(self)
        mid.grid(row=2, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        columns = ("name", "target", "reason", "status")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name", text="名称")
        self.tree.heading("target", text="分类")
        self.tree.heading("reason", text="命中规则")
        self.tree.heading("status", text="状态")
        self.tree.column("name", width=460, anchor="w")
        self.tree.column("target", width=200, anchor="w")
        self.tree.column("reason", width=460, anchor="w")
        self.tree.column("status", width=110, anchor="center")

        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        # 进度 + 日志
        bottom = ttk.Frame(self)
        bottom.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.pb = ttk.Progressbar(bottom, orient="horizontal", mode="determinate")
        self.pb.grid(row=0, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        logf = ttk.LabelFrame(self, text="日志输出")
        logf.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        self.rowconfigure(4, weight=1)

        self.txt_log = tk.Text(logf, height=8, wrap="none")
        log_v = ttk.Scrollbar(logf, orient="vertical", command=self.txt_log.yview)
        log_h = ttk.Scrollbar(logf, orient="horizontal", command=self.txt_log.xview)
        self.txt_log.configure(yscrollcommand=log_v.set, xscrollcommand=log_h.set)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        log_v.grid(row=0, column=1, sticky="ns")
        log_h.grid(row=1, column=0, sticky="ew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)

        # 菜单
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="退出", command=self.destroy)
        menubar.add_cascade(label="文件", menu=filemenu)
        self.config(menu=menubar)

        # 定时处理日志/状态队列
        self.after(100, self._process_queue)

        # 加载规则
        try:
            self.rule_blocks = load_rules(RULE_FILE)
            self.portable_patterns = load_portable_patterns(RULE_FILE)
        except FileNotFoundError:
            messagebox.showerror("规则文件缺失", f"未找到规则文件：{RULE_FILE.name}\n请将该文件放到脚本同目录。")
        except Exception as e:
            messagebox.showerror("规则解析错误", str(e))

    # -------- util --------
    def _make_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            pass

    def log(self, text: str):
        self.msg_queue.put(("log", text))

    def set_status(self, iid, text: str):
        self.msg_queue.put(("status", iid, text))

    def set_progress(self, value: int, total: int):
        self.msg_queue.put(("progress", value, total))

    def _process_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                t = item[0]
                if t == "log":
                    self.txt_log.insert("end", time.strftime("[%H:%M:%S] ") + item[1] + "\n")
                    self.txt_log.see("end")
                elif t == "status":
                    _, iid, text = item
                    self.tree.set(iid, "status", text)
                elif t == "progress":
                    _, value, total = item
                    self.pb["maximum"] = max(1, total)
                    self.pb["value"] = value
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    # -------- actions --------
    def choose_dir(self):
        path = filedialog.askdirectory(title="选择软件根目录（仅扫描一层）")
        if path:
            self.root_dir = Path(path)
            self.entry_dir.delete(0, "end")
            self.entry_dir.insert(0, str(self.root_dir))

    def scan_dir(self):
        if not self.root_dir or not self.root_dir.exists():
            messagebox.showwarning("未选择目录", "请先选择有效目录。")
            return
        if not self.rule_blocks:
            messagebox.showwarning("规则未加载", f"未加载规则，请将 {RULE_FILE.name} 放在脚本同目录。")
            return

        self.tree.delete(*self.tree.get_children())
        self.plan.clear()

        count = 0
        for child in self.root_dir.iterdir():
            # 忽略系统/临时目录与 portable 索引目录
            if child.name.startswith(("~$", ".")) or child.name == PORTABLE_INDEX_DIR:
                continue
            if child.name in {"System Volume Information", "$RECYCLE.BIN"}:
                continue

            target, reason = choose_target(child, self.rule_blocks)
            iid = self.tree.insert("", "end", values=(child.name, target, reason, "等待"))
            self.plan.append({"path": child, "target": target, "reason": reason, "iid": iid})
            count += 1

        self.log(f"扫描完成，共 {count} 项。")

    def show_summary(self):
        if not self.plan:
            messagebox.showinfo("无数据", "请先扫描分类。")
            return

        stats: Dict[str, int] = {}
        for it in self.plan:
            stats[it["target"]] = stats.get(it["target"], 0) + 1

        win = tk.Toplevel(self)
        win.title("预览汇总")
        win.geometry("560x460")
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="按分类统计（双击分类高亮主表对应条目）：").pack(anchor="w")

        columns = ("category", "count")
        tv = ttk.Treeview(frm, columns=columns, show="headings", height=10)
        tv.heading("category", text="分类")
        tv.heading("count", text="数量")
        tv.column("category", width=320, anchor="w")
        tv.column("count", width=80, anchor="center")
        vsb = ttk.Scrollbar(frm, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set)
        tv.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for cat in sorted(stats.keys()):
            tv.insert("", "end", values=(cat, stats[cat]))

        def on_dbl_click(event):
            item = tv.focus()
            if not item:
                return
            cat = tv.item(item, "values")[0]
            # 清除旧选择
            for iid in self.tree.get_children():
                self.tree.selection_remove(iid)
            # 选中该分类对应项
            targets = [row["iid"] for row in self.plan if row["target"] == cat]
            for iid in targets:
                self.tree.selection_add(iid)
            if targets:
                self.tree.see(targets[0])
        tv.bind("<Double-1>", on_dbl_click)

        ttk.Button(frm, text="关闭", command=win.destroy).pack(anchor="e", pady=(8, 0))

    def exec_move(self):
        if not self.plan:
            messagebox.showinfo("无计划", "没有可移动的项，请先扫描。")
            return

        # 仅移动选中项
        work = self.plan
        if self.var_move_selected.get():
            selected = set(self.tree.selection())
            work = [it for it in self.plan if it["iid"] in selected]
            if not work:
                messagebox.showinfo("未选择", "未选择任何条目。")
                return
        self._work_subset = work

        self.btn_choose.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_move.config(state="disabled")
        self.btn_clear.config(state="disabled")
        self.btn_portable.config(state="disabled")

        t = threading.Thread(target=self._worker_move, daemon=True)
        t.start()

    def _worker_move(self):
        work = getattr(self, "_work_subset", self.plan)
        total = len(work)
        done = 0
        self.set_progress(0, total)

        for item in work:
            src: Path = item["path"]
            target_dir = self.root_dir / item["target"]
            dest = target_dir / src.name
            iid = item["iid"]

            if src.parent == target_dir:
                self.set_status(iid, "已在目标")
                self.log(f"跳过（已在目标）：{src}")
                done += 1
                self.set_progress(done, total)
                continue

            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    self.set_status(iid, "已存在")
                    self.log(f"已存在，跳过：{dest}")
                else:
                    shutil.move(str(src), str(dest))
                    self.set_status(iid, "已移动")
                    self.log(f"移动成功：{src} → {dest}")
            except Exception as e:
                self.set_status(iid, "失败")
                self.log(f"失败：{src} → {dest} | {repr(e)}")
            finally:
                done += 1
                self.set_progress(done, total)

        # 可选：删除空目录（仅根目录一层）
        if self.var_delete_empty.get():
            removed = 0
            for child in list(self.root_dir.iterdir()):
                try:
                    if child.is_dir() and child.name not in DEFAULT_TARGET_DIRS and child.name != PORTABLE_INDEX_DIR:
                        if not any(child.iterdir()):  # 空目录
                            child.rmdir()
                            removed += 1
                except Exception:
                    pass
            self.log(f"空目录清理完成：删除 {removed} 个。")

        self.btn_choose.config(state="normal")
        self.btn_scan.config(state="normal")
        self.btn_move.config(state="normal")
        self.btn_clear.config(state="normal")
        self.btn_portable.config(state="normal")
        messagebox.showinfo("完成", "执行结束，详见日志。")

    # ---------------- Portable index ----------------
    def build_portable_index(self):
        """在根目录创建 90_portable，生成 .url 快捷方式与 portable_list.txt（只做索引，不复制文件）"""
        if not self.root_dir or not self.root_dir.exists():
            messagebox.showwarning("未选择目录", "请先选择有效目录。")
            return
        if not self.portable_patterns:
            messagebox.showwarning("未配置规则", "规则文件中未定义 # portable_mark 段，无法识别便携软件。")
            return

        idx_dir = self.root_dir / PORTABLE_INDEX_DIR
        idx_dir.mkdir(parents=True, exist_ok=True)

        # 收集候选：根目录一层 + 各分类目录下一层
        candidates: List[Path] = []
        # 根目录
        for child in self.root_dir.iterdir():
            if child.name in {"System Volume Information", "$RECYCLE.BIN", PORTABLE_INDEX_DIR}:
                continue
            candidates.append(child)
        # 各分类目录下一层
        for cat in DEFAULT_TARGET_DIRS:
            p = self.root_dir / cat
            if p.is_dir():
                for sub in p.iterdir():
                    candidates.append(sub)

        # 生成 .url 与清单
        created = 0
        lines = []
        for p in candidates:
            name = p.name
            if is_portable(name, self.portable_patterns):
                target_uri = p.resolve().as_uri()  # file:///D:/...
                safe_name = re.sub(r'[\\/:*?"<>|]+', "_", name)[:200]
                url_file = idx_dir / f"{safe_name}.url"
                with url_file.open("w", encoding="utf-8") as f:
                    f.write("[InternetShortcut]\n")
                    f.write(f"URL={target_uri}\n")
                    f.write(f"IDList=\n")
                created += 1
                lines.append(f"{name}\t{p}")

        with (idx_dir / "portable_list.txt").open("w", encoding="utf-8") as f:
            f.write(time.strftime("Generated at %Y-%m-%d %H:%M:%S\n"))
            f.write(f"Total: {created}\n\n")
            for line in sorted(lines, key=str.lower):
                f.write(line + "\n")

        self.log(f"Portable 索引生成完成：{created} 个条目，目录：{idx_dir}")

    def clear_all(self):
        """清空主表、日志和进度条，重置计划"""
        self.tree.delete(*self.tree.get_children())
        self.txt_log.delete("1.0", "end")
        self.plan.clear()
        self.pb["value"] = 0
        self.log("已清空界面。")


if __name__ == "__main__":
    try:
        app = AutoSortApp()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("运行错误", repr(e))
