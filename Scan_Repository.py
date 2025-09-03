import os
import sys
import subprocess
import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tempfile

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

ensure_dependency("git", "3.1.31")  # avoid numpy dependency
ensure_dependency("openpyxl")
import git
from git.remote import RemoteProgress

# ---------------- Export Functions ---------------- #
def export_csv(results, output_file="search_results.csv"):
    if not results:
        messagebox.showwarning("No Results", "No results found to export.")
        return
    with open(output_file, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["#", "Source", "File Path", "Line Number", "Line Content"])
        for idx, row in enumerate(results, start=1):
            writer.writerow([idx] + [str(x) for x in row])
    messagebox.showinfo("Export Complete", f"Results exported to {os.path.abspath(output_file)}")

def export_excel(results, output_file="search_results.xlsx"):
    if not results:
        messagebox.showwarning("No Results", "No results found to export.")
        return
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Search Results"
    ws.append(["#", "Source", "File Path", "Line Number", "Line Content"])
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
def search_in_files(base_path, keyword, extensions, source, tree, progress_bar, count_var):
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
                    line_text = str(line.strip())
                    # exact and case-sensitive match
                    if keyword in line_text.split():
                        match_count += 1
                        results.append((source, file, i, line_text))
                        # bold only keyword
                        display_line = line_text.replace(keyword, f"{keyword}")
                        tree.insert("", "end", values=(len(results), source, file, i, display_line), tags=("highlight",))
        except Exception:
            continue
        progress = (idx / max(1, total_files)) * 100
        progress_bar["value"] = progress
        progress_bar.update_idletasks()
    count_var.set(f"Found Keywords: {match_count}")
    return results

# ---------------- UI Logic ---------------- #
def browse_local_folder():
    folder = filedialog.askdirectory(title="Select Local Folder")
    if folder:
        local_path_entry.delete(0, "end")
        local_path_entry.insert(0, folder)

def run_search():
    keyword = keyword_entry.get().strip()
    mode = mode_var.get()
    exts_choice = extension_var.get()
    if not keyword:
        messagebox.showwarning("Input Error", "Please enter a keyword to search.")
        return
    if exts_choice == "All":
        extensions = ["*"]
    elif exts_choice == "Custom":
        custom_exts = custom_extension_entry.get().strip()
        if not custom_exts:
            messagebox.showwarning("Input Error", "Enter at least one extension.")
            return
        extensions = [e.strip() for e in custom_exts.split(",")]
    else:
        extensions = [exts_choice]
    for item in results_tree.get_children():
        results_tree.delete(item)
    progress_bar["value"] = 0
    count_var.set("Found Keywords: 0")
    results = []

    if mode == "Local":
        folder = local_path_entry.get().strip()
        if not folder:
            messagebox.showwarning("Input Error", "Please select a local folder.")
            return
        results.extend(search_in_files(folder, keyword, extensions, "Local", results_tree, progress_bar, count_var))

    elif mode == "Bitbucket":
        clone_url = bitbucket_url_entry.get().strip()
        if not clone_url:
            messagebox.showwarning("Input Error", "Please provide Bitbucket Clone Repository URL.")
            return
        temp_dir = tempfile.mkdtemp()
        repo_name = os.path.basename(clone_url).replace(".git", "")
        try:
            status_label.config(text=f"Cloning {repo_name}...", foreground="blue")
            git.Repo.clone_from(clone_url, temp_dir, progress=CloneProgress(progress_bar, status_label))
            status_label.config(text=f"{repo_name} cloned successfully", foreground="green")
            results.extend(search_in_files(temp_dir, keyword, extensions, "Bitbucket", results_tree, progress_bar, count_var))
            if messagebox.askyesno("Cleanup", "Do you want to delete the cloned repository?"):
                import shutil
                shutil.rmtree(temp_dir)
        except Exception as e:
            status_label.config(text=f"Failed to clone {repo_name}", foreground="red")
            messagebox.showerror("Clone Error", f"Failed to clone Bitbucket repo: {e}")
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
root.title("Repository Keyword Search Utility")
root.geometry("1400x900")

padx_val = 10
pady_val = 5

