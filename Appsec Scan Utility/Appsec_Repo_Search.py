#!/usr/bin/env python3
"""
Repository Keyword Search Utility - Final with menu, shortcuts, auto-open summary toggle
Dependencies: customtkinter, openpyxl (pygments optional)
"""

import os
import re
import csv
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import json
import tempfile
import subprocess
import openpyxl
import customtkinter as ctk
import sys

try:
    from pygments.lexers import get_lexer_for_filename, guess_lexer_for_filename, TextLexer
    from pygments.token import Token as PToken
    PYGMENTS_AVAILABLE = True
except Exception:
    PYGMENTS_AVAILABLE = False

# ---------------------- Constants / Comment markers ----------------------
SINGLE_LINE_MARKERS = {
    ".py": ["#"],
    ".java": ["//"],
    ".js": ["//"],
    ".ts": ["//"],
    ".c": ["//"],
    ".cpp": ["//"],
    ".cs": ["//"],
    ".php": ["//", "#"],
    ".css": [],
    ".go": ["//"],
    ".rs": ["//"],
    ".swift": ["//"],
    ".sql": ["--"],
    ".html": [],
    ".xml": [],
    ".jsp": []
}

MULTI_COMMENT_TOKENS = {
    ".java": [("/*", "*/")],
    ".js": [("/*", "*/")],
    ".ts": [("/*", "*/")],
    ".c": [("/*", "*/")],
    ".cpp": [("/*", "*/")],
    ".cs": [("/*", "*/")],
    ".php": [("/*", "*/")],
    ".css": [("/*", "*/")],
    ".go": [("/*", "*/")],
    ".rs": [("/*", "*/")],
    ".swift": [("/*", "*/")],
    ".sql": [("/*", "*/")],
    ".html": [("<!--", "-->")],
    ".xml": [("<!--", "-->")],
    ".jsp": [("<%--", "--%>")],
    ".py": [('"""', '"""'), ("'''", "'''")],
    ".txt": []
}

APP_NAME = "RepoSearch"
HISTORY_FILENAME = "history.json"
MAX_HISTORY = 10

# ---------------------- Helpers ----------------------
def sanitize_excel_value(v):
    if not isinstance(v, str):
        v = str(v)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", v)

def _first_unquoted_marker_index(line, markers):
    n = len(line)
    i = 0
    in_squote = False
    in_dquote = False
    escape = False
    markers_sorted = sorted(markers, key=lambda m: -len(m))
    while i < n:
        ch = line[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if not in_dquote and ch == "'" and not in_squote:
            in_squote = True; i += 1; continue
        elif in_squote and ch == "'" and not escape:
            in_squote = False; i += 1; continue
        if not in_squote and ch == '"' and not in_dquote:
            in_dquote = True; i += 1; continue
        elif in_dquote and ch == '"' and not escape:
            in_dquote = False; i += 1; continue
        if not in_squote and not in_dquote:
            for m in markers_sorted:
                L = len(m)
                if i + L <= n and line[i:i+L] == m:
                    return i, m
        i += 1
    return -1, None

def get_history_path():
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, HISTORY_FILENAME)

def load_history():
    p = get_history_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"scans": []}

def save_history(history):
    p = get_history_path()
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        print("Failed to save history:", e)

# ---------------------- VarProxy (throttle UI updates) ----------------------
class VarProxy:
    def __init__(self, tk_root, real_var, interval_ms=120):
        self.root = tk_root
        self.real_var = real_var
        self.interval_ms = interval_ms
        self._pending = None
        self._job = None
        self._lock = threading.Lock()

    def set(self, value):
        with self._lock:
            self._pending = value
            if not self._job:
                self._job = self.root.after(self.interval_ms, self._flush)

    def _flush(self):
        with self._lock:
            if self._pending is not None:
                try:
                    self.real_var.set(self._pending)
                except Exception:
                    pass
                self._pending = None
            self._job = None

    def get(self):
        return self.real_var.get()

