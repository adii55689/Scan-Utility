import os
import sys
import subprocess
import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tempfile
import urllib.parse
import git
from git.remote import RemoteProgress

# ---------------- Dependency Installer ---------------- #
def ensure_dependency(package, version=None):
    try:
        __import__(package)
        return True
    except ImportError:
        try:
            if version:
                subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}"])
            else:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            return True
        except Exception as e:
            messagebox.showerror("Dependency Install Failed", f"Failed to install {package}: {e}")
            return False

ensure_dependency("gitpython")
ensure_dependency("openpyxl")
import openpyxl

# ---------------- Export Functions ---------------- #
def export_csv(results, output_file="search_results.csv"):
    if not results:
        messagebox.showwarning("No Results", "No results found to export.")
        return
    with open(output_file, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["#", "File Path", "Line Number", "Line Content"])
        for idx, row in enumerate(results, start=1):
            writer.writerow([idx] + [str(x) for x in row])
    messagebox.showinfo("Export Complete", f"Results exported to {os.path.abspath(output_file)}")

def export_excel(results, output_file="search_results.xlsx"):
    if not results:
        messagebox.showwarning("No Results", "No results found to export.")
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Search Results"
    ws.append(["#", "File Path", "Line Number", "Line Content"])
    for idx, row in enumerate(results, start=1):
        ws.append([idx] + [str(x) for x in row])
    wb.save(output_file)
    messagebox.showinfo("Export Complete", f"Results exported to {os.path.abspath(output_file)}")

# ---------------- Clone Progress ---------------- #
class CloneProgress(RemoteProgress):
    def __init__(self, progress_bar, status_label):
        super().__init__()
        self.progress_bar = progress_bar
        self.status_label = status_label

    def update(self, op_code, cur_count, max_count=None, message=''):
        if max_count:
            percent = (cur_count / max_count) * 100
            self.progress_bar["value"] = percent
            self.progress_bar.update_idletasks()

# ---------------- Search Logic ---------------- #
def search_in_files(base_path, keyword, extensions, tree, progress_bar, count_var):
    results = []
    file_list = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if extensions == ["*"] or any(file.endswith(ext) for ext in extensions):
                file_list.append(os.path.join(root, file))
    total_files = len(file_list)
    match_count = 0
    for idx, file in enumerate(file_list, start=1):
        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, start=1):
                    line_text = line.strip()
                    # Case-insensitive exact match
                    if any(word.lower() == keyword.lower() for word in line_text.split()):
                        match_count += 1
                        results.append((file, i, line_text))
                        tree.insert("", "end", values=(len(results), file, i, line_text), tags=("highlight",))
        except Exception:
            continue
        progress = (idx / max(1, total_files)) * 100
        progress_bar["value"] = progress
        progress_bar.update_idletasks()
    count_var.set(f"Found Keywords: {match_count}")
    return results

# ---------------- Run Search ---------------- #
def run_search():
    repo_url = repo_url_entry.get().strip()
    username = username_entry.get().strip()
    token = token_entry.get().strip()
    keyword = keyword_entry.get().strip()
    exts_choice = extension_var.get().strip()

    if not repo_url or not username or not token or not keyword:
        messagebox.showwarning("Input Error", "Please provide all required fields.")
        return

    extensions = ["*"] if exts_choice.lower() == "all" else [e.strip() for e in exts_choice.split(",")]

    for item in results_tree.get_children():
        results_tree.delete(item)
    progress_bar["value"] = 0
    count_var.set("Found Keywords: 0")
    results = []

    temp_dir = tempfile.mkdtemp()
    try:
        token_encoded = urllib.parse.quote(token)
        url_parts = repo_url.replace("https://", "").split("/", 1)
        repo_url_auth = f"https://{username}:{token_encoded}@{url_parts[0]}/{url_parts[1]}"

        status_label.config(text="Cloning repository...", foreground="blue")
        root.update_idletasks()
        git.Repo.clone_from(repo_url_auth, temp_dir, progress=CloneProgress(progress_bar, status_label))
        status_label.config(text="Repository cloned successfully", foreground="green")

        results.extend(search_in_files(temp_dir, keyword, extensions, results_tree, progress_bar, count_var))

        if messagebox.askyesno("Cleanup", "Do you want to delete the cloned repository?"):
            import shutil
            shutil.rmtree(temp_dir)

    except Exception as e:
        status_label.config(text="Failed to clone repository", foreground="red")
        messagebox.showerror("Clone Error", f"Failed to clone repository: {e}")
        return

    run_search.results = results
    messagebox.showinfo("Search Complete", f"Found {len(results)} matches.")