# Keyword
tk.Label(root, text="Keyword to Search:").grid(row=0, column=0, sticky="e", padx=padx_val, pady=pady_val)
keyword_entry = tk.Entry(root, width=60)
keyword_entry.grid(row=0, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Mode
tk.Label(root, text="Search Mode:").grid(row=1, column=0, sticky="e", padx=padx_val, pady=pady_val)
mode_var = tk.StringVar(value="Local")
mode_dropdown = ttk.Combobox(root, textvariable=mode_var, values=["Local", "Bitbucket"], state="readonly", width=58)
mode_dropdown.grid(row=1, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Extension
tk.Label(root, text="File Extension:").grid(row=2, column=0, sticky="e", padx=padx_val, pady=pady_val)
extension_var = tk.StringVar(value="All")
extension_dropdown = ttk.Combobox(root, textvariable=extension_var,
                                  values=["All", ".py", ".java", ".js", ".txt", "Custom"], state="readonly", width=55)
extension_dropdown.grid(row=2, column=1, sticky="w", padx=padx_val, pady=pady_val)

custom_extension_label = tk.Label(root, text="Add comma separated extension:")
custom_extension_entry = tk.Entry(root, width=40)
def show_custom_entry(event):
    if extension_var.get() == "Custom":
        custom_extension_label.grid(row=3, column=0, sticky="e", padx=padx_val, pady=pady_val)
        custom_extension_entry.grid(row=3, column=1, sticky="w", padx=padx_val, pady=pady_val)
    else:
        custom_extension_label.grid_forget()
        custom_extension_entry.grid_forget()
extension_dropdown.bind("<<ComboboxSelected>>", show_custom_entry)

# Local folder
tk.Label(root, text="Local Folder:").grid(row=4, column=0, sticky="e", padx=padx_val, pady=pady_val)
local_path_entry = tk.Entry(root, width=55)
local_path_entry.grid(row=4, column=1, sticky="w", padx=(0,5), pady=pady_val)
tk.Button(root, text="Browse", command=browse_local_folder, width=12).grid(row=4, column=2, sticky="w", padx=(0, padx_val), pady=pady_val)

# Bitbucket URL
tk.Label(root, text="Bitbucket Clone Repository URL:").grid(row=5, column=0, sticky="e", padx=padx_val, pady=pady_val)
bitbucket_url_entry = tk.Entry(root, width=60)
bitbucket_url_entry.grid(row=5, column=1, sticky="w", padx=padx_val, pady=pady_val)

# Status Label
status_label = tk.Label(root, text="Repository Status: Not started", foreground="black")
status_label.grid(row=6, column=0, columnspan=3, sticky="w", padx=padx_val, pady=pady_val)

# Buttons
tk.Button(root, text="Run Search", command=run_search, bg="lightblue", width=15).grid(row=7, column=0, padx=padx_val, pady=pady_val)
tk.Button(root, text="Export CSV", command=lambda: export_results("csv"), bg="lightgreen", width=15).grid(row=7, column=1, padx=padx_val, pady=pady_val)
tk.Button(root, text="Export Excel", command=lambda: export_results("excel"), bg="lightgreen", width=15).grid(row=7, column=2, padx=padx_val, pady=pady_val)

# Keyword count
count_var = tk.StringVar(value="Found Keywords: 0")
tk.Label(root, textvariable=count_var, font=("Arial", 10, "bold")).grid(row=8, column=0, columnspan=3, sticky="w", padx=padx_val, pady=pady_val)

# Progress Bar
progress_bar = ttk.Progressbar(root, orient="horizontal", length=800, mode="determinate")
progress_bar.grid(row=9, column=0, columnspan=3, padx=padx_val, pady=pady_val)

# Results Treeview with scrollbars
results_frame = tk.Frame(root)
results_frame.grid(row=10, column=0, columnspan=3, sticky="nsew", padx=padx_val, pady=pady_val)

columns = ("#", "Source", "File Path", "Line Number", "Line Content")
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

# Bold keyword tag (applied only to keyword in line content)
results_tree.tag_configure("highlight", font=("Arial", 10, "bold"))

root.mainloop()
