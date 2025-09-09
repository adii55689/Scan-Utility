import os
import re
import csv
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from datetime import datetime
import openpyxl

# ---------------- Globals ---------------- #
stop_search = False
all_results = []
MAX_DISPLAY = 5000  # Max rows to display in UI


# ---------------- Search Logic ---------------- #
def search_in_files(base_path, keyword, extensions, match_mode, case_sensitive,
                    safeguard_limit, tree, progress_bar, percent_label, count_var, status_var):
    global stop_search, all_results
    stop_search = False
    all_results = []

    file_list = []
    keyword_cmp = keyword if case_sensitive else keyword.lower()

    # Regex for per-token exact match
    if " " not in keyword_cmp:  # single token
        token_pattern = re.compile(rf"\b{re.escape(keyword_cmp)}\b",
                                   0 if case_sensitive else re.IGNORECASE)
    else:
        token_pattern = None

    # Collect files
    for root, _, files in os.walk(base_path):
        for file in files:
            if extensions == ["*"] or any(file.endswith(ext) for ext in extensions):
                file_list.append(os.path.join(root, file))

    total_files = len(file_list)
    match_count = 0

    # Clear old results
    for item in tree.get_children():
        tree.delete(item)

    for idx, file in enumerate(file_list, start=1):
        if stop_search:
            break

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, start=1):
                    if stop_search:
                        break
                    line_text = line.rstrip("\n")
                    line_cmp = line_text if case_sensitive else line_text.lower()

                    match = False
                    if match_mode == "exact":
                        if token_pattern:
                            if token_pattern.search(line_text):
                                match = True
                        else:
                            if keyword_cmp == line_cmp.strip():
                                match = True
                    else:  # contains
                        if keyword_cmp in line_cmp:
                            match = True

                    if match:
                        match_count += 1
                        all_results.append((file, i, line_text))

                        if match_count % 50 == 0:  # live counter update
                            count_var.set(f"Found Keywords: {match_count}")
        except Exception:
            continue

        # Progress bar update
        progress = (idx / max(1, total_files)) * 100
        progress_bar["value"] = progress
        percent_label.config(text=f"{progress:.1f}% ({idx}/{total_files} files)")

        progress_bar.update_idletasks()
        percent_label.update_idletasks()
        count_var.set(f"Found Keywords: {match_count}")

    status_var.set("Idle")

    if stop_search:
        messagebox.showinfo("Search Cancelled", f"Search cancelled.\nMatches Found: {match_count}")
    else:
        messagebox.showinfo("Search Completed", f"Search completed.\nMatches Found: {match_count}")

    # Safeguard confirmation
    if not stop_search and match_count > safeguard_limit:
        proceed = messagebox.askyesno("Large Result Set",
                                      f"Search found {match_count} matches.\n"
                                      f"Loading all results may freeze the UI.\n\n"
                                      f"Do you want to continue displaying results?")
        if not proceed:
            count_var.set(f"Found Keywords: {match_count} (results stored, not shown)")
            return

    # Load into Treeview
    for idx, row in enumerate(all_results[:MAX_DISPLAY], start=1):
        file, line_no, line_text = row
        tree.insert("", "end", values=(idx, file, line_no, line_text))

    if not stop_search and len(all_results) > MAX_DISPLAY:
        messagebox.showinfo("Results Truncated",
                            f"Found {match_count} matches, showing only first {MAX_DISPLAY}.")

    count_var.set(f"Found Keywords: {match_count}")


# ---------------- Export Logic ---------------- #
def export_csv():
    if not all_results:
        messagebox.showwarning("Export", "No results to export.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"search_results_{timestamp}.csv"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Line No", "Line Text"])
        writer.writerows(all_results)

    messagebox.showinfo("Export", f"Results exported:\n{csv_file}")


def export_excel():
    if not all_results:
        messagebox.showwarning("Export", "No results to export.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx_file = f"search_results_{timestamp}.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["File", "Line No", "Line Text"])
    for row in all_results:
        ws.append(row)
    wb.save(xlsx_file)

    messagebox.showinfo("Export", f"Results exported:\n{xlsx_file}")


# ---------------- Run Search Thread ---------------- #
def run_search_thread(base_path, keyword, extensions, match_mode, case_sensitive,
                      safeguard_limit, tree, progress_bar, percent_label, count_var, status_var):
    t = threading.Thread(target=search_in_files,
                         args=(base_path, keyword, extensions, match_mode,
                               case_sensitive, safeguard_limit,
                               tree, progress_bar, percent_label, count_var, status_var))
    t.daemon = True
    t.start()


