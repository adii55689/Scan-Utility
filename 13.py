# RepoSearch — reference-themed UI + Summary donut + complete scanning + stable legend

import os
import sys
import time
import threading
import subprocess
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("customtkinter is required. Install with: pip install customtkinter")

try:
    import openpyxl
except ImportError:
    openpyxl = None

# ---------------- Theme (exact reference palette) ----------------
# Matches the sidebar, background, and accents in the provided image. [attached_image:1]
LIGHT_UI = {
    "bg": "#EAF0FF",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFF",
    "sidebar": "#FFB36B",
    "sidebar_dark": "#3B4DC8",
    "sidebar_text": "#FFFFFF",
    "text": "#1E2A45",
    "muted": "#5D6B7C",
    "border": "#E6ECF7",
    "chip_bg": "#F2F6FF",
    "primary": "#5B7CFF",
    "primary_hover": "#4A6AF7",
    "danger": "#FF6B6B",
    "warning": "#FFC75F",
    "success": "#41C29B",
    "accent": "#B56BFF",
    "accent2": "#FFB36B",
}  # [attached_image:1]

DARK_UI = {
    "bg": "#0F1218",
    "surface": "#12161F",
    "surface_alt": "#171C26",
    "sidebar": "#0E1117",
    "sidebar_dark": "#0B0F14",
    "sidebar_text": "#D7DCE2",
    "text": "#D7DCE2",
    "muted": "#8A93A0",
    "border": "#1F2633",
    "chip_bg": "#1A1F2B",
    "primary": "#4E61E8",
    "primary_hover": "#5B7CFF",
    "danger": "#FF6B6B",
    "warning": "#FFD166",
    "success": "#43C59E",
    "accent": "#7A5CFF",
    "accent2": "#FFB36B",
}  # [attached_image:1]

FONT_STACK = ("Inter", 11)
FONT_STACK_BOLD = ("Inter", 11, "bold")
FONT_MONO = ("Consolas", 10)

class Theme:
    def __init__(self, dark=False):
        self.dark = dark
        self.palette = DARK_UI if dark else LIGHT_UI
    def toggle(self):
        self.dark = not self.dark
        self.palette = DARK_UI if self.dark else LIGHT_UI

theme = Theme(dark=False)

def apply_ttk_theme():
    style = ttk.Style()
    try:
        style.theme_use("default")
    except Exception:
        pass
    p = theme.palette
    style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                    foreground=p["text"], font=("Inter", 10), rowheight=26, borderwidth=0)
    style.configure("Treeview.Heading", background=p["surface"], foreground=p["text"],
                    font=("Inter", 10, "bold"))
    style.map("Treeview", background=[("selected", p["chip_bg"])],
              foreground=[("selected", p["text"])])

def style_button(btn, kind="primary"):
    p = theme.palette
    if kind == "primary":
        btn.configure(corner_radius=18, fg_color=p["primary"], hover_color=p["primary_hover"],
                      text_color="#FFFFFF", font=FONT_STACK_BOLD, height=34)
    elif kind == "light":
        btn.configure(corner_radius=18, fg_color=p["chip_bg"], hover_color=p["border"],
                      text_color=p["text"], font=FONT_STACK_BOLD, height=34)
    elif kind == "danger":
        btn.configure(corner_radius=18, fg_color=p["danger"], hover_color=p["danger"],
                      text_color="#FFFFFF", font=FONT_STACK_BOLD, height=34)
    elif kind == "success":
        btn.configure(corner_radius=18, fg_color=p["success"], hover_color=p["success"],
                      text_color="#FFFFFF", font=FONT_STACK_BOLD, height=34)

def style_entry(widget):
    p = theme.palette
    widget.configure(corner_radius=12, fg_color=p["surface_alt"], border_color=p["border"],
                     border_width=1, text_color=p["text"], font=FONT_STACK, height=28)

def style_combo(widget):
    p = theme.palette
    widget.configure(corner_radius=12, fg_color=p["surface_alt"], button_color=p["primary"],
                     border_color=p["border"], text_color=p["text"], font=FONT_STACK,
                     dropdown_fg_color=p["surface"], dropdown_text_color=p["text"],
                     dropdown_hover_color=p["chip_bg"])

def chip(parent, text, color=None):
    p = theme.palette
    bg = p["chip_bg"] if not color else color
    return ctk.CTkLabel(parent, text=text, corner_radius=12, fg_color=bg,
                        text_color=p["text"], font=FONT_STACK_BOLD, padx=10, pady=6)

# ---------------- Utilities ----------------
APP_NAME = "RepoSearch"
MAX_HISTORY = 40  # [file:3]

def get_history_dir():
    base = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}_history")
    os.makedirs(base, exist_ok=True)
    return base  # [file:3]

def history_file_path():
    return os.path.join(get_history_dir(), "history.txt")  # [file:3]

def sanitize_excel(val):
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@"):
        s = "'" + s
    return s[:32760]  # [file:3]

def load_history():
    hist = {"scans": []}
    pth = history_file_path()
    if not os.path.exists(pth):
        return hist
    try:
        with open(pth, "r", encoding="utf-8") as f:
            block = {}
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    if block:
                        hist["scans"].append(block)
                    block = {}
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    block[k.strip()] = v.strip()
            if block:
                hist["scans"].append(block)
    except Exception:
        pass
    return hist  # [file:3]

def save_history(hist):
    pth = history_file_path()
    try:
        with open(pth, "w", encoding="utf-8") as f:
            for s in hist.get("scans", [])[:MAX_HISTORY]:
                for k, v in s.items():
                    f.write(f"{k}: {v}\n")
                f.write("\n")
    except Exception:
        pass  # [file:3]

def open_path(p):
    try:
        if os.name == "nt":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as e:
        messagebox.showerror("Open failed", str(e))  # [file:3]

def iter_files(root, extensions=None):
    if not extensions or "All" in extensions:
        exts = None
    else:
        exts = set(e.lower() for e in extensions)
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if exts:
                lf = fn.lower()
                if not any(lf.endswith(e) for e in exts):
                    continue
            yield os.path.join(dirpath, fn)  # [file:3]

def read_text_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()
    except Exception:
        return []  # [file:3]