# ---------------------- Search implementation ----------------------
def search_in_files(base_path, keyword, extensions, exact_match, per_token, case_sensitive,
                    ignore_comments, safeguard_limit, filename_var,
                    progress_setter, progress_var, count_var, files_scanned_var, total_files_var,
                    stop_check=None):
    results = []
    file_list = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if extensions == ["*"] or any(file.endswith(ext) for ext in extensions):
                file_list.append(os.path.join(root, file))

    total_files = len(file_list)
    total_files_var.set(f"Total Files: {total_files}")
    match_count = 0
    update_chunk = 50
    search_keyword = keyword if case_sensitive else keyword.lower()
    token_splitter = re.compile(r"\W+")
    scanned_files = 0

    for idx, file in enumerate(file_list, start=1):
        if stop_check and stop_check():
            break
        ext = os.path.splitext(file)[1]
        single_markers = SINGLE_LINE_MARKERS.get(ext, [])
        multi_tokens = MULTI_COMMENT_TOKENS.get(ext, [])
        inside_multiline = False
        current_multi_end = None

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for i, raw_line in enumerate(f, start=1):
                    if stop_check and stop_check():
                        break
                    original_line = raw_line.rstrip("\n")
                    processing_line = original_line
                    if filename_var is not None:
                        display_path = file if len(file) <= 80 else "..." + file[-80:]
                        filename_var.set(f"Scanning: {display_path}")

                    if ignore_comments:
                        if inside_multiline:
                            if current_multi_end and current_multi_end in processing_line:
                                end_idx = processing_line.find(current_multi_end)
                                processing_line = processing_line[end_idx + len(current_multi_end):]
                                inside_multiline = False
                                current_multi_end = None
                            else:
                                continue
                        if multi_tokens:
                            while True:
                                earliest_start = -1
                                chosen_start, chosen_end = None, None
                                for s_tok, e_tok in multi_tokens:
                                    s_idx = processing_line.find(s_tok)
                                    if s_idx != -1 and (earliest_start == -1 or s_idx < earliest_start):
                                        earliest_start = s_idx
                                        chosen_start, chosen_end = s_tok, e_tok
                                if earliest_start == -1:
                                    break
                                e_idx = processing_line.find(chosen_end, earliest_start + len(chosen_start))
                                if e_idx != -1:
                                    processing_line = processing_line[:earliest_start] + processing_line[e_idx + len(chosen_end):]
                                    continue
                                else:
                                    processing_line = processing_line[:earliest_start]
                                    inside_multiline = True
                                    current_multi_end = chosen_end
                                    break
                        if single_markers:
                            marker_idx, marker = _first_unquoted_marker_index(processing_line, single_markers)
                            if marker_idx != -1:
                                processing_line = processing_line[:marker_idx]
                        if not processing_line.strip():
                            continue
                        mrk_idx, mrk = _first_unquoted_marker_index(processing_line, single_markers) if single_markers else (-1, None)
                        if mrk_idx == 0:
                            continue

                    search_line = processing_line if case_sensitive else processing_line.lower()
                    if per_token:
                        tokens = token_splitter.split(search_line)
                        match_found = (search_keyword in tokens)
                    elif exact_match:
                        match_found = (search_line.strip() == search_keyword)
                    else:
                        match_found = (search_keyword in search_line)

                    if match_found:
                        match_count += 1
                        results.append((file, i, original_line))
                        if match_count % update_chunk == 0:
                            count_var.set(f"Found Keywords: {match_count}")
                if stop_check and stop_check():
                    pass
        except Exception:
            pass

        scanned_files = idx
        files_scanned_var.set(f"Scanned: {scanned_files}/{max(1, total_files)}")
        progress_fraction = (scanned_files / max(1, total_files))
        if progress_setter:
            try:
                progress_setter(progress_fraction)
            except Exception:
                progress_var.set(f"{progress_fraction*100:.1f}%")
        else:
            progress_var.set(f"{progress_fraction*100:.1f}%")

        if stop_check and stop_check():
            break

    count_var.set(f"Found Keywords: {match_count}")
    return results, scanned_files, total_files

