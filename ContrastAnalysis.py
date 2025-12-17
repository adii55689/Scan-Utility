import requests
import argparse
from datetime import datetime
from pathlib import Path
import sys
import hashlib

# =====================================================
# CONFIGURATION (UPDATE THESE)
# =====================================================
CONTRAST_BASE_URL = "https://contrast.eclinicalworks.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"

# 👇 COPY THIS DIRECTLY FROM CONTRAST (NO CHANGES)
AUTHORIZATION_HEADER = "Basic <PASTE_BASE64_VALUE_HERE>"
API_KEY = "YOUR_API_KEY"

TIMEOUT = 30  # VPN-safe timeout

# =====================================================
# SESSION SETUP
# =====================================================
HEADERS = {
    "Authorization": AUTHORIZATION_HEADER,
    "API-Key": API_KEY,
    "Accept": "application/json"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# =====================================================
# CONNECTION VALIDATION
# =====================================================
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

    if r.status_code == 401:
        print("❌ 401 Unauthorized – check Authorization or API key")
    elif r.status_code == 403:
        print("❌ 403 Forbidden – check permissions")
    else:
        print(f"❌ Unexpected response {r.status_code}")
        print(r.text)

    sys.exit(1)

# =====================================================
# TRACE ID INPUT
# =====================================================
def load_trace_ids(traces, file):
    ids = set()
    if traces:
        ids.update(t.strip() for t in traces.split(",") if t.strip())
    if file:
        ids.update(line.strip() for line in open(file) if line.strip())
    if not ids:
        raise ValueError("No Trace IDs provided")
    return list(ids)

# =====================================================
# FETCH TRACE
# =====================================================
def fetch_trace(trace_id):
    url = f"{CONTRAST_BASE_URL}/{ORG_ID}/traces/{trace_id}"
    r = SESSION.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        raise Exception(f"Failed to fetch trace {trace_id} ({r.status_code})")
    return r.json()

# =====================================================
# SAFE TRACE IDENTIFIER
# =====================================================
def get_trace_identifier(trace):
    for key in ("uuid", "traceId", "id", "vulnerabilityUuid"):
        if key in trace and trace[key]:
            return str(trace[key])
    return hashlib.sha256(str(trace).encode()).hexdigest()[:8]

# =====================================================
# LLM ANALYSIS (PLACEHOLDER)
# =====================================================
def call_llm(prompt: str) -> str:
    return f"""
### Why this is Vulnerable
Untrusted input reaches a sensitive sink without sufficient validation.

### Exploitability
An attacker can manipulate input during normal execution paths.

### Secure Fix
Validate input and use secure framework APIs.

### Risk Summary
This issue violates trust boundaries and requires remediation.
"""

# =====================================================
# TRACE ANALYSIS
# =====================================================
def analyze_trace(trace):
    trace_id = get_trace_identifier(trace)
    analysis_id = f"ANL-{trace_id[:8].upper()}"

    src = trace.get("sourceLocation", {})
    snk = trace.get("sinkLocation", {})

    prompt = f"""
Analysis ID: {analysis_id}

Vulnerability: {trace.get('title')}
Severity: {trace.get('severity')}

Input:
File: {src.get('file')}
Line: {src.get('line')}

Output:
File: {snk.get('file')}
Line: {snk.get('line')}

Source → Sink:
{trace.get('source')} → {trace.get('sink')}
"""

    explanation = call_llm(prompt)
    return analysis_id, explanation

# =====================================================
# MARKDOWN REPORT
# =====================================================
def generate_report(traces):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        "# 🔐 Automated Contrast Analysis Report",
        "",
        f"Generated: {now}",
        "",
        "### How to Use",
        "Reference **Analysis ID** in Codex for follow-ups.",
        "",
        "---"
    ]

    for trace in traces:
        analysis_id, explanation = analyze_trace(trace)
        src = trace.get("sourceLocation", {})
        snk = trace.get("sinkLocation", {})

        md.extend([
            f"## 🆔 Analysis ID: {analysis_id}",
            f"**Application:** {trace.get('application', {}).get('name')}",
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

# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description="Contrast Trace Analysis (Direct Auth)")
    parser.add_argument("--traces", help="Comma-separated Trace IDs")
    parser.add_argument("--file", help="File containing Trace IDs")
    parser.add_argument("--out", default="contrast_analysis_report.md")
    args = parser.parse_args()

    validate_connection()

    trace_ids = load_trace_ids(args.traces, args.file)

    traces = []
    for tid in trace_ids:
        print(f"🔹 Fetching trace {tid}")
        traces.append(fetch_trace(tid))

    report = generate_report(traces)
    Path(args.out).write_text(report, encoding="utf-8")

    print(f"\n✅ Analysis completed: {args.out}")

if __name__ == "__main__":
    main()
