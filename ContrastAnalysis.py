import requests
import argparse
import base64
from datetime import datetime
from pathlib import Path
import sys

# =====================================================
# CONFIGURATION (MATCH YOUR WORKING CURL)
# =====================================================
CONTRAST_BASE_URL = "https://contrast.eclinicalworks.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"

USERNAME = "your.email@company.com"
SERVICE_KEY = "YOUR_SERVICE_KEY"
API_KEY = "YOUR_API_KEY"

TIMEOUT = 30  # VPN-safe

# =====================================================
# AUTH + SESSION
# =====================================================
def build_headers():
    raw = f"{USERNAME}:{SERVICE_KEY}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("utf-8")
    return {
        "Authorization": f"Basic {encoded}",
        "API-Key": API_KEY,
        "Accept": "application/json"
    }

SESSION = requests.Session()
SESSION.headers.update(build_headers())

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

    print(f"❌ Validation failed ({r.status_code})")
    print(r.text)
    sys.exit(1)

# =====================================================
# INPUT HANDLING
# =====================================================
def load_trace_ids(traces, file):
    ids = set()
    if traces:
        ids.update(t.strip() for t in traces.split(",") if t.strip())
    if file:
        with open(file) as f:
            ids.update(line.strip() for line in f if line.strip())
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
# EXTRACT SOURCE & SINK (REAL FIX)
# =====================================================
def extract_source_sink(trace):
    source = {}
    sink = {}

    for event in trace.get("events", []):
        if event.get("type") == "SOURCE":
            source = event
        elif event.get("type") == "SINK":
            sink = event

    return source, sink

# =====================================================
# ANALYSIS ID RESOLUTION
# =====================================================
def resolve_trace_identifier(trace, fallback):
    return (
        trace.get("traceId")
        or trace.get("uuid")
        or trace.get("id")
        or fallback
    )

# =====================================================
# LLM PLACEHOLDER (Codex reads MD later)
# =====================================================
def security_analysis_text():
    return (
        "Untrusted input reaches a sensitive sink without sufficient validation, "
        "allowing an attacker to influence application behavior across trust boundaries. "
        "This can be exploited during normal execution paths and should be remediated "
        "using strict input validation and safe framework APIs."
    )

# =====================================================
# GENERATE MARKDOWN REPORT
# =====================================================
def generate_report(traces_with_ids):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        "# 🔐 Automated Contrast Analysis Report",
        "",
        f"Generated: {now}",
        "",
        "### How to Use",
        "Paste this Markdown into Codex and ask questions using **Analysis ID**.",
        "",
        "---"
    ]

    for trace, trace_id in traces_with_ids:
        trace_identifier = resolve_trace_identifier(trace, trace_id)
        analysis_id = f"ANL-{trace_identifier.replace('-', '')[:8].upper()}"

        source, sink = extract_source_sink(trace)

        application = (
            trace.get("applicationName")
            or trace.get("application", {}).get("name")
            or "Unknown"
        )

        severity = trace.get("severity", "Unknown")
        vuln = trace.get("title", "Unknown")

        md.extend([
            f"## 🆔 Analysis ID: {analysis_id}",
            f"**Trace ID:** {trace_identifier}",
            f"**Application:** {application}",
            f"**Severity:** {severity}",
            f"**Vulnerability:** {vuln}",
            "",
            "### 📥 Input (Source)",
            f"- File: `{source.get('file', 'N/A')}`",
            f"- Line: `{source.get('line', 'N/A')}`",
            "",
            "### 📤 Output (Sink)",
            f"- File: `{sink.get('file', 'N/A')}`",
            f"- Line: `{sink.get('line', 'N/A')}`",
            "",
            "### 🧠 Security Analysis",
            security_analysis_text(),
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
    parser = argparse.ArgumentParser(description="Final Contrast Analysis Generator")
    parser.add_argument("--traces", help="Comma-separated Trace IDs")
    parser.add_argument("--file", help="File containing Trace IDs")
    parser.add_argument("--out", default="contrast_analysis_report.md")
    args = parser.parse_args()

    validate_connection()

    trace_ids = load_trace_ids(args.traces, args.file)

    traces_with_ids = []
    for tid in trace_ids:
        print(f"🔹 Fetching trace {tid}")
        trace = fetch_trace(tid)
        traces_with_ids.append((trace, tid))

    report = generate_report(traces_with_ids)
    Path(args.out).write_text(report, encoding="utf-8")

    print(f"\n✅ Report generated: {args.out}")

if __name__ == "__main__":
    main()
