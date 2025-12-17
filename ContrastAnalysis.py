import requests
import argparse
import sys
from datetime import datetime
from pathlib import Path

# ==============================
# 🔧 CONFIGURATION (MATCHES CURL)
# ==============================

CONTRAST_BASE_URL = "https://contrast.eclinicalworks.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"

# 👇 COPY DIRECTLY FROM WORKING CURL
AUTHORIZATION_HEADER = "Basic YOUR_BASE64_VALUE"
API_KEY = "YOUR_API_KEY"

TIMEOUT = 30  # VPN-safe

HEADERS = {
    "Accept": "application/json",
    "Authorization": AUTHORIZATION_HEADER,
    "API-Key": API_KEY
}

# Reuse connection (important for VPN)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ==============================
# 🔍 CONNECTION VALIDATION
# ==============================
def validate_connection():
    print("🔍 Validating Contrast connectivity...")
    url = f"{CONTRAST_BASE_URL}/{ORG_ID}/applications"

    try:
        r = SESSION.get(url, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        print("❌ Network error:", e)
        sys.exit(1)

    if r.status_code == 200:
        print("✅ Connection validated\n")
        return
    elif r.status_code == 401:
        print("❌ Unauthorized (check Base64 auth or API key)")
    elif r.status_code == 403:
        print("❌ Forbidden (permissions issue)")
    else:
        print(f"❌ Unexpected status {r.status_code}")
        print(r.text)

    sys.exit(1)

# ==============================
# 📥 TRACE INPUT
# ==============================
def load_trace_ids(traces, file):
    ids = set()
    if traces:
        ids.update(t.strip() for t in traces.split(",") if t.strip())
    if file:
        with open(file) as f:
            ids.update(line.strip() for line in f if line.strip())
    if not ids:
        raise ValueError("No trace IDs provided")
    return list(ids)

# ==============================
# 📡 FETCH TRACE
# ==============================
def fetch_trace(trace_id):
    url = f"{CONTRAST_BASE_URL}/{ORG_ID}/traces/{trace_id}"
    r = SESSION.get(url, timeout=TIMEOUT)

    if r.status_code != 200:
        raise Exception(f"Failed to fetch trace {trace_id} ({r.status_code})")

    return r.json()

# ==============================
# 🧠 LLM ANALYSIS (PLACEHOLDER)
# ==============================
def analyze_trace(trace):
    analysis_id = f"ANL-{trace['uuid'][:8].upper()}"

    src = trace.get("sourceLocation", {})
    snk = trace.get("sinkLocation", {})

    explanation = f"""
### Why this is Vulnerable
Untrusted input enters the application at
`{src.get('file')}:{src.get('line')}` and reaches a sensitive sink at
`{snk.get('file')}:{snk.get('line')}` without adequate validation.

### Exploitability
An attacker can supply crafted input to manipulate application behavior,
crossing a trust boundary and impacting confidentiality or integrity.

### Secure Fix
Validate input at the boundary, use framework-safe APIs, and avoid
passing user-controlled data directly to sensitive operations.

### Standards Mapping
- OWASP Top 10: A03 – Injection
- CWE: CWE-89 / CWE-79 (context dependent)
"""

    return analysis_id, explanation

# ==============================
# 📝 MARKDOWN REPORT
# ==============================
def generate_report(traces):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        "# 🔐 Contrast Automated Trace Analysis",
        "",
        f"Generated: {now}",
        "",
        "### Usage",
        "Use the **Analysis ID** when asking follow-up questions in Codex.",
        "",
        "---"
    ]

    for trace in traces:
        analysis_id, explanation = analyze_trace(trace)
        src = trace.get("sourceLocation", {})
        snk = trace.get("sinkLocation", {})

        md.extend([
            f"## 🆔 Analysis ID: {analysis_id}",
            f"**Trace ID:** {trace['uuid']}",
            f"**Application:** {trace['application']['name']}",
            f"**Severity:** {trace.get('severity')}",
            "",
            "### 📥 Input (Source)",
            f"- File: `{src.get('file')}`",
            f"- Line: `{src.get('line')}`",
            "",
            "### 📤 Output (Sink)",
            f"- File: `{snk.get('file')}`",
            f"- Line: `{snk.get('line')}`",
            "",
            "### 🧠 Security Analysis",
            explanation,
            "",
            "### 🧵 Stack Trace",
            "```",
            trace.get("stackTrace", "N/A"),
            "```",
            "",
            "---"
        ])

    return "\n".join(md)

# ==============================
# 🚀 MAIN
# ==============================
def main():
    parser = argparse.ArgumentParser(description="Contrast Trace Analyzer")
    parser.add_argument("--traces", help="Comma-separated Trace IDs")
    parser.add_argument("--file", help="File containing Trace IDs")
    parser.add_argument("--out", default="contrast_final_analysis.md")
    args = parser.parse_args()

    validate_connection()

    trace_ids = load_trace_ids(args.traces, args.file)

    traces = []
    for tid in trace_ids:
        print(f"🔹 Fetching trace {tid}")
        traces.append(fetch_trace(tid))

    report = generate_report(traces)
    Path(args.out).write_text(report, encoding="utf-8")

    print(f"\n✅ Analysis complete: {args.out}")

if __name__ == "__main__":
    main()
