import os
import tempfile
import shutil
from flask import Flask, request, render_template, redirect, url_for, send_file, flash
import git
import csv
import openpyxl
from io import BytesIO

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"

# ---------------- Utility Functions ---------------- #
def search_in_repo(base_path, keyword, extensions):
    results = []
    file_list = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if extensions == ["*"] or any(file.endswith(ext) for ext in extensions):
                file_list.append(os.path.join(root, file))
    for file in file_list:
        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    line_text = line.strip()
                    if keyword in line_text.split():  # exact match
                        results.append((file, i, line_text))
        except Exception:
            continue
    return results

def export_csv(results):
    output = BytesIO()
    writer = csv.writer(output)
    writer.writerow(["File Path", "Line Number", "Line Content"])
    for row in results:
        writer.writerow(row)
    output.seek(0)
    return output

def export_excel(results):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Search Results"
    ws.append(["File Path", "Line Number", "Line Content"])
    for row in results:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

# ---------------- Routes ---------------- #
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        repo_url = request.form.get("repo_url").strip()
        auth_type = request.form.get("auth_type")
        keyword = request.form.get("keyword").strip()
        exts_choice = request.form.get("extension")
        extensions = ["*"] if exts_choice == "All" else [e.strip() for e in exts_choice.split(",")]

        if not repo_url or not keyword:
            flash("Please enter repository URL and keyword.")
            return redirect(url_for("index"))

        temp_dir = tempfile.mkdtemp()
        try:
            # ---------------- HTTPS Authentication ---------------- #
            if auth_type == "https":
                username = request.form.get("https_username").strip()
                password = request.form.get("https_password").strip()
                if not username or not password:
                    flash("Please provide HTTPS username and password/app password.")
                    return redirect(url_for("index"))
                url_parts = repo_url.replace("https://", "").split("/", 1)
                repo_url_auth = f"https://{username}:{password}@{url_parts[0]}/{url_parts[1]}"
                git.Repo.clone_from(repo_url_auth, temp_dir)

            # ---------------- SSH Authentication ---------------- #
            elif auth_type == "ssh":
                ssh_key_content = request.form.get("ssh_key").strip()
                if not ssh_key_content:
                    flash("Please paste your private SSH key.")
                    return redirect(url_for("index"))
                key_file = tempfile.NamedTemporaryFile(delete=False)
                key_file.write(ssh_key_content.encode())
                key_file.close()
                os.environ["GIT_SSH_COMMAND"] = f"ssh -i \"{key_file.name}\" -o StrictHostKeyChecking=no"
                git.Repo.clone_from(repo_url, temp_dir)
                os.unlink(key_file.name)
            else:
                flash("Invalid authentication type selected.")
                return redirect(url_for("index"))

            # ---------------- Search ---------------- #
            results = search_in_repo(temp_dir, keyword, extensions)
            shutil.rmtree(temp_dir)

            if not results:
                flash("No matches found.")
                return redirect(url_for("index"))

            # Store results temporarily in session-like global variable
            request.session = {"results": results}  # Simple workaround
            return render_template("results.html", results=results)

        except Exception as e:
            shutil.rmtree(temp_dir)
            flash(f"Error cloning/searching repo: {e}")
            return redirect(url_for("index"))

    return render_template("index.html")

@app.route("/export/<fmt>")
def export(fmt):
    results = getattr(request, "session", {}).get("results")
    if not results:
        flash("No results to export.")
        return redirect(url_for("index"))
    if fmt == "csv":
        output = export_csv(results)
        return send_file(output, as_attachment=True, download_name="search_results.csv", mimetype="text/csv")
    elif fmt == "excel":
        output = export_excel(results)
        return send_file(output, as_attachment=True, download_name="search_results.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        flash("Invalid export format.")
        return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