# ---------------------- App ----------------------
class SearchUtilityApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System"); ctk.set_default_color_theme("blue")
        self.title("Appsec Repository Search")
        self.geometry("1400x900")
        self.minsize(1200,700)

        # state
        self.stop_flag = False
        self.search_results = []
        self.history = load_history()
        self.auto_open_summary = tk.BooleanVar(value=True)  # default on; controlled by menu

        # UI variables
        self.progress_text = tk.StringVar(value="0.0%")
        self.found_text = tk.StringVar(value="Found Keywords: 0")
        self.files_scanned_text = tk.StringVar(value="Scanned: 0/0")
        self.current_file_text = tk.StringVar(value="")
        self.total_files_text = tk.StringVar(value="Total Files: 0")
        self.toast_text = tk.StringVar(value="")

        self._build_ui()
        self._bind_shortcuts()
        self._build_menu()

    def _build_menu(self):
        # top menubar with a short label (ellipsis) per request
        menubar = tk.Menu(self)
        more_menu = tk.Menu(menubar, tearoff=0)
        more_menu.add_checkbutton(label="Auto-open Summary", onvalue=1, offvalue=0, variable=self.auto_open_summary)
        more_menu.add_separator()
        more_menu.add_command(label="Shortcuts", command=self._show_shortcuts_help)
        more_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="⋯", menu=more_menu)  # short label
        self.config(menu=menubar)

    def _show_shortcuts_help(self):
        help_text = (
            "Keyboard Shortcuts:\n\n"
            "Ctrl+F — Focus Keyword\n"
            "Ctrl+L — Focus Folder\n"
            "Ctrl+R — Run Search\n"
            "Esc    — Cancel (confirmation)\n"
            "Ctrl+E — Export CSV\n"
            "Ctrl+Shift+E — Export Excel\n"
        )
        messagebox.showinfo("Shortcuts", help_text)

    def _show_about(self):
        messagebox.showinfo("About", "Repo Search Utility\nAuthor: (Aditya Dhande)\nProvides fast local keyword search and export.")

    def _bind_shortcuts(self):
        # Note: bind_all ensures shortcuts work regardless of widget focus
        self.bind_all("<Control-f>", lambda e: (self.keyword_entry.focus_set(), "break"))
        self.bind_all("<Control-F>", lambda e: (self.keyword_entry.focus_set(), "break"))
        self.bind_all("<Control-l>", lambda e: (self.folder_entry.focus_set(), "break"))
        self.bind_all("<Control-L>", lambda e: (self.folder_entry.focus_set(), "break"))
        self.bind_all("<Control-r>", lambda e: (self.start_search_thread(), "break"))
        self.bind_all("<Control-R>", lambda e: (self.start_search_thread(), "break"))
        self.bind_all("<Escape>", lambda e: (self.cancel_search_immediate(), "break"))
        self.bind_all("<Control-e>", lambda e: (self._export("csv"), "break"))
        # Ctrl+Shift+E: platform dependent; use uppercase E to catch shift
        self.bind_all("<Control-Shift-E>", lambda e: (self._export("excel"), "break"))
        self.bind_all("<Control-Shift-e>", lambda e: (self._export("excel"), "break"))

    def _build_ui(self):
        pad = 12
        self.notebook = ttk.Notebook(self)
        self.tab_search = ttk.Frame(self.notebook)
        self.tab_summary = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_search, text="Search")
        self.notebook.add(self.tab_summary, text="Summary")
        self.notebook.pack(fill="both", expand=True, padx=pad, pady=pad)

        self._build_search_tab(self.tab_search)
        self._build_summary_tab(self.tab_summary)

    def _build_search_tab(self, parent):
        pad = 12
        top = ctk.CTkFrame(parent, corner_radius=8)
        top.grid(row=0, column=0, padx=pad, pady=pad, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Keyword:").grid(row=0, column=0, sticky="e", padx=(10,4), pady=8)
        self.keyword_entry = ctk.CTkEntry(top, width=520, placeholder_text="Enter keyword")
        self.keyword_entry.grid(row=0, column=1, sticky="w", pady=8)

        ctk.CTkLabel(top, text="Folder:").grid(row=1, column=0, sticky="e", padx=(10,4), pady=8)
        self.folder_entry = ctk.CTkEntry(top, width=520, placeholder_text="Select folder to search")
        self.folder_entry.grid(row=1, column=1, sticky="w", pady=8)
        ctk.CTkButton(top, text="Browse", width=110, command=self.browse_folder).grid(row=1, column=2, padx=10)

        ctk.CTkLabel(top, text="File Ext:").grid(row=2, column=0, sticky="e", padx=(10,4), pady=8)
        self.extension_cb = ctk.CTkComboBox(top, values=["All", ".java", ".jsp", ".py", ".cpp", ".html", ".js", "Custom"], width=300)
        self.extension_cb.set("All")
        self.extension_cb.configure(command=self._on_ext_change)
        self.extension_cb.grid(row=2, column=1, sticky="w", pady=8)

        ctk.CTkLabel(top, text="Custom Ext:").grid(row=3, column=0, sticky="e", padx=(10,4), pady=8)
        self.custom_ext_entry = ctk.CTkEntry(top, width=300, placeholder_text=".py,.java")
        self.custom_ext_entry.grid(row=3, column=1, sticky="w", pady=8)
        self.custom_ext_entry.grid_remove()

        opts = ctk.CTkFrame(parent, corner_radius=8)
        opts.grid(row=1, column=0, padx=pad, pady=(0,pad), sticky="ew")
        opts.grid_columnconfigure(3, weight=1)

        self.exact_var = tk.BooleanVar(value=False)
        self.token_var = tk.BooleanVar(value=False)
        self.case_var = tk.BooleanVar(value=False)

        ctk.CTkCheckBox(opts, text="Exact", variable=self.exact_var).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkCheckBox(opts, text="Per Token", variable=self.token_var).grid(row=0, column=1, padx=10, pady=8, sticky="w")
        ctk.CTkCheckBox(opts, text="Case", variable=self.case_var).grid(row=0, column=2, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(opts, text="Ignore Comments:").grid(row=1, column=0, padx=10, pady=8, sticky="e")
        self.comment_filter_cb = ctk.CTkComboBox(opts, values=["Yes", "No"], width=120)
        self.comment_filter_cb.set("Yes")
        self.comment_filter_cb.grid(row=1, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(opts, text="Safeguard:").grid(row=1, column=2, padx=10, pady=8, sticky="e")
        self.safeguard_entry = ctk.CTkEntry(opts, width=120)
        self.safeguard_entry.insert(0, "5000")
        self.safeguard_entry.grid(row=1, column=3, padx=10, pady=8, sticky="w")

        btn_frame = ctk.CTkFrame(parent, corner_radius=8)
        btn_frame.grid(row=2, column=0, padx=pad, pady=(0,pad), sticky="ew")
        btn_frame.grid_columnconfigure((0,1,2), weight=1, uniform="a")

        self.run_btn = ctk.CTkButton(btn_frame, text="Run", fg_color="#4CAF50", hover_color="#45a049", command=self.start_search_thread)
        self.run_btn.grid(row=0, column=0, padx=8, pady=10, sticky="ew")
        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="#f44336", hover_color="#e53935", command=self.cancel_search_immediate)
        self.cancel_btn.grid(row=0, column=1, padx=8, pady=10, sticky="ew")
        self.clear_btn = ctk.CTkButton(btn_frame, text="Clear", fg_color="#008CBA", hover_color="#007BB5", command=self.clear_results)
        self.clear_btn.grid(row=0, column=2, padx=8, pady=10, sticky="ew")

        status = ctk.CTkFrame(parent, corner_radius=8)
        status.grid(row=3, column=0, padx=pad, pady=(0,pad), sticky="ew")
        status.grid_columnconfigure(1, weight=1)

        self.progress_bar = ctk.CTkProgressBar(status, width=700)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkLabel(status, textvariable=self.progress_text).grid(row=0, column=1, padx=8, pady=10, sticky="w")

        # proxies
        self.files_scanned_proxy = VarProxy(self, self.files_scanned_text, interval_ms=120)
        self.progress_text_proxy = VarProxy(self, self.progress_text, interval_ms=120)

        ctk.CTkLabel(status, textvariable=self.files_scanned_text).grid(row=1, column=0, padx=12, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.total_files_text).grid(row=1, column=1, padx=8, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.current_file_text, wraplength=1000).grid(row=2, column=0, columnspan=2, padx=12, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.found_text, font=("Arial", 12, "bold")).grid(row=0, column=2, padx=12, pady=10, sticky="e")

        self.toast_label = ctk.CTkLabel(parent, textvariable=self.toast_text, fg_color="#333333", text_color="white", corner_radius=8)
        self.toast_label.grid(row=6, column=0, pady=(0,6))
        self.toast_label.grid_remove()

        # results
        results_frame = ctk.CTkFrame(parent, corner_radius=8)
        results_frame.grid(row=4, column=0, padx=pad, pady=(0,pad), sticky="nsew")
        parent.grid_rowconfigure(4, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)

        cols = ("#", "File Path", "Line Number", "Line Content")
        self.tree = ttk.Treeview(results_frame, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("#", width=60, anchor="center")
        self.tree.column("File Path", width=420, anchor="w")
        self.tree.column("Line Number", width=100, anchor="center")
        self.tree.column("Line Content", width=700, anchor="w")

        yscroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=yscroll.set, xscroll=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        bottom_frame = ctk.CTkFrame(parent, corner_radius=8)
        bottom_frame.grid(row=5, column=0, padx=pad, pady=(0,pad), sticky="ew")
        bottom_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkButton(bottom_frame, text="Export XLSX", command=lambda: self._export("excel"), width=140, fg_color="#0D47A1").grid(row=0, column=0, padx=10, pady=12, sticky="w")
        ctk.CTkButton(bottom_frame, text="Export CSV", command=lambda: self._export("csv"), width=140, fg_color="#2E7D32").grid(row=0, column=1, padx=10, pady=12, sticky="w")

    def _build_summary_tab(self, parent):
        pad = 12
        summary_frame = ctk.CTkFrame(parent, corner_radius=8)
        summary_frame.pack(fill="both", expand=True, padx=pad, pady=pad)

        ctk.CTkLabel(summary_frame, text="Recent Scans (latest 10)", font=("Arial", 12, "bold")).pack(anchor="nw", pady=(6,10))

        scols = ("#", "Timestamp", "Keyword", "Folder", "Files", "Matches", "Duration(s)", "Status")
        self.summary_tree = ttk.Treeview(summary_frame, columns=scols, show="headings", height=10)
        for c in scols:
            self.summary_tree.heading(c, text=c)
            self.summary_tree.column(c, width=140, anchor="center")
        self.summary_tree.pack(fill="x", padx=6, pady=6)
        s_vsb = ttk.Scrollbar(summary_frame, orient="vertical", command=self.summary_tree.yview)
        self.summary_tree.configure(yscroll=s_vsb.set)
        s_vsb.place(relx=0.98, rely=0.09, relheight=0.5)

        self.summary_tree.tag_configure("status_success", foreground="green")
        self.summary_tree.tag_configure("status_cancelled", foreground="red")
        self.summary_tree.tag_configure("status_other", foreground="black")

        self.summary_detail_text = tk.Text(summary_frame, height=10, width=80, state="disabled", wrap="word")
        self.summary_detail_text.pack(fill="both", expand=False, padx=6, pady=6)

        btns = ctk.CTkFrame(summary_frame)
        btns.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(btns, text="Rerun", command=self.rerun_selected_summary).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Open", command=self.open_selected_export).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Delete", command=self.delete_selected_summary).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Clear All", command=self.clear_summary_history).pack(side="left", padx=6)

        self._refresh_summary_tree()
        self.summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)

    # ---------- UI helpers ----------
    def _on_ext_change(self, value=None):
        try:
            sel = self.extension_cb.get()
        except Exception:
            sel = None
        if sel == "Custom":
            self.custom_ext_entry.grid()
        else:
            self.custom_ext_entry.delete(0, tk.END)
            self.custom_ext_entry.grid_remove()

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)

    def start_search_thread(self):
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.stop_flag = False
        self.search_results = []
        self.tree.delete(*self.tree.get_children())
        self.found_text.set("Found Keywords: 0")
        self.files_scanned_text.set("Scanned: 0/0")
        self.total_files_text.set("Total Files: 0")
        self.current_file_text.set("")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0%")
        self.toast_text.set("")
        self.toast_label.grid_remove()
        threading.Thread(target=self._search_worker, daemon=True).start()

    def cancel_search_immediate(self):
        confirm = messagebox.askyesno("Confirm", "Cancel search?")
        if confirm:
            self.stop_flag = True
            self.current_file_text.set("Cancelling...")
            self.cancel_btn.configure(state="disabled")

    def clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.search_results = []
        self.found_text.set("Found Keywords: 0")
        self.files_scanned_text.set("Scanned: 0/0")
        self.total_files_text.set("Total Files: 0")
        self.current_file_text.set("")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0%")
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        self.stop_flag = False
        self.toast_text.set("")
        self.toast_label.grid_remove()

    def _safe_ui_update(self, progress=None, files_scanned=None, found_count=None, current_file=None, total_files=None, final=False):
        def _apply():
            if progress is not None:
                try:
                    self.progress_bar.set(progress)
                    self.progress_text.set(f"{progress*100:.1f}%")
                except Exception:
                    self.progress_text.set(f"{progress*100:.1f}%")
            if files_scanned is not None:
                self.files_scanned_text.set(f"Scanned: {files_scanned}/{self.total_files}")
            if found_count is not None:
                self.found_text.set(f"Found Keywords: {found_count}")
            if current_file is not None:
                self.current_file_text.set(current_file)
            if total_files is not None:
                self.total_files_text.set(f"Total Files: {total_files}")
            if final:
                self.current_file_text.set("Search completed.")
                self.run_btn.configure(state="normal")
                self.cancel_btn.configure(state="normal")
        self.after(1, _apply)

    def show_toast(self, message, duration_ms=3000):
        self.toast_text.set(message)
        self.toast_label.grid()
        self.after(duration_ms, lambda: (self.toast_text.set(""), self.toast_label.grid_remove()))

    # ---------- Export (CSV/XLSX) ----------
    def _export(self, fmt):
        if not self.search_results:
            messagebox.showwarning("No Results", "No results to export.")
            return
        if fmt == "csv":
            file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")], title="Save CSV as...")
        else:
            file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files","*.xlsx")], title="Save Excel as...")
        if not file_path:
            return

        remove_dup = messagebox.askyesno("Remove duplicates", "Remove duplicate rows (unique file+line) in exported results?")
        export_list = []
        seen = set()
        for fp, ln, txt in self.search_results:
            key = (fp, ln, txt)
            if remove_dup and key in seen:
                continue
            seen.add(key)
            export_list.append((fp, ln, txt))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "csv":
            out = f"{file_path}_{timestamp}.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["#", "File Path", "Line Number", "Line Content"])
                for i, (fp, ln, txt) in enumerate(export_list, start=1):
                    w.writerow([i, fp, ln, txt])
                w.writerow([])
                w.writerow(["--- SUMMARY ---"])
                w.writerow(["Search Keyword:", self.keyword_entry.get().strip()])
                w.writerow(["Total Matches:", len(self.search_results)])
                ufiles = sorted(set([r[0] for r in self.search_results]))
                w.writerow(["Unique Files Count:", len(ufiles)])
                w.writerow(["Unique Files:"])
                for uf in ufiles:
                    w.writerow([uf])
            messagebox.showinfo("Export", f"CSV exported: {out}")
            # record in latest summary entry if exists
            if self.history.get("scans"):
                self.history['scans'][0]['export_csv'] = out
                save_history(self.history)
                self._refresh_summary_tree()
        else:
            out = f"{file_path}_{timestamp}.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Results"
            ws.append(["#", "File Path", "Line Number", "Line Content"])
            for i, (fp, ln, txt) in enumerate(export_list, start=1):
                ws.append([sanitize_excel_value(i), sanitize_excel_value(fp), sanitize_excel_value(ln), sanitize_excel_value(txt)])
            s = wb.create_sheet(title="Summary")
            s.append(["--- SUMMARY ---"])
            s.append(["Search Keyword", self.keyword_entry.get().strip()])
            s.append(["Total Matches", len(self.search_results)])
            ufiles = sorted(set([r[0] for r in self.search_results]))
            s.append(["Unique Files Count", len(ufiles)])
            s.append([])
            s.append(["Unique Files"])
            for uf in ufiles:
                s.append([sanitize_excel_value(uf)])
            wb.save(out)
            messagebox.showinfo("Export", f"Excel exported: {out}")
            if self.history.get("scans"):
                self.history['scans'][0]['export_xlsx'] = out
                save_history(self.history)
                self._refresh_summary_tree()

    # ---------- file opener used by summary ----------
    def _open_file_path(self, p):
        if not p or not os.path.exists(p):
            messagebox.showinfo("Open", "File not found.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(p)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def open_selected_export(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a summary row.")
            return
        idx = int(sel[0])
        try:
            s = self.history['scans'][idx]
        except Exception:
            return
        csv_p = s.get("export_csv")
        xlsx_p = s.get("export_xlsx")
        # prefer csv if both exist
        if csv_p and os.path.exists(csv_p):
            self._open_file_path(csv_p)
        elif xlsx_p and os.path.exists(xlsx_p):
            self._open_file_path(xlsx_p)
        else:
            messagebox.showinfo("Open", "No exported file found for this scan.")

    # ---------- Search worker ----------
    def _search_worker(self):
        keyword = self.keyword_entry.get().strip()
        folder = self.folder_entry.get().strip()
        if not folder or not keyword:
            messagebox.showwarning("Input Error", "Provide folder and keyword.")
            self.run_btn.configure(state="normal")
            return

        ext_choice = self.extension_cb.get()
        if ext_choice == "All":
            extensions = ["*"]
        elif ext_choice == "Custom":
            custom_ext = self.custom_ext_entry.get().strip()
            if not custom_ext:
                messagebox.showwarning("Input Error", "Enter at least one extension.")
                self.run_btn.configure(state="normal")
                return
            extensions = [e.strip() for e in custom_ext.split(",")]
        else:
            extensions = [ext_choice]

        exact_flag = bool(self.exact_var.get())
        token_flag = bool(self.token_var.get())
        case_flag = bool(self.case_var.get())
        ignore_comments_flag = True if self.comment_filter_cb.get() == "Yes" else False
        try:
            safeguard_limit_val = int(self.safeguard_entry.get())
        except Exception:
            safeguard_limit_val = 5000

        def progress_setter(frac):
            try:
                self.progress_text_proxy.set(f"{frac*100:.1f}%")
                self._safe_ui_update(progress=frac)
            except Exception:
                pass

        def stop_check():
            return self.stop_flag

        start_time = time.time()
        results, scanned_count, total_files = search_in_files(
            folder, keyword, extensions, exact_flag, token_flag, case_flag,
            ignore_comments_flag, safeguard_limit_val, self.current_file_text,
            progress_setter, self.progress_text_proxy, self.found_text, self.files_scanned_proxy, self.total_files_text,
            stop_check=stop_check
        )
        duration = time.time() - start_time

        self.search_results = results
        self.tree.delete(*self.tree.get_children())
        display_limit = safeguard_limit_val
        for idx, row in enumerate(self.search_results[:display_limit], start=1):
            fp, ln, txt = row
            self.tree.insert("", "end", values=(idx, fp, ln, txt))

        if len(self.search_results) > display_limit:
            self.after(10, lambda: messagebox.showwarning("Safeguard", f"{display_limit} results shown. Total matches: {len(self.search_results)}"))

        if self.stop_flag:
            self._safe_ui_update(progress=1.0, files_scanned=scanned_count, found_count=len(self.search_results), current_file="Search cancelled.", total_files=total_files, final=True)
            self.show_toast("Search cancelled.", duration_ms=3000)
            status = "cancelled"
        else:
            self._safe_ui_update(progress=1.0, files_scanned=scanned_count, found_count=len(self.search_results), current_file="Search completed.", total_files=total_files, final=True)
            status = "success"

        top_files = {}
        for fp, ln, txt in self.search_results:
            top_files[fp] = top_files.get(fp, 0) + 1
        top_sorted = sorted(top_files.items(), key=lambda x: x[1], reverse=True)[:3]
        top_fmt = [{"path": p, "count": c} for p, c in top_sorted]

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "Local",
            "target": folder,
            "keyword": keyword,
            "extensions": extensions,
            "files_scanned": scanned_count,
            "total_files": total_files,
            "matches_found": len(self.search_results),
            "top_files": top_fmt,
            "duration_seconds": round(duration, 2),
            "status": status,
            "export_csv": None,
            "export_xlsx": None,
            "errors": None
        }

        hist = load_history()
        hist['scans'].insert(0, entry)
        hist['scans'] = hist['scans'][:MAX_HISTORY]
        save_history(hist)
        self.history = hist
        self._refresh_summary_tree()

        # if auto-open enabled, switch to summary tab
        if self.auto_open_summary.get():
            self.notebook.select(self.tab_summary)

        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        self.stop_flag = False

    # ---------- Summary UI ops ----------
    def _refresh_summary_tree(self):
        for iid in self.summary_tree.get_children():
            self.summary_tree.delete(iid)
        scans = self.history.get("scans", [])
        for idx, s in enumerate(scans, start=1):
            ts = s.get("timestamp", "")
            kw = s.get("keyword", "")
            targ = (s.get("target") or "")[:40]
            files = f"{s.get('files_scanned',0)}/{s.get('total_files',0)}"
            matches = s.get("matches_found", 0)
            dur = s.get("duration_seconds", 0)
            status = s.get("status", "")
            tag = "status_other"
            if status == "success":
                display_status = "✔ Success"
                tag = "status_success"
            elif status == "cancelled":
                display_status = "✖ Cancelled"
                tag = "status_cancelled"
            else:
                display_status = status or "Unknown"
            self.summary_tree.insert("", "end", iid=str(idx-1), values=(idx, ts, kw, targ, files, matches, dur, display_status), tags=(tag,))

    def _on_summary_select(self, _evt=None):
        sel = self.summary_tree.selection()
        if not sel: return
        idx = int(sel[0])
        try:
            s = self.history['scans'][idx]
        except Exception:
            return
        self.summary_detail_text.config(state="normal")
        self.summary_detail_text.delete("1.0", "end")
        self.summary_detail_text.insert("1.0", f"Timestamp: {s.get('timestamp')}\n")
        self.summary_detail_text.insert("end", f"Keyword: {s.get('keyword')}\n")
        self.summary_detail_text.insert("end", f"Folder: {s.get('target')}\n")
        self.summary_detail_text.insert("end", f"Extensions: {', '.join(s.get('extensions',[]))}\n")
        self.summary_detail_text.insert("end", f"Files scanned: {s.get('files_scanned')}/{s.get('total_files')}\n")
        self.summary_detail_text.insert("end", f"Matches found: {s.get('matches_found')}\n")
        top = s.get('top_files', [])
        if top:
            self.summary_detail_text.insert("end", "Top files:\n")
            for tf in top:
                self.summary_detail_text.insert("end", f"  {tf.get('path')} ({tf.get('count')})\n")
        self.summary_detail_text.insert("end", f"Duration (s): {s.get('duration_seconds')}\n")
        self.summary_detail_text.insert("end", f"Status: {s.get('status')}\n")
        self.summary_detail_text.insert("end", f"Export CSV: {s.get('export_csv')}\n")
        self.summary_detail_text.insert("end", f"Export XLSX: {s.get('export_xlsx')}\n")
        self.summary_detail_text.config(state="disabled")

    def rerun_selected_summary(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a summary entry.")
            return
        idx = int(sel[0])
        try:
            s = self.history['scans'][idx]
        except Exception:
            return
        # switch to Search tab and prefill & auto-run
        self.notebook.select(self.tab_search)
        self.keyword_entry.delete(0, tk.END); self.keyword_entry.insert(0, s.get("keyword",""))
        self.folder_entry.delete(0, tk.END); self.folder_entry.insert(0, s.get("target",""))
        exts = s.get("extensions", [])
        if exts and exts != ["*"]:
            self.extension_cb.set("Custom")
            self.custom_ext_entry.grid()
            self.custom_ext_entry.delete(0, tk.END)
            self.custom_ext_entry.insert(0, ",".join([e for e in exts]))
        else:
            self.extension_cb.set("All")
            self.custom_ext_entry.grid_remove()
        self.start_search_thread()

    def open_selected_csv(self):
        # kept for compatibility; prefer open_selected_export
        self.open_selected_export()

    def delete_selected_summary(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a summary entry.")
            return
        idx = int(sel[0])
        if messagebox.askyesno("Confirm Delete", "Delete selected summary entry?"):
            try:
                del self.history['scans'][idx]
                save_history(self.history)
                self._refresh_summary_tree()
                self.summary_detail_text.config(state="normal"); self.summary_detail_text.delete("1.0","end"); self.summary_detail_text.config(state="disabled")
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))

    def clear_summary_history(self):
        if messagebox.askyesno("Confirm", "Clear all stored summary history?"):
            self.history = {"scans": []}
            save_history(self.history)
            self._refresh_summary_tree()
            self.summary_detail_text.config(state="normal"); self.summary_detail_text.delete("1.0","end"); self.summary_detail_text.config(state="disabled")

# ---------------------- Run ----------------------
if __name__ == "__main__":
    if not PYGMENTS_AVAILABLE:
        msg = ("Pygments not installed. Comment filtering may be slightly less accurate.\nInstall: pip install pygments\nContinue?")
        root_tmp = tk.Tk(); root_tmp.withdraw()
        if not messagebox.askyesno("Pygments missing", msg):
            raise SystemExit()
        root_tmp.destroy()
    app = SearchUtilityApp()
    app.mainloop()