def export_results(fmt):
    if not hasattr(run_search, "results") or not run_search.results:
        messagebox.showwarning("No Results", "No results to export.")
        return
    if fmt == "csv":
        export_csv(run_search.results)
    elif fmt == "excel":
        export_excel(run_search.results)

# ---------------- Build UI ---------------- #
root = tk.Tk()
root.title("Bitbucket Keyword Search Utility")
root.geometry("1400x900")

padx_val = 10
pady_val = 5

# Repo URL
tk.Label(root, text="Bitbucket Repository HTTPS URL:").grid(row=0, column=0, sticky="e", padx=padx_val, pady=pady_val)
repo_url_entry = tk.Entry(root, width=60)
repo_url_entry.grid(row=0, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Username
tk.Label(root, text="Bitbucket Username:").grid(row=1, column=0, sticky="e", padx=padx_val, pady=pady_val)
username_entry = tk.Entry(root, width=60)
username_entry.grid(row=1, column=1, sticky="w", padx=padx_val, pady=pady_val)

# HTTP Access Token
tk.Label(root, text="HTTP Access Token:").grid(row=2, column=0, sticky="e", padx=padx_val, pady=pady_val)
token_entry = tk.Entry(root, width=60, show="*")
token_entry.grid(row=2, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Keyword
tk.Label(root, text="Keyword to Search:").grid(row=3, column=0, sticky="e", padx=padx_val, pady=pady_val)
keyword_entry = tk.Entry(root, width=60)
keyword_entry.grid(row=3, column=1, sticky="w", padx=padx_val, pady=pady_val)

# File Extensions
tk.Label(root, text="File Extensions (comma separated or All):").grid(row=4, column=0, sticky="e", padx=padx_val, pady=pady_val)
extension_var = tk.StringVar(value="All")
extension_entry = tk.Entry(root, textvariable=extension_var, width=60)
extension_entry.grid(row=4, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Buttons
tk.Button(root, text="Run Search", command=run_search, bg="lightblue", width=15).grid(row=5, column=0, padx=padx_val, pady=pady_val)
tk.Button(root, text="Export CSV", command=lambda: export_results("csv"), bg="lightgreen", width=15).grid(row=5, column=1, padx=padx_val, pady=pady_val)
tk.Button(root, text="Export Excel", command=lambda: export_results("excel"), bg="lightgreen", width=15).grid(row=5, column=2, padx=padx_val, pady=pady_val)

# Status Label
status_label = tk.Label(root, text="Repository Status: Not started", foreground="black")
status_label.grid(row=6, column=0, columnspan=3, sticky="w", padx=padx_val, pady=pady_val)

# Keyword count
count_var = tk.StringVar(value="Found Keywords: 0")
tk.Label(root, textvariable=count_var, font=("Arial", 10, "bold")).grid(row=7, column=0, columnspan=3, sticky="w", padx=padx_val, pady=pady_val)

# Progress Bar
progress_bar = ttk.Progressbar(root, orient="horizontal", length=800, mode="determinate")
progress_bar.grid(row=8, column=0, columnspan=3, padx=padx_val, pady=pady_val)

# Results Treeview
results_frame = tk.Frame(root)
results_frame.grid(row=9, column=0, columnspan=3, sticky="nsew", padx=padx_val, pady=pady_val)

columns = ("#", "File Path", "Line Number", "Line Content")
results_tree = ttk.Treeview(results_frame, columns=columns, show="headings")
for col in columns:
    results_tree.heading(col, text=col)
    results_tree.column(col, anchor="center" if col in ["#", "Line Number"] else "w", width=200, stretch=True)
results_tree.column("Line Content", width=600, anchor="w", stretch=True)

vsb = ttk.Scrollbar(results_frame, orient="vertical", command=results_tree.yview)
hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=results_tree.xview)
results_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

results_tree.grid(row=0, column=0, sticky="nsew")
vsb.grid(row=0, column=1, sticky="ns")
hsb.grid(row=1, column=0, sticky="ew")
results_frame.grid_rowconfigure(0, weight=1)
results_frame.grid_columnconfigure(0, weight=1)

results_tree.tag_configure("highlight", font=("Arial", 10, "bold"))

root.mainloop()