# ---------------- Worker and search ----------------
def worker_search_file(
    fpath, primarykeyword, subscan_enabled, contextkw,
    bufferbefore, bufferafter, bufferboth,
    exactmatch, pertoken, casesensitive, ignorecomments, stopevent,
):
    if stopevent.is_set():
        return []
    lines = read_text_lines(fpath)
    results = []

    def norm(s): return s if casesensitive else s.lower()
    key = norm(primarykeyword)
    ctx = norm(contextkw) if contextkw else None

    def is_comment_line_text(hay):
        t = hay.lstrip()
        return (t.startswith("//") or t.startswith("#") or t.startswith("--")
                or t.startswith("/*") or t.startswith("*") or t.startswith("*/"))

    for idx, raw in enumerate(lines, start=1):
        if stopevent.is_set():
            break
        line = raw.rstrip("\n")
        hay = norm(line)

        if ignorecomments == "Yes" and is_comment_line_text(hay):
            continue

        if exactmatch:
            found = hay == key
        elif pertoken:
            found = key in hay.split()
        else:
            found = key in hay

        if not found:
            continue

        codeblock = ""
        if subscan_enabled:
            before_n = bufferbefore
            after_n = bufferafter

            window_lines = []
            j = idx - 2
            taken_before = 0
            while j >= 0 and taken_before < before_n:
                line_j = lines[j]
                hay_j = norm(line_j)
                if not (ignorecomments == "Yes" and is_comment_line_text(hay_j)):
                    window_lines.insert(0, line_j)
                    taken_before += 1
                j -= 1

            window_lines.append(lines[idx - 1])

            k = idx
            taken_after = 0
            while k < len(lines) and taken_after < after_n:
                line_k = lines[k]
                hay_k = norm(line_k)
                if not (ignorecomments == "Yes" and is_comment_line_text(hay_k)):
                    window_lines.append(line_k)
                    taken_after += 1
                k += 1

            window = "".join(window_lines)
            window_proc = norm(window)

            context_found = True
            if ctx:
                if exactmatch:
                    context_found = window_proc.strip() == ctx
                elif pertoken:
                    context_found = ctx in window_proc.split()
                else:
                    context_found = ctx in window_proc

            if not context_found:
                continue

            codeblock = window.rstrip()

        results.append((fpath, idx, line, codeblock))

    return results  # [file:3]

def search_in_files_parallel(
    folder, primarykeyword, extensions, exact, pertoken, case,
    ignorecomments, safeguard, currentfile_var, progresssetter, progressproxy,
    foundtext_var, filesproxy, totalfiles_var,
    subscan_enabled=False, contextkeyword="", bufferbefore=2, bufferafter=2, bufferboth=True, stopevent=None,
):
    filelist = list(iter_files(folder, extensions))
    total = len(filelist)
    scanned = 0
    files_with_match = 0
    results = []

    try:
        totalfiles_var.set(f"Total Files {total}")
    except Exception:
        pass

    maxworkers = max(2, min(32, (os.cpu_count() or 4)))
    last_update = time.time()

    def throttled_progress(frac):
        try:
            progressproxy.set(f"{frac*100:0.1f}")
        except Exception:
            pass
        try:
            progresssetter(frac)
        except Exception:
            pass

    if total == 0:
        throttled_progress(0.0)

    shared_stop = stopevent or threading.Event()
    with ThreadPoolExecutor(max_workers=maxworkers) as exe:
        future_map = {
            exe.submit(
                worker_search_file,
                fpath,
                primarykeyword,
                subscan_enabled,
                contextkeyword,
                bufferbefore,
                bufferafter,
                bufferboth,
                exact,
                pertoken,
                case,
                ignorecomments,
                shared_stop,
            ): fpath
            for fpath in filelist
        }

        for fut in as_completed(future_map):
            fpath = future_map[fut]

            if shared_stop.is_set():
                try:
                    _ = fut.result(timeout=0)
                except Exception:
                    pass
                continue

            try:
                matches = fut.result()
            except Exception:
                matches = []

            if matches:
                results.extend(matches)
                files_with_match += 1

            scanned += 1
            now = time.time()
            if now - last_update >= 0.20 or scanned == total:
                last_update = now
                frac = scanned / total if total else 1.0
                try:
                    currentfile_var.set(fpath)
                except Exception:
                    pass
                try:
                    filesproxy.set(f"Scanned {scanned}/{total}")
                except Exception:
                    pass
                try:
                    foundtext_var.set(f"Files with matches {files_with_match}")
                except Exception:
                    pass
                throttled_progress(frac)

            if safeguard and safeguard > 0 and scanned >= safeguard:
                break

    try:
        throttled_progress(1.0 if total else 0.0)
    except Exception:
        pass
    try:
        filesproxy.set(f"Scanned {scanned}/{total}")
    except Exception:
        pass
    try:
        foundtext_var.set(f"Files with matches {files_with_match}")
    except Exception:
        pass

    return results, scanned, total, files_with_match  # [file:3]