# ---------------- UI ---------------- #
def build_ui():
    global stop_search
    root = tk.Tk()
    root.title("Local Repo Keyword Search")
    root.geometry("1000x700")

    # Frame
    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="both", expand=True)

    # Directory
    ttk.Label(frm, text="Directory:").grid(row=0, column=0, sticky="w")
    dir_entry = ttk.Entry(frm, width=65)
    dir_entry.grid(row=0, column=1, sticky="w")
    ttk.Button(frm, text="Browse", command=lambda: dir_entry.insert(0, filedialog.askdirectory())).grid(row=0, column=2, padx=5, sticky="w")

    # Keyword
    ttk.Label(frm, text="Keyword:").grid(row=1, column=0, sticky="w")
    keyword_entry = ttk.Entry(frm, width=50)
    keyword_entry.grid(row=1, column=1, sticky="w")

    # Match Mode (side by side)
    ttk.Label(frm, text="Match Mode:").grid(row=2, column=0, sticky="w")
    match_var = tk.StringVar(value="contains")
    ttk.Radiobutton(frm, text="Contains", variable=match_var, value="contains").grid(row=2, column=1, sticky="w")
    ttk.Radiobutton(frm, text="Exact", variable=match_var, value="exact").grid(row=2, column=1, sticky="e")

    # Case Sensitivity
    case_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text="Case Sensitive", variable=case_var).grid(row=3, column=1, sticky="w")

    # File Extensions
    ttk.Label(frm, text="File Extensions:").grid(row=4, column=0, sticky="w")
    ext_var = tk.StringVar(value="All")
    ext_dropdown = ttk.Combobox(frm, textvariable=ext_var,
                                values=["All", "Java/JSP", "Python", "Text", "Custom"], state="readonly")
    ext_dropdown.grid(row=4, column=1, sticky="w")

    custom_ext_label = ttk.Label(frm, text="Enter Comma separated extensions:")
    custom_ext_entry = ttk.Entry(frm, width=40)

    def on_ext_change(event=None):
        if ext_var.get() == "Custom":
            custom_ext_label.grid(row=5, column=0, sticky="w")
            custom_ext_entry.grid(row=5, column=1, sticky="w")
        else:
            custom_ext_label.grid_remove()
            custom_ext_entry.grid_remove()

    ext_dropdown.bind("<<ComboboxSelected>>", on_ext_change)

    # Safeguard Limit
    ttk.Label(frm, text="Safeguard Limit:").grid(row=6, column=0, sticky="w")
    safeguard_var = tk.IntVar(value=50000)
    safeguard_spin = ttk.Spinbox(frm, from_=1000, to=200000, increment=1000,
                                 textvariable=safeguard_var, width=10)
    safeguard_spin.grid(row=6, column=1, sticky="w")

    # Buttons Row
    btn_frame = tk.Frame(frm)
    btn_frame.grid(row=7, column=0, columnspan=3, pady=10)

    def run_search():
        global stop_search
        stop_search = False
        base_path = dir_entry.get().strip()
        keyword = keyword_entry.get().strip()
        if not base_path or not keyword:
            messagebox.showwarning("Input Error", "Please provide directory and keyword.")
            return

        # Extensions
        exts = ["*"]
        if ext_var.get() == "Java/JSP":
            exts = [".java", ".jsp"]
        elif ext_var.get() == "Python":
            exts = [".py"]
        elif ext_var.get() == "Text":
            exts = [".txt"]
        elif ext_var.get() == "Custom":
            raw = custom_ext_entry.get().strip()
            if not raw:
                messagebox.showwarning("Input Error", "Please enter at least one extension.")
                return
            exts = [e.strip() if e.strip().startswith(".") else "." + e.strip()
                    for e in raw.split(",") if e.strip()]

        run_search_thread(base_path, keyword, exts,
                          match_var.get(), case_var.get(),
                          safeguard_var.get(),
                          tree, progress_bar, percent_label, count_var, status_var)

    def cancel_search():
        global stop_search
        stop_search = True

    def clear_results():
        global all_results
        for item in tree.get_children():
            tree.delete(item)
        all_results = []
        count_var.set("Found Keywords: 0")
        progress_bar["value"] = 0
        percent_label.config(text="0%")

    # Unified Button Style
    button_style = {"width": 12, "height": 1}

    tk.Button(btn_frame, text="Run Search", command=run_search, bg="#4CAF50", fg="white", **button_style).grid(row=0, column=0, padx=5)
    tk.Button(btn_frame, text="Cancel Search", command=cancel_search, bg="#F44336", fg="white", **button_style).grid(row=0, column=1, padx=5)
    tk.Button(btn_frame, text="Export CSV", command=export_csv, bg="#2196F3", fg="white", **button_style).grid(row=0, column=2, padx=5)
    tk.Button(btn_frame, text="Export Excel", command=export_excel, bg="#3F51B5", fg="white", **button_style).grid(row=0, column=3, padx=5)
    tk.Button(btn_frame, text="Clear Results", command=clear_results, bg="#9E9E9E", fg="white", **button_style).grid(row=0, column=4, padx=5)

    # Progress Bar
    progress_bar = ttk.Progressbar(frm, orient="horizontal", length=600, mode="determinate")
    progress_bar.grid(row=8, column=0, columnspan=2, pady=5, sticky="w")
    percent_label = ttk.Label(frm, text="0%")
    percent_label.grid(row=8, column=2, sticky="w")

    # Results Table
    cols = ("#", "File", "Line No", "Line Text")
    tree = ttk.Treeview(frm, columns=cols, show="headings", height=15)
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width=250 if col == "Line Text" else 120)
    tree.grid(row=9, column=0, columnspan=3, sticky="nsew")

    scroll_y = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
    tree.configure(yscroll=scroll_y.set)
    scroll_y.grid(row=9, column=3, sticky="ns")

    # Keyword Count
    count_var = tk.StringVar(value="Found Keywords: 0")
    ttk.Label(frm, textvariable=count_var).grid(row=10, column=0, sticky="w")

    # Status Bar
    status_var = tk.StringVar(value="Idle")
    status_bar = ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w")
    status_bar.pack(side="bottom", fill="x")

    frm.rowconfigure(9, weight=1)
    frm.columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    build_ui()
