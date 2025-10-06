#!/usr/bin/env python3
"""
Advanced Keyword Search Utility - Updated:
- Fixes: Custom extension field visibility (CTkComboBox command)
- Cancel flow: pause -> confirm -> stop/resume (immediate pause on Cancel click)
Other functionality unchanged.
Dependencies: customtkinter, openpyxl, pygments (optional)
"""

import os
import re
import csv
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import openpyxl
import customtkinter as ctk

try:
    from pygments.lexers import get_lexer_for_filename, guess_lexer_for_filename, TextLexer
    from pygments.token import Token as PToken
    PYGMENTS_AVAILABLE = True
except Exception:
    PYGMENTS_AVAILABLE = False

# ---------------------- COMMENT MARKERS / TOKENS ----------------------
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

# ---------------------- HELPERS ----------------------
def sanitize_excel_value(v):
    if not isinstance(v, str):
        v = str(v)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", v)

def _first_unquoted_marker_index(line, markers):
    """
    Return (idx, marker) of the earliest marker in 'line' that is NOT inside a single/double-quoted string.
    If none found, return (-1, None).
    """
    earliest = -1
    earliest_marker = None
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
            in_squote = True
            i += 1
            continue
        elif in_squote and ch == "'" and not escape:
            in_squote = False
            i += 1
            continue
        if not in_squote and ch == '"' and not in_dquote:
            in_dquote = True
            i += 1
            continue
        elif in_dquote and ch == '"' and not escape:
            in_dquote = False
            i += 1
            continue

        if not in_squote and not in_dquote:
            for m in markers_sorted:
                L = len(m)
                if i + L <= n and line[i:i+L] == m:
                    return i, m
        i += 1
    return -1, None

# ---------------------- SEARCH FUNCTION (enhanced) ----------------------
def search_in_files(base_path, keyword, extensions, exact_match, per_token, case_sensitive,
                    ignore_comments, safeguard_limit, filename_var,
                    progress_setter, progress_var, count_var, files_scanned_var, total_files_var,
                    stop_check=None, pause_check=None):
    """
    - stop_check: optional callable that returns True if search should stop immediately.
    - pause_check: optional callable that returns True while the worker should pause (blocked).
    All other behavior preserved.
    """
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

    for idx, file in enumerate(file_list, start=1):
        # check stop at file granularity
        if stop_check and stop_check():
            break

        # handle pause: if pause_check returns True, block here until cleared or stopped
        while pause_check and pause_check():
            # still allow immediate termination while paused
            if stop_check and stop_check():
                break
            time.sleep(0.08)  # short sleep to be responsive

        if stop_check and stop_check():
            break

        ext = os.path.splitext(file)[1]
        single_markers = SINGLE_LINE_MARKERS.get(ext, [])
        multi_tokens = MULTI_COMMENT_TOKENS.get(ext, [])

        inside_multiline = False
        current_multi_end = None

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                for i, raw_line in enumerate(lines, start=1):
                    # check cancellation mid-file
                    if stop_check and stop_check():
                        break

                    # handle pause mid-file
                    while pause_check and pause_check():
                        if stop_check and stop_check():
                            break
                        time.sleep(0.08)
                    if stop_check and stop_check():
                        break

                    original_line = raw_line.rstrip("\n")
                    processing_line = original_line
                    display_line = original_line

                    # update current filename in UI
                    if filename_var is not None:
                        display_path = file if len(file) <= 80 else "..." + file[-80:]
                        filename_var.set(f"Scanning: {display_path}")

                    if ignore_comments:
                        # if inside multiline block, look for end
                        if inside_multiline:
                            if current_multi_end and current_multi_end in processing_line:
                                end_idx = processing_line.find(current_multi_end)
                                processing_line = processing_line[end_idx + len(current_multi_end):]
                                inside_multiline = False
                                current_multi_end = None
                            else:
                                # whole line inside block comment -> skip
                                continue

                        # remove inline multiline blocks or enter multiline mode
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

                        # remove inline single-line comment tails safely (marker not inside string)
                        if single_markers:
                            marker_idx, marker = _first_unquoted_marker_index(processing_line, single_markers)
                            if marker_idx != -1:
                                processing_line = processing_line[:marker_idx]

                        # if remaining text empty or starts with marker -> skip
                        stripped_remaining = processing_line.strip()
                        if not stripped_remaining:
                            continue
                        is_entire_comment = False
                        for m in single_markers:
                            mrk_idx, mrk = _first_unquoted_marker_index(stripped_remaining, single_markers)
                            if mrk_idx == 0:
                                is_entire_comment = True
                                break
                        if is_entire_comment:
                            continue

                    # prepare for search
                    search_line = processing_line if case_sensitive else processing_line.lower()

                    # matching logic
                    if per_token:
                        tokens = token_splitter.split(search_line)
                        match_found = (search_keyword in tokens)
                    elif exact_match:
                        match_found = (search_line.strip() == search_keyword)
                    else:
                        match_found = (search_keyword in search_line)

                    if match_found:
                        match_count += 1
                        results.append((file, i, display_line))
                        if match_count % update_chunk == 0:
                            count_var.set(f"Found Keywords: {match_count}")

                # end per-line loop
                if stop_check and stop_check():
                    break

        except Exception:
            # skip unreadable files
            pass

        # update per-file progress
        files_scanned_var.set(f"Scanned: {idx}/{max(1, total_files)}")
        progress_fraction = (idx / max(1, total_files))
        if progress_setter:
            try:
                progress_setter(progress_fraction)
            except Exception:
                progress_var.set(f"{progress_fraction*100:.1f}%")
        else:
            progress_var.set(f"{progress_fraction*100:.1f}%")

        # check cancellation between files
        if stop_check and stop_check():
            break

    count_var.set(f"Found Keywords: {match_count}")
    return results