# --------------------- UI App ---------------------
class RepoSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("Light")
        self.apply_theme()
        self.title("RepoSearch - Rounded UI")
        self.geometry("1260x780")
        self.minsize(1080, 640)

        # State
        self.stopevent = threading.Event()
        self.searchresults = []
        self.history = load_history()
        self.auto_summary = tk.BooleanVar(value=True)

        # Live labels
        self.progress_text = tk.StringVar(value="0.0")
        self.files_scanned_text = tk.StringVar(value="Scanned 0/0")
        self.current_file_text = tk.StringVar(value="")
        self.total_files_text = tk.StringVar(value="Total Files 0")

        # Subscan options
        self.subscan_var = tk.BooleanVar(value=False)
        self.context_var = tk.StringVar(value="")
        self.buffer_mode_var = tk.StringVar(value="Both")
        self.buffer_single_var = tk.IntVar(value=2)
        self.exact_var = tk.BooleanVar(value=False)
        self.token_var = tk.BooleanVar(value=False)
        self.case_var = tk.BooleanVar(value=False)

        # Build UI
        self._build_sidebar()
        self._build_main()
    # Theme, dialogs, navigation
    def apply_theme(self):
        p = theme.palette
        self.configure(fg_color=p["bg"])
        apply_ttk_theme()

    def toggle_theme(self):
        theme.toggle()
        ctk.set_appearance_mode("Dark" if theme.dark else "Light")
        self.apply_theme()
        try:
            self.sidebar.configure(fg_color=theme.palette["sidebar"])
            self.main.configure(fg_color=theme.palette["bg"])
            self.code_text.configure(
                bg=theme.palette["surface_alt"],
                fg=theme.palette["text"],
                insertbackground=theme.palette["primary"],
            )
        except Exception:
            pass

    def show_shortcuts(self):
        messagebox.showinfo(
            "Shortcuts",
            "Ctrl+F Focus Keyword\nCtrl+L Focus Folder\nCtrl+R Run Search\nEsc Cancel\nCtrl+E Export CSV\nCtrl+Shift+E Export XLSX"
        )

    def show_about(self):
        messagebox.showinfo(
            "About RepoSearch",
            "RepoSearch — Themed code search with Subscan context, history, donut summary, and exports."
        )

    def show_search(self):
        self.search_card.lift()

    def show_summary(self):
        self.summary_card.lift()

    def browse_folder(self):
        d = filedialog.askdirectory(title="Select folder to scan")
        if d:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, d)

    def on_ext_change(self, _=None):
        sel = self.ext_cb.get()
        if sel == "Custom":
            self.custom_label.grid()
            self.custom_entry.grid()
        else:
            self.custom_label.grid_remove()
            self.custom_entry.grid_remove()
            self.custom_entry.delete(0, "end")

    def on_subscan_toggle(self):
        widgets = (self.dir_lbl, self.dir_cb, self.ctx_lbl, self.ctx_entry, self.buf_lbl, self.buf_entry)
        if self.subscan_var.get():
            self.dir_lbl.grid(row=0, column=1, sticky="e", padx=(8, 6))
            self.dir_cb.grid(row=0, column=2, sticky="ew", padx=(0, 10))
            self.ctx_lbl.grid(row=0, column=3, sticky="e", padx=(8, 6))
            self.ctx_entry.grid(row=0, column=4, sticky="ew", padx=(0, 8))
            self.on_direction_change(self.buffer_mode_var.get())
        else:
            for w in widgets:
                w.grid_remove()

    def on_direction_change(self, value):
        if value == "Both":
            self.buf_lbl.configure(text="Buffer")
        elif value == "After":
            self.buf_lbl.configure(text="After")
        else:
            self.buf_lbl.configure(text="Before")
        self.buf_lbl.grid(row=0, column=5, sticky="e", padx=(8, 6))
        self.buf_entry.grid(row=0, column=6, sticky="ew", padx=(0, 8))

    def _safe_ui_update(self, progress=None, filesscanned=None, foundcount=None, currentfile=None, totalfiles=None, final=False):
        def apply():
            if progress is not None:
                try:
                    self.progress_bar.set(progress)
                    self.progress_text.set(f"{progress*100:0.1f}")
                except Exception:
                    self.progress_text.set(f"{progress*100:0.1f}")
            if filesscanned is not None:
                try:
                    total = self.total_files_text.get().split()[-1]
                except Exception:
                    total = "?"
                self.files_scanned_text.set(f"Scanned {filesscanned}/{total}")
            if foundcount is not None:
                self.found_chip.configure(text=f"Found {foundcount}")
            if currentfile is not None:
                self.current_file_text.set(currentfile)
            if totalfiles is not None:
                self.total_files_text.set(f"Total Files {totalfiles}")
        self.after(1, apply)

    def start_search_thread(self):
        keyword = self.keyword_entry.get().strip()
        folder = self.folder_entry.get().strip()

        if not keyword:
            messagebox.showwarning("Input", "Enter a keyword to search.")
            return
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("Input", "Select a valid folder to search.")
            return

        sel = self.ext_cb.get()
        if sel == "All":
            extensions = ["All"]
        elif sel == "Custom":
            custom = self.custom_entry.get().strip()
            if not custom:
                messagebox.showwarning("Input", "Enter custom extensions, comma separated.")
                return
            extensions = [
                e.strip() if e.strip().startswith(".") else "." + e.strip()
                for e in custom.split(",")
                if e.strip()
            ]
        else:
            extensions = [sel]

        try:
            safeguard = int(self.safeguard_entry.get().strip() or "0")
        except Exception:
            safeguard = 0

        exact = bool(self.exact_var.get())
        pertoken = bool(self.token_var.get())
        case = bool(self.case_var.get())
        ignorecomments = self.ignore_cb.get()

        subscan_enabled = bool(self.subscan_var.get())
        context = self.context_var.get().strip()
        buf = max(0, int(self.buffer_single_var.get() or 0))
        dirv = self.buffer_mode_var.get()
        if dirv == "Both":
            bufferbefore = buf; bufferafter = buf; bufferboth = True
        elif dirv == "After":
            bufferbefore = 0; bufferafter = buf; bufferboth = True
        else:
            bufferbefore = buf; bufferafter = 0; bufferboth = True

        self.stopevent.clear()
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.code_text.configure(state="normal")
        self.code_text.delete("1.0", "end")
        self.searchresults = []
        self.current_file_text.set("")
        self.files_scanned_text.set("Scanned 0/0")
        self.total_files_text.set("Total Files 0")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0")
        self.found_chip.configure(text="Found 0")

        def progresssetter(frac):
            try:
                self.progress_bar.set(frac)
                self.progress_text.set(f"{frac*100:0.1f}")
            except Exception:
                pass

        start_ts = time.time()

        def run():
            results, scanned, total, files_with_match = search_in_files_parallel(
                folder,
                keyword,
                extensions,
                exact,
                pertoken,
                case,
                ignorecomments,
                safeguard,
                self.current_file_text,
                progresssetter,
                VarProxy(self, self.progress_text),
                tk.StringVar(),
                VarProxy(self, self.files_scanned_text),
                self.total_files_text,
                subscan_enabled=subscan_enabled,
                contextkeyword=context,
                bufferbefore=bufferbefore,
                bufferafter=bufferafter,
                bufferboth=bufferboth,
                stopevent=self.stopevent,
            )

            duration = time.time() - start_ts
            self.searchresults = results
            for idx, (fp, ln, txt, codeblock) in enumerate(results, start=1):
                self.tree.insert("", "end", values=(idx, fp, ln, txt))

            self._safe_ui_update(
                progress=1.0,
                filesscanned=scanned,
                foundcount=len(results),
                currentfile=("Search cancelled." if self.stopevent.is_set() else "Search completed."),
                totalfiles=total,
                final=True,
            )

            entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "keyword": keyword,
                "target": folder,
                "extensions": ",".join(extensions),
                "filesscanned": str(scanned),
                "totalfiles": str(total),
                "matchesfound": str(len(results)),
                "fileswithmatch": str(files_with_match),
                "durationseconds": str(round(duration, 2)),
                "status": "cancelled" if self.stopevent.is_set() else "success",
                "exportcsv": "",
                "exportxlsx": "",
                "sub_enabled": str(subscan_enabled),
                "context": context,
                "bufferbefore": str(bufferbefore),
                "bufferafter": str(bufferafter),
                "bufferboth": str(bufferboth),
            }

            hist = load_history()
            hist.setdefault("scans", [])
            hist["scans"].insert(0, entry)
            hist["scans"] = hist["scans"][:MAX_HISTORY]
            save_history(hist)
            self.history = hist
            self.refresh_summary_tree()

            if self.auto_summary.get():
                self.show_summary()
                self.update_donut_for_index(0)

        threading.Thread(target=run, daemon=True).start()

    # ---------------- Build UI (sidebar and main cards) ----------------
    def _build_sidebar(self):
        p = theme.palette
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=20, fg_color=p["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=16, pady=16)
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(20, weight=1)

        title = ctk.CTkLabel(self.sidebar, text="RepoSearch", font=("Inter", 15, "bold"), text_color=p["sidebar_text"])
        title.grid(row=0, column=0, padx=16, pady=(14, 10), sticky="w")

        self.btn_nav_search = ctk.CTkButton(self.sidebar, text="Search", command=self.show_search, width=190)
        style_button(self.btn_nav_search, "primary")
        self.btn_nav_search.grid(row=1, column=0, padx=16, pady=6, sticky="ew")

        self.btn_nav_summary = ctk.CTkButton(self.sidebar, text="Summary", command=self.show_summary, width=190)
        style_button(self.btn_nav_summary, "light")
        self.btn_nav_summary.grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.auto_summary_chk = ctk.CTkCheckBox(
            self.sidebar, text="Auto Summary", variable=self.auto_summary,
            checkbox_width=18, checkbox_height=18, fg_color=p["primary"], text_color=p["sidebar_text"]
        )
        self.auto_summary_chk.grid(row=3, column=0, padx=16, pady=(6, 6), sticky="w")

        div = ctk.CTkFrame(self.sidebar, height=1, fg_color=p["sidebar_dark"])
        div.grid(row=4, column=0, padx=16, pady=(8, 8), sticky="ew")

        explbl = ctk.CTkLabel(self.sidebar, text="Export", text_color=p["sidebar_text"], font=("Inter", 12, "bold"))
        explbl.grid(row=5, column=0, padx=16, pady=(2, 2), sticky="w")

        self.sb_export_csv = ctk.CTkButton(self.sidebar, text="Export CSV", command=self.export_csv, width=190)
        style_button(self.sb_export_csv, "success")
        self.sb_export_csv.grid(row=6, column=0, padx=16, pady=6, sticky="ew")

        self.sb_export_xlsx = ctk.CTkButton(self.sidebar, text="Export XLSX", command=self.export_excel, width=190)
        style_button(self.sb_export_xlsx, "primary")
        self.sb_export_xlsx.grid(row=7, column=0, padx=16, pady=6, sticky="ew")

        self.btn_shortcuts = ctk.CTkButton(self.sidebar, text="Shortcuts", command=self.show_shortcuts, width=190)
        style_button(self.btn_shortcuts, "light")
        self.btn_shortcuts.grid(row=18, column=0, padx=16, pady=(10, 6), sticky="ew")

        self.btn_about = ctk.CTkButton(self.sidebar, text="About", command=self.show_about, width=190)
        style_button(self.btn_about, "light")
        self.btn_about.grid(row=19, column=0, padx=16, pady=6, sticky="ew")

        self.btn_clear_hist = ctk.CTkButton(self.sidebar, text="Clear History", command=self.clear_history, width=190)
        style_button(self.btn_clear_hist, "danger")
        self.btn_clear_hist.grid(row=21, column=0, padx=16, pady=6, sticky="ew")

        tgl = ctk.CTkButton(self.sidebar, text="Toggle Theme", command=self.toggle_theme, width=190)
        style_button(tgl, "light")
        tgl.grid(row=22, column=0, padx=16, pady=(6, 14), sticky="ew")

    def _build_main(self):
        p = theme.palette
        self.main = ctk.CTkFrame(self, corner_radius=20, fg_color=p["bg"])
        self.main.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.search_card = ctk.CTkFrame(self.main, corner_radius=20, fg_color=p["bg"])
        self.summary_card = ctk.CTkFrame(self.main, corner_radius=20, fg_color=p["bg"])
        for card in (self.search_card, self.summary_card):
            card.grid(row=0, column=0, sticky="nsew")

        self._build_search_ui(self.search_card)
        self._build_summary_ui(self.summary_card)
        self.show_search()

    def _build_search_ui(self, parent):
        p = theme.palette

        top = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["surface"])
        top.pack(fill="x", padx=8, pady=(0, 8))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Keyword", width=90, anchor="e", text_color=p["text"], font=FONT_STACK_BOLD)\
            .grid(row=0, column=0, sticky="e", padx=(12, 6), pady=6)
        self.keyword_entry = ctk.CTkEntry(top, width=520, placeholder_text="Enter primary keyword")
        style_entry(self.keyword_entry)
        self.keyword_entry.grid(row=0, column=1, sticky="w", padx=6, pady=6)

        ctk.CTkLabel(top, text="Folder", width=90, anchor="e", text_color=p["text"], font=FONT_STACK_BOLD)\
            .grid(row=1, column=0, sticky="e", padx=(12, 6), pady=6)
        self.folder_entry = ctk.CTkEntry(top, width=520, placeholder_text="Select folder to search")
        style_entry(self.folder_entry)
        self.folder_entry.grid(row=1, column=1, sticky="w", padx=6, pady=6)
        self.browse_btn = ctk.CTkButton(top, text="Browse", width=96, command=self.browse_folder)
        style_button(self.browse_btn, "primary")
        self.browse_btn.grid(row=1, column=2, padx=(6, 12), pady=6)

        ctk.CTkLabel(top, text="File Type", width=90, anchor="e", text_color=p["text"], font=FONT_STACK_BOLD)\
            .grid(row=2, column=0, sticky="e", padx=(12, 6), pady=6)
        self.ext_cb = ctk.CTkComboBox(
            top, values=["All", ".java", ".jsp", ".py", ".cpp", ".html", ".js", "Custom"], width=220,
            command=self.on_ext_change
        )
        style_combo(self.ext_cb)
        self.ext_cb.set("All")
        self.ext_cb.grid(row=2, column=1, sticky="w", padx=6, pady=6)

        self.custom_label = ctk.CTkLabel(top, text="Custom Ext", width=90, anchor="e", text_color=p["text"], font=FONT_STACK_BOLD)
        self.custom_entry = ctk.CTkEntry(top, width=220, placeholder_text=".java,.jsp")
        style_entry(self.custom_entry)
        self.custom_label.grid(row=3, column=0, sticky="e", padx=(12, 6), pady=6)
        self.custom_entry.grid(row=3, column=1, sticky="w", padx=6, pady=6)
        self.custom_label.grid_remove()
        self.custom_entry.grid_remove()

        sub = ctk.CTkFrame(top, corner_radius=12, fg_color=p["surface_alt"])
        sub.grid(row=4, column=0, columnspan=3, sticky="ew", padx=(12, 12), pady=(8, 6))
        for c in (0, 1, 2, 3, 4, 5, 6):
            sub.grid_columnconfigure(c, weight=1)

        self.subscan_chk = ctk.CTkCheckBox(
            sub, text="Subscan", variable=self.subscan_var, command=self.on_subscan_toggle,
            checkbox_width=18, checkbox_height=18, fg_color=p["primary"], text_color=p["text"]
        )
        self.subscan_chk.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        self.dir_lbl = ctk.CTkLabel(sub, text="Search Directions", text_color=p["text"], font=FONT_STACK_BOLD)
        self.dir_cb = ctk.CTkComboBox(sub, values=["Both", "After", "Before"], width=150,
                                      variable=self.buffer_mode_var, command=self.on_direction_change)
        style_combo(self.dir_cb)

        self.ctx_lbl = ctk.CTkLabel(sub, text="Context", text_color=p["text"], font=FONT_STACK_BOLD)
        self.ctx_entry = ctk.CTkEntry(sub, width=240, textvariable=self.context_var, placeholder_text="e.g. userType")
        style_entry(self.ctx_entry)

        self.buf_lbl = ctk.CTkLabel(sub, text="Buffer", text_color=p["text"], font=FONT_STACK_BOLD)
        self.buf_entry = ctk.CTkEntry(sub, width=80, textvariable=self.buffer_single_var)
        style_entry(self.buf_entry)

        for w in (self.dir_lbl, self.dir_cb, self.ctx_lbl, self.ctx_entry, self.buf_lbl, self.buf_entry):
            w.grid_remove()

        opts = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["surface"])
        opts.pack(fill="x", padx=8, pady=(0, 8))
        opts.grid_columnconfigure(6, weight=1)

        self.exact_cb = ctk.CTkCheckBox(opts, text="Exact", variable=self.exact_var,
                                        checkbox_width=18, checkbox_height=18, fg_color=p["primary"], text_color=p["text"])
        self.token_cb = ctk.CTkCheckBox(opts, text="Per Token", variable=self.token_var,
                                        checkbox_width=18, checkbox_height=18, fg_color=p["primary"], text_color=p["text"])
        self.case_cb = ctk.CTkCheckBox(opts, text="Case Sensitive", variable=self.case_var,
                                       checkbox_width=18, checkbox_height=18, fg_color=p["primary"], text_color=p["text"])
        self.exact_cb.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.token_cb.grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self.case_cb.grid(row=0, column=2, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(opts, text="Ignore Comments", text_color=p["text"], font=FONT_STACK_BOLD)\
            .grid(row=0, column=3, padx=(16, 4), pady=6, sticky="e")
        self.ignore_cb = ctk.CTkComboBox(opts, values=["Yes", "No"], width=80)
        style_combo(self.ignore_cb)
        self.ignore_cb.set("Yes")
        self.ignore_cb.grid(row=0, column=4, padx=6, pady=6, sticky="w")

        ctk.CTkLabel(opts, text="Safeguard", text_color=p["text"], font=FONT_STACK_BOLD)\
            .grid(row=0, column=5, padx=(10, 4), pady=6, sticky="e")
        self.safeguard_entry = ctk.CTkEntry(opts, width=100)
        style_entry(self.safeguard_entry)
        self.safeguard_entry.insert(0, "0")
        self.safeguard_entry.grid(row=0, column=6, padx=6, pady=6, sticky="w")

        actions = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["surface"])
        actions.pack(fill="x", padx=8, pady=(0, 8))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        actions.grid_columnconfigure(2, weight=1)
        self.run_btn = ctk.CTkButton(actions, text="Run", command=self.start_search_thread, width=120)
        style_button(self.run_btn, "primary")
        self.run_btn.grid(row=0, column=0, padx=8, pady=8)
        self.cancel_btn = ctk.CTkButton(actions, text="Cancel", command=lambda: self.stopevent.set(), width=120)
        style_button(self.cancel_btn, "light")
        self.cancel_btn.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.clear_btn = ctk.CTkButton(actions, text="Clear", command=self.clear_results, width=120)
        style_button(self.clear_btn, "danger")
        self.clear_btn.grid(row=0, column=2, padx=8, pady=8)

        status = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["surface"])
        status.pack(fill="x", padx=8, pady=(0, 8))
        status.grid_columnconfigure(1, weight=1)
        self.progress_bar = ctk.CTkProgressBar(status, width=720)
        self.progress_bar.set(0.0)
        self.progress_bar.configure(progress_color=p["primary"], fg_color=p["chip_bg"], height=10, corner_radius=8)
        self.progress_bar.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkLabel(status, textvariable=self.progress_text, text_color=p["muted"], font=FONT_STACK)\
            .grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(status, textvariable=self.files_scanned_text, text_color=p["muted"], font=FONT_STACK)\
            .grid(row=1, column=0, sticky="w", padx=12)
        ctk.CTkLabel(status, textvariable=self.total_files_text, text_color=p["muted"], font=FONT_STACK)\
            .grid(row=1, column=1, sticky="w")
        ctk.CTkLabel(status, textvariable=self.current_file_text, wraplength=860, text_color=p["muted"], font=FONT_STACK)\
            .grid(row=2, column=0, columnspan=2, sticky="w", padx=12)
        self.found_chip = chip(status, "Found 0", color=p["chip_bg"])
        self.found_chip.grid(row=0, column=2, padx=10, pady=6, sticky="e")

        bottom = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["surface"])
        bottom.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(bottom, corner_radius=12, fg_color=p["surface"])
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 6), pady=8)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        cols = ("#", "File Path", "Line Number", "Line Content")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("#", width=50, anchor="center")
        self.tree.column("File Path", width=420, anchor="w")
        self.tree.column("Line Number", width=100, anchor="center")
        self.tree.column("Line Content", width=520, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_result_select)

        right = ctk.CTkFrame(bottom, corner_radius=12, fg_color=p["surface"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 8), pady=8)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="Code Block (context window)", anchor="w",
                     font=FONT_STACK_BOLD, text_color=p["text"]).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.code_text = tk.Text(
            right, wrap="none", height=18, padx=6, pady=6, font=FONT_MONO,
            bg=theme.palette["surface_alt"], fg=theme.palette["text"],
            insertbackground=theme.palette["primary"], relief="flat"
        )
        self.code_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        codev = ttk.Scrollbar(right, orient="vertical", command=self.code_text.yview)
        codeh = ttk.Scrollbar(right, orient="horizontal", command=self.code_text.xview)
        self.code_text.configure(yscrollcommand=codev.set, xscrollcommand=codeh.set)
        codev.grid(row=1, column=1, sticky="ns")
        codeh.grid(row=2, column=0, sticky="ew")

    def _build_summary_ui(self, parent):
        p = theme.palette
        wrap = ctk.CTkFrame(parent, corner_radius=16, fg_color=p["bg"])
        wrap.pack(fill="both", expand=True, padx=8, pady=8)

        top = ctk.CTkFrame(wrap, corner_radius=16, fg_color=p["surface"])
        top.pack(fill="x", padx=6, pady=(0, 8))
        ctk.CTkLabel(top, text="Recent Scans", font=("Inter", 13, "bold"), text_color=p["text"])\
            .grid(row=0, column=0, sticky="w", padx=12, pady=(10, 8))

        metrics = ctk.CTkFrame(wrap, corner_radius=16, fg_color=p["surface"])
        metrics.pack(fill="x", padx=6, pady=(0, 8))
        metrics.grid_columnconfigure(1, weight=1)

        self.donut_canvas = tk.Canvas(metrics, width=210, height=210, bg=p["surface"], highlightthickness=0)
        self.donut_canvas.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        # Persistent legend rows; updated in place to avoid CustomTkinter canvas deletion errors
        self.donut_legend = ctk.CTkFrame(metrics, corner_radius=12, fg_color=p["surface"])
        self.donut_legend.grid(row=0, column=1, sticky="w", padx=6, pady=12)
        self.legend_rows = []
        for _ in range(3):
            row = ctk.CTkFrame(self.donut_legend, corner_radius=8, fg_color=p["surface"])
            sw = ctk.CTkLabel(row, text="  ", width=16, height=16, corner_radius=8, fg_color=p["chip_bg"])
            sw.pack(side="left", padx=(0, 8))
            lbl = ctk.CTkLabel(row, text="", text_color=p["text"], font=FONT_STACK)
            lbl.pack(side="left")
            row.pack(anchor="w", pady=3)
            self.legend_rows.append((sw, lbl))

        frame = ctk.CTkFrame(wrap, corner_radius=16, fg_color=p["surface"])
        frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        frame.grid_columnconfigure(0, weight=1)

        scols = ("#", "Timestamp", "Keyword", "Folder", "Files", "Matches", "Duration", "Status")
        self.summary_tree = ttk.Treeview(frame, columns=scols, show="headings", height=10)
        for c in scols:
            self.summary_tree.heading(c, text=c)
            self.summary_tree.column(c, width=130, anchor="center")
        self.summary_tree.pack(fill="x", padx=8, pady=(8, 6))
        sv = ttk.Scrollbar(frame, orient="vertical", command=self.summary_tree.yview)
        self.summary_tree.configure(yscrollcommand=sv.set)
        sv.place(relx=0.985, rely=0.12, relheight=0.33)

        self.summary_detail = tk.Text(
            frame, height=8, wrap="word", state="disabled",
            bg=theme.palette["surface_alt"], fg=theme.palette["text"], relief="flat", padx=8, pady=8
        )
        self.summary_detail.pack(fill="both", expand=False, padx=8, pady=(6, 8))

        btns = ctk.CTkFrame(frame, corner_radius=12, fg_color=p["surface"])
        btns.pack(fill="x", padx=8, pady=6)
        b1 = ctk.CTkButton(btns, text="Rerun Selected", command=self.rerun_selected_summary)
        style_button(b1, "primary"); b1.pack(side="left", padx=6)
        b2 = ctk.CTkButton(btns, text="Open Export", command=self.open_selected_export)
        style_button(b2, "light"); b2.pack(side="left", padx=6)
        b3 = ctk.CTkButton(btns, text="Delete", command=self.delete_selected_summary)
        style_button(b3, "danger"); b3.pack(side="left", padx=6)
        b4 = ctk.CTkButton(btns, text="Clear All", command=self.clear_history)
        style_button(b4, "danger"); b4.pack(side="left", padx=6)

        self.refresh_summary_tree()
        self.summary_tree.bind("<<TreeviewSelect>>", self.on_summary_select)
        self.update_donut_for_index(0)

    # ---------- Donut helpers ----------
    def _legend_set(self, idx, color, text):
        sw, lbl = self.legend_rows[idx]
        sw.configure(fg_color=color)
        lbl.configure(text=text)

    def draw_donut(self, matches, nonmatches, remainder, title="Files matched"):
        p = theme.palette
        cv = self.donut_canvas
        cv.delete("all")

        W, H = int(cv["width"]), int(cv["height"])
        size = min(W, H) - 12
        pad = (min(W, H) - size) // 2
        x0 = pad; y0 = pad; x1 = x0 + size; y1 = y0 + size
        thickness = int(size * 0.32)

        total = max(matches + nonmatches + remainder, 0)
        if total == 0:
            total = 1; matches = nonmatches = 0; remainder = 1

        cv.create_oval(x0, y0, x1, y1, fill="", outline=p["chip_bg"], width=thickness)

        start = 0
        def seg(val, color):
            nonlocal start
            if val <= 0: return
            extent = 360 * (val / total)
            cv.create_arc(x0, y0, x1, y1, start=start, extent=extent, style="arc",
                          outline=color, width=thickness)
            start += extent

        seg(matches, p["primary"]); seg(nonmatches, p["accent2"]); seg(remainder, p["warning"])

        inner = thickness * 0.92
        cv.create_oval(x0 + inner, y0 + inner, x1 - inner, y1 - inner, fill=p["surface"], outline=p["surface"])

        cv.create_text((W // 2, H // 2 - 6), text=str(matches), fill=p["text"], font=("Inter", 20, "bold"))
        cv.create_text((W // 2, H // 2 + 16), text=title, fill=p["muted"], font=("Inter", 11))

        self._legend_set(0, p["primary"], f"Files matched: {matches}")
        self._legend_set(1, p["accent2"], f"Files without match: {nonmatches}")
        self._legend_set(2, p["warning"], f"Unscanned remainder: {remainder}")
    def update_donut_for_scan(self, s):
        try:
            scanned = int(s.get("filesscanned", "0") or 0)
            total = int(s.get("totalfiles", "0") or 0)
            files_with_match = int(s.get("fileswithmatch", "0") or 0)
        except Exception:
            scanned = total = files_with_match = 0
        nonmatches = max(scanned - files_with_match, 0)
        remainder = max(total - scanned, 0)
        self.draw_donut(files_with_match, nonmatches, remainder, title="Files matched")

    def update_donut_for_index(self, idx):
        scans = self.history.get("scans", [])
        if not scans:
            self.draw_donut(0, 0, 1, title="No data")
            return
        idx = max(0, min(idx, len(scans) - 1))
        self.update_donut_for_scan(scans[idx])

    # ---------- Result table selection ----------
    def on_result_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            return
        try:
            idx = int(vals[0]) - 1
        except Exception:
            return
        if not (0 <= idx < len(self.searchresults)):
            return
        _, _, _, codeblock = self.searchresults[idx]
        self.code_text.configure(state="normal")
        self.code_text.delete("1.0", "end")
        self.code_text.insert("1.0", codeblock)

    # ---------- Summary table actions ----------
    def refresh_summary_tree(self):
        for iid in self.summary_tree.get_children():
            self.summary_tree.delete(iid)
        scans = self.history.get("scans", [])
        for idx, s in enumerate(scans, start=1):
            ts = s.get("timestamp", "")
            kw = s.get("keyword", "")
            targ = s.get("target", "")
            files = f'{s.get("filesscanned","0")}/{s.get("totalfiles","0")}'
            matches = s.get("matchesfound", "0")
            dur = s.get("durationseconds", "0")
            st = s.get("status", "Unknown")
            self.summary_tree.insert("", "end", iid=str(idx - 1),
                                     values=(idx, ts, kw, targ, files, matches, dur, st))

    def on_summary_select(self, event=None):
        sel = self.summary_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        scans = self.history.get("scans", [])
        if not (0 <= idx < len(scans)):
            return
        s = scans[idx]
        self.summary_detail.configure(state="normal")
        self.summary_detail.delete("1.0", "end")

        def put(k, v): self.summary_detail.insert("end", f"{k}: {v}\n")

        put("Timestamp", s.get("timestamp", ""))
        put("Keyword", s.get("keyword", ""))
        put("Folder", s.get("target", ""))
        put("Extensions", s.get("extensions", ""))
        put("Files scanned", f'{s.get("filesscanned","0")}/{s.get("totalfiles","0")}')
        put("Line matches", s.get("matchesfound", "0"))
        put("Files with match", s.get("fileswithmatch", "0"))
        if s.get("sub_enabled", "False") == "True":
            put("Subscan", "Enabled")
            put("Context", s.get("context", ""))
            put("Before", s.get("bufferbefore", "0"))
            put("After", s.get("bufferafter", "0"))
        put("Duration", s.get("durationseconds", "0"))
        put("Status", s.get("status", ""))
        put("CSV", s.get("exportcsv", ""))
        put("XLSX", s.get("exportxlsx", ""))
        self.summary_detail.configure(state="disabled")

        self.update_donut_for_scan(s)

    def rerun_selected_summary(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an entry to rerun.")
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        scans = self.history.get("scans", [])
        if not (0 <= idx < len(scans)):
            return
        s = scans[idx]

        self.show_search()
        self.keyword_entry.delete(0, "end")
        self.keyword_entry.insert(0, s.get("keyword", ""))
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, s.get("target", ""))

        exts = [e.strip() for e in s.get("extensions", "").split(",") if e.strip()]
        if exts and exts != ["All"]:
            self.ext_cb.set("Custom")
            self.on_ext_change()
            self.custom_entry.delete(0, "end")
            self.custom_entry.insert(0, ",".join(exts))
        else:
            self.ext_cb.set("All")
            self.on_ext_change()

        if s.get("sub_enabled", "False") == "True":
            self.subscan_var.set(True)
            self.on_subscan_toggle()
            self.context_var.set(s.get("context", ""))
            before = int(s.get("bufferbefore", "0") or 0)
            after = int(s.get("bufferafter", "0") or 0)
            if before > 0 and after > 0:
                self.buffer_mode_var.set("Both")
                self.buffer_single_var.set(max(before, after))
            elif after > 0:
                self.buffer_mode_var.set("After")
                self.buffer_single_var.set(after)
            else:
                self.buffer_mode_var.set("Before")
                self.buffer_single_var.set(before)
            self.on_direction_change(self.buffer_mode_var.get())
        else:
            self.subscan_var.set(False)
            self.on_subscan_toggle()

        self.start_search_thread()

    def open_selected_export(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an entry.")
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        scans = self.history.get("scans", [])
        if not (0 <= idx < len(scans)):
            return
        s = scans[idx]
        csvp = s.get("exportcsv", "")
        xlsxp = s.get("exportxlsx", "")
        p = csvp if csvp and os.path.exists(csvp) else xlsxp
        if p and os.path.exists(p):
            open_path(p)
        else:
            messagebox.showinfo("Open", "No exported file found.")

    def delete_selected_summary(self):
        sel = self.summary_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an entry.")
            return
        if not messagebox.askyesno("Confirm", "Delete selected summary?"):
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        scans = self.history.get("scans", [])
        if not (0 <= idx < len(scans)):
            return
        try:
            del scans[idx]
            save_history({"scans": scans})
            self.history = load_history()
            self.refresh_summary_tree()
            self.update_donut_for_index(0)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def clear_history(self):
        if not messagebox.askyesno("Confirm", "Clear all history?"):
            return
        save_history({"scans": []})
        self.history = {"scans": []}
        self.refresh_summary_tree()
        self.summary_detail.configure(state="normal")
        self.summary_detail.delete("1.0", "end")
        self.summary_detail.configure(state="disabled")
        self.update_donut_for_index(0)

    # ---------- Export helpers ----------
    def prepare_export_rows(self, dedupe_by_filename: bool):
        if not self.searchresults:
            return []
        if not dedupe_by_filename:
            return [(i, fp, ln, txt, code) for i, (fp, ln, txt, code) in enumerate(self.searchresults, start=1)]
        seen = set()
        unique = []
        for fp, ln, txt, code in [(fp, ln, txt, code) for fp, ln, txt, code in self.searchresults]:
            if fp not in seen:
                seen.add(fp)
                unique.append((fp, ln, txt, code))
        return [(i, fp, ln, txt, code) for i, (fp, ln, txt, code) in enumerate(unique, start=1)]

    def prepare_summary_rows(self):
        hdr = ["Timestamp", "Keyword", "Folder", "Extensions", "Files Scanned", "Total Files",
               "Line Matches", "Files With Match", "Duration(s)", "Status", "CSV", "XLSX",
               "Subscan", "Context", "Before", "After", "Both"]
        rows = [hdr]
        for s in self.history.get("scans", []):
            rows.append([
                s.get("timestamp", ""),
                s.get("keyword", ""),
                s.get("target", ""),
                s.get("extensions", ""),
                s.get("filesscanned", ""),
                s.get("totalfiles", ""),
                s.get("matchesfound", ""),
                s.get("fileswithmatch", ""),
                s.get("durationseconds", ""),
                s.get("status", ""),
                s.get("exportcsv", ""),
                s.get("exportxlsx", ""),
                s.get("sub_enabled", ""),
                s.get("context", ""),
                s.get("bufferbefore", ""),
                s.get("bufferafter", ""),
                s.get("bufferboth", ""),
            ])
        return rows

    def export_csv(self):
        if not self.searchresults:
            messagebox.showwarning("No Results", "No results to export.")
            return
        resp = messagebox.askyesnocancel(
            "Export CSV",
            "Remove duplicate files (export unique filenames only)?\nYes = unique files, No = all results, Cancel = abort",
        )
        if resp is None:
            return
        dedupe = bool(resp)

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        out = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"search_{ts}.csv",
            title="Save results as CSV",
        )
        if not out:
            return

        try:
            rows = self.prepare_export_rows(dedupe_by_filename=dedupe)
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                w.writerow(["Index", "File Path", "Line Number", "Line Content", "Code Block"])
                for r in rows:
                    w.writerow(r)
            messagebox.showinfo("Exported", f"CSV exported:\n{out}")

            hist = load_history()
            if hist.get("scans"):
                hist["scans"][0]["exportcsv"] = out
                save_history(hist)
                self.history = hist
                self.refresh_summary_tree()
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def export_excel(self):
        if not self.searchresults:
            messagebox.showwarning("No Results", "No results to export.")
            return
        if openpyxl is None:
            messagebox.showerror("Export error", "openpyxl is not installed. Install with: pip install openpyxl")
            return

        resp = messagebox.askyesnocancel(
            "Export Excel",
            "Remove duplicate files (export unique filenames only)?\nYes = unique files, No = all results, Cancel = abort",
        )
        if resp is None:
            return
        dedupe = bool(resp)

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        out = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=f"search_{ts}.xlsx",
            title="Save results as Excel",
        )
        if not out:
            return

        try:
            rows = self.prepare_export_rows(dedupe_by_filename=dedupe)
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Results"
            ws.append(["Index", "File Path", "Line Number", "Line Content", "Code Block"])
            for r in rows:
                ws.append([r[0], sanitize_excel(r[1]), sanitize_excel(r[2]), sanitize_excel(r[3]), sanitize_excel(r[4])])

            ws2 = wb.create_sheet("Summary")
            for row in self.prepare_summary_rows():
                ws2.append([sanitize_excel(c) for c in row])

            wb.save(out)
            messagebox.showinfo("Exported", f"Excel exported:\n{out}")

            hist = load_history()
            if hist.get("scans"):
                hist["scans"][0]["exportxlsx"] = out
                save_history(hist)
                self.history = hist
                self.refresh_summary_tree()
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def clear_results(self):
        self.stopevent.set()
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.code_text.configure(state="normal")
        self.code_text.delete("1.0", "end")
        self.searchresults = []
        self.current_file_text.set("")
        self.files_scanned_text.set("Scanned 0/0")
        self.total_files_text.set("Total Files 0")
        self.progress_bar.set(0.0)
        self.progress_text.set("0.0")
        self.found_chip.configure(text="Found 0")

# ---------- Throttled variable proxy ----------
class VarProxy:
    def __init__(self, app, tkvar, interval_ms: int = 120):
        self.app = app
        self.var = tkvar
        self.interval = interval_ms
        self.last = None
        self.pending = None
        self.lock = threading.Lock()

    def set(self, text):
        with self.lock:
            self.pending = text
        self.app.after(self.interval, self.flush)

    def flush(self):
        with self.lock:
            if self.pending is None:
                return
            text = self.pending
            self.pending = None
        try:
            if text != self.last:
                self.var.set(text)
                self.last = text
        except Exception:
            pass


if __name__ == "__main__":
    app = RepoSearchApp()
    app.bind("<Control-f>", lambda e: app.keyword_entry.focus_set())
    app.bind("<Control-l>", lambda e: app.folder_entry.focus_set())
    app.bind("<Control-r>", lambda e: app.start_search_thread())
    app.bind("<Escape>", lambda e: app.stopevent.set())
    app.bind("<Control-e>", lambda e: app.export_csv())
    app.bind("<Control-E>", lambda e: app.export_excel())
    app.mainloop()