# ---------------------- CUSTOMTKINTER APP ----------------------
class SearchUtilityApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.title("Advanced Keyword Search Utility")
        self.geometry("1400x900")
        self.minsize(1200,700)

        # state
        self.stop_flag = False        # true => worker should stop
        self.pause_flag = False       # true => worker should pause
        self.search_results = []
        self.match_count = 0
        self.files_scanned = 0
        self.total_files = 0

        # UI variables
        self.progress_text = tk.StringVar(value="0.0%")
        self.found_text = tk.StringVar(value="Found Keywords: 0")
        self.files_scanned_text = tk.StringVar(value="Scanned: 0/0")
        self.current_file_text = tk.StringVar(value="")
        self.total_files_text = tk.StringVar(value="Total Files: 0")

        # toast for cancellation/completion messages
        self.toast_text = tk.StringVar(value="")
        self._build_ui()

    def _build_ui(self):
        pad = 12

        top = ctk.CTkFrame(self, corner_radius=8)
        top.grid(row=0, column=0, padx=pad, pady=pad, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Keyword:").grid(row=0, column=0, sticky="e", padx=(10,4), pady=8)
        self.keyword_entry = ctk.CTkEntry(top, width=520, placeholder_text="Enter keyword")
        self.keyword_entry.grid(row=0, column=1, sticky="w", pady=8)

        ctk.CTkLabel(top, text="Folder:").grid(row=1, column=0, sticky="e", padx=(10,4), pady=8)
        self.folder_entry = ctk.CTkEntry(top, width=520, placeholder_text="Select folder to search")
        self.folder_entry.grid(row=1, column=1, sticky="w", pady=8)
        ctk.CTkButton(top, text="Browse", width=110, command=self.browse_folder).grid(row=1, column=2, padx=10)

        ctk.CTkLabel(top, text="File Extension:").grid(row=2, column=0, sticky="e", padx=(10,4), pady=8)
        self.extension_cb = ctk.CTkComboBox(top, values=["All", ".java", ".jsp", ".py", ".cpp", ".html", ".js", "Custom"], width=300)
        self.extension_cb.set("All")
        # use command callback to reliably detect selection changes
        self.extension_cb.configure(command=self._on_ext_change)
        self.extension_cb.grid(row=2, column=1, sticky="w", pady=8)

        ctk.CTkLabel(top, text="Custom Extension:").grid(row=3, column=0, sticky="e", padx=(10,4), pady=8)
        self.custom_ext_entry = ctk.CTkEntry(top, width=300, placeholder_text="Comma-separated extensions (e.g. .py,.java)")
        # hide custom extension initially
        self.custom_ext_entry.grid(row=3, column=1, sticky="w", pady=8)
        self.custom_ext_entry.grid_remove()

        opts = ctk.CTkFrame(self, corner_radius=8)
        opts.grid(row=1, column=0, padx=pad, pady=(0,pad), sticky="ew")
        opts.grid_columnconfigure(3, weight=1)

        self.exact_var = tk.BooleanVar(value=False)
        self.token_var = tk.BooleanVar(value=False)
        self.case_var = tk.BooleanVar(value=False)

        ctk.CTkCheckBox(opts, text="Exact Match", variable=self.exact_var).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkCheckBox(opts, text="Per Token Match", variable=self.token_var).grid(row=0, column=1, padx=10, pady=8, sticky="w")
        ctk.CTkCheckBox(opts, text="Case Sensitive", variable=self.case_var).grid(row=0, column=2, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(opts, text="Ignore in Comments:").grid(row=1, column=0, padx=10, pady=8, sticky="e")
        self.comment_filter_cb = ctk.CTkComboBox(opts, values=["Yes", "No"], width=120)
        self.comment_filter_cb.set("Yes")
        self.comment_filter_cb.grid(row=1, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(opts, text="Safeguard Limit (UI results):").grid(row=1, column=2, padx=10, pady=8, sticky="e")
        self.safeguard_entry = ctk.CTkEntry(opts, width=120)
        self.safeguard_entry.insert(0, "5000")
        self.safeguard_entry.grid(row=1, column=3, padx=10, pady=8, sticky="w")

        btn_frame = ctk.CTkFrame(self, corner_radius=8)
        btn_frame.grid(row=2, column=0, padx=pad, pady=(0,pad), sticky="ew")
        btn_frame.grid_columnconfigure((0,1,2), weight=1, uniform="a")

        self.run_btn = ctk.CTkButton(btn_frame, text="Run Search", fg_color="#4CAF50",
                                     hover_color="#45a049", command=self.start_search_thread)
        self.run_btn.grid(row=0, column=0, padx=8, pady=10, sticky="ew")
        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="#f44336",
                                        hover_color="#e53935", command=self.cancel_search)
        self.cancel_btn.grid(row=0, column=1, padx=8, pady=10, sticky="ew")
        self.clear_btn = ctk.CTkButton(btn_frame, text="Clear Results", fg_color="#008CBA",
                                       hover_color="#007BB5", command=self.clear_results)
        self.clear_btn.grid(row=0, column=2, padx=8, pady=10, sticky="ew")

        status = ctk.CTkFrame(self, corner_radius=8)
        status.grid(row=3, column=0, padx=pad, pady=(0,pad), sticky="ew")
        status.grid_columnconfigure(1, weight=1)

        self.progress_bar = ctk.CTkProgressBar(status, width=700)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkLabel(status, textvariable=self.progress_text).grid(row=0, column=1, padx=8, pady=10, sticky="w")
        ctk.CTkLabel(status, textvariable=self.files_scanned_text).grid(row=1, column=0, padx=12, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.total_files_text).grid(row=1, column=1, padx=8, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.current_file_text, wraplength=1000).grid(row=2, column=0, columnspan=2, padx=12, pady=(0,12), sticky="w")
        ctk.CTkLabel(status, textvariable=self.found_text, font=("Arial", 12, "bold")).grid(row=0, column=2, padx=12, pady=10, sticky="e")

        # Toast label (hidden until used)
        self.toast_label = ctk.CTkLabel(self, textvariable=self.toast_text, fg_color="#333333", text_color="white", corner_radius=8)
        self.toast_label.grid(row=6, column=0, pady=(0,6))
        self.toast_label.grid_remove()

        results_frame = ctk.CTkFrame(self, corner_radius=8)
        results_frame.grid(row=4, column=0, padx=pad, pady=(0,pad), sticky="nsew")
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)
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

        bottom_frame = ctk.CTkFrame(self, corner_radius=8)
        bottom_frame.grid(row=5, column=0, padx=pad, pady=(0,pad), sticky="ew")
        bottom_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkButton(bottom_frame, text="Export Excel", command=lambda: self._export("excel"),
                      width=140, fg_color="#0D47A1").grid(row=0, column=0, padx=10, pady=12, sticky="w")
        ctk.CTkButton(bottom_frame, text="Export CSV", command=lambda: self._export("csv"),
                      width=140, fg_color="#2E7D32").grid(row=0, column=1, padx=10, pady=12, sticky="w")

    def _on_ext_change(self, value=None):
        """
        Called via CTkComboBox 'command' (value param provided by CTk).
        Show the custom extension entry only when 'Custom' selected.
        """
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
        # disable run, enable cancel, reset flags
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.stop_flag = False
        self.pause_flag = False
        self.search_results = []
        self.match_count = 0
        self.files_scanned = 0
        self.tree.delete(*self.tree.get_children())
        self.found_text.set("Found Keywords: 0")
        self.files_scanned_text.set("Scanned: 0/0")
        self.total_files_text.set("Total Files: 0")
        self.current_file_text.set("")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0%")
        # hide any existing toast
        self.toast_text.set("")
        self.toast_label.grid_remove()
        threading.Thread(target=self._search_worker, daemon=True).start()

    def cancel_search(self):
        """
        New flow:
        - Immediately pause worker by setting pause_flag True.
        - Disable cancel button to prevent re-entry.
        - Show confirmation dialog (blocking main thread).
        - If user confirms -> set stop_flag True and clear pause_flag (worker will wake & exit).
        - If user declines -> clear pause_flag to resume.
        """
        # Immediately pause the worker
        self.pause_flag = True
        # provide immediate UI feedback
        self.current_file_text.set("Pausing... awaiting confirmation")
        self.cancel_btn.configure(state="disabled")

        # Show confirmation dialog (this blocks the main thread; worker is paused)
        confirm = messagebox.askyesno("Confirm Cancel", "Are you sure you want to cancel the search?")
        if confirm:
            # user wants to cancel: instruct worker to stop
            self.stop_flag = True
            # unpause so worker can exit promptly
            self.pause_flag = False
            self.current_file_text.set("Cancelling...")
            # keep cancel btn disabled until worker finishes and resets
        else:
            # user chose not to cancel: resume worker
            self.pause_flag = False
            self.current_file_text.set("Resuming search...")
            # re-enable cancel button
            self.cancel_btn.configure(state="normal")

    def clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.search_results = []
        self.match_count = 0
        self.files_scanned = 0
        self.total_files = 0
        self.found_text.set("Found Keywords: 0")
        self.files_scanned_text.set("Scanned: 0/0")
        self.total_files_text.set("Total Files: 0")
        self.current_file_text.set("")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0%")
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        self.stop_flag = False
        self.pause_flag = False
        # hide toast if any
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
        """Show a small transient label (toast) with message for duration_ms milliseconds."""
        self.toast_text.set(message)
        self.toast_label.grid()  # show
        # schedule hide
        self.after(duration_ms, lambda: (self.toast_text.set(""), self.toast_label.grid_remove()))

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
            messagebox.showinfo("Export Complete", f"CSV exported: {out}")
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
            messagebox.showinfo("Export Complete", f"Excel exported: {out}")

    # ---------------- worker that glues UI to search_in_files ----------------
    def _search_worker(self):
        keyword = self.keyword_entry.get().strip()
        folder = self.folder_entry.get().strip()
        if not folder or not keyword:
            messagebox.showwarning("Input Error", "Please provide folder and keyword.")
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

        # progress_setter callable
        def progress_setter(frac):
            # update UI -- don't directly check stop_flag here
            try:
                self._safe_ui_update(progress=frac, files_scanned=self.files_scanned, found_count=self.match_count, current_file=self.current_file_text.get())
            except Exception:
                pass

        # stop_check callable for immediate cancellation
        def stop_check():
            return self.stop_flag

        # pause_check callable (returns True while paused)
        def pause_check():
            return self.pause_flag

        # call the search (blocking inside thread)
        results = search_in_files(
            folder, keyword, extensions, exact_flag, token_flag, case_flag,
            ignore_comments_flag, safeguard_limit_val, self.current_file_text,
            progress_setter, self.progress_text, self.found_text, self.files_scanned_text, self.total_files_text,
            stop_check=stop_check, pause_check=pause_check
        )

        # store and display results (respect safeguard)
        self.search_results = results
        self.tree.delete(*self.tree.get_children())
        display_limit = safeguard_limit_val
        for idx, row in enumerate(self.search_results[:display_limit], start=1):
            fp, ln, txt = row
            self.tree.insert("", "end", values=(idx, fp, ln, txt))

        if len(self.search_results) > display_limit:
            self.after(10, lambda: messagebox.showwarning("Safeguard Limit Reached",
                                                         f"{display_limit} results displayed in UI. Total matches: {len(self.search_results)}"))

        # final UI updates: show toast if cancelled, else normal completion
        if self.stop_flag:
            # show cancelled toast
            self._safe_ui_update(progress=1.0, files_scanned=len(self.search_results), found_count=len(self.search_results), current_file="Search cancelled.", total_files=len(self.search_results), final=True)
            # show transient toast
            self.show_toast("Search cancelled.", duration_ms=3000)
        else:
            self._safe_ui_update(progress=1.0, files_scanned=len(self.search_results), found_count=len(self.search_results),
                                 current_file="Search completed.", total_files=len(self.search_results), final=True)

        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        # reset flags after run
        self.stop_flag = False
        self.pause_flag = False

# ---------------------- Run App ----------------------
if __name__ == "__main__":
    if not PYGMENTS_AVAILABLE:
        msg = ("Pygments package not installed. Comment filtering may be slightly less accurate.\nInstall: pip install pygments\nContinue anyway?")
        if not messagebox.askyesno("Pygments not found", msg):
            raise SystemExit()
    app = SearchUtilityApp()
    app.mainloop()
