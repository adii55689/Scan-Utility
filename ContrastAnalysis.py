import requests
import argparse
from datetime import datetime
from pathlib import Path
import sys

# =====================================================
# CONFIGURATION (MATCH YOUR WORKING CURL)
# =====================================================
CONTRAST_BASE_URL = "https://contrast.eclinicalworks.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"

# 👇 YOU ALREADY HAVE BASE64 – PASTE IT AS-IS
AUTHORIZATION_HEADER = "Basic YOUR_BASE64_VALUE_HERE"
API_KEY = "YOUR_API_KEY"

TIMEOUT = 30  # VPN / enterprise safe

# =====================================================
# SESSION SETUP
# =====================================================
SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": AUTHORIZATION_HEADER,
    "API-Key": API_KEY,
    "Accept": "application/json"
})

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

    print(f"❌ Connection failed ({r.status_code})")
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
# FETCH TRACE (UI-BACKED ENDPOINT)
# =====================================================
def fetch_trace(trace_id):
    url = (
        f"{CONTRAST_BASE_URL}/{ORG_ID}/orgtraces/filter/{trace_id}"
        "?expand=events,request,application,violations"
    )

    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

# =====================================================
# EXTRACT SOURCE & SINK
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
# ANALYZE TRACE
# =====================================================
def analyze_trace(trace, fallback_trace_id):
    analysis_id = f"ANL-{fallback_trace_id.replace('-', '')[:8].upper()}"

    application = trace.get("application", {}).get("name", "Unknown")

    violations = trace.get("violations", [])
    vulnerability = violations[0].get("rule", "Unknown") if violations else "Unknown"
    severity = violations[0].get("severity", "Unknown") if violations else "Unknown"

    source, sink = extract_source_sink(trace)

    request = trace.get("request", {})
    request_url = request.get("url")
    request_method = request.get("method")
    request_params = request.get("parameters", [])

    return {
        "analysis_id": analysis_id,
        "trace_id": fallback_trace_id,
        "application": application,
        "severity": severity,
        "vulnerability": vulnerability,
        "source": source,
        "sink": sink,
        "request_url": request_url,
        "request_method": request_method,
        "request_params": request_params,
        "stack": trace.get("stackTrace", "N/A")
    }

# =====================================================
# MARKDOWN REPORT
# =====================================================
def generate_report(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        "# 🔐 Automated Contrast Analysis Report",
        "",
        f"Generated: {now}",
        "",
        "## How to Use",
        "Paste this Markdown into Codex and ask questions using **Analysis ID**.",
        "Example:",
        "`Explain Analysis ID ANL-XXXXXXX with exploit scenario and secure fix.`",
        "",
        "---"
    ]

    for r in results:
        md.extend([
            f"## 🆔 Analysis ID: {r['analysis_id']}",
            f"**Trace ID:** {r['trace_id']}",
            f"**Application:** {r['application']}",
            f"**Severity:** {r['severity']}",
            f"**Vulnerability:** {r['vulnerability']}",
            "",
            "### 🌐 Request Context",
            f"- Method: `{r['request_method']}`",
            f"- URL: `{r['request_url']}`",
            f"- Parameters: `{', '.join(r['request_params']) if r['request_params'] else 'N/A'}`",
            "",
            "### 📥 Input (Source)",
            f"- File: `{r['source'].get('file', 'N/A')}`",
            f"- Line: `{r['source'].get('line', 'N/A')}`",
            "",
            "### 📤 Output (Sink)",
            f"- File: `{r['sink'].get('file', 'N/A')}`",
            f"- Line: `{r['sink'].get('line', 'N/A')}`",
            "",
            "### 🧠 Security Analysis",
            "Untrusted input flows from the identified source to a sensitive sink.",
            "This allows attacker-controlled data to influence application behavior",
            "during normal execution paths, making the issue exploitable.",
            "",
            "### 🧵 Stack Trace",
            "```",
            r["stack"],
            "```",
            "",
            "---"
        ])

    return "\n".join(md)

# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(
        description="Contrast → Codex Automated Analysis (Final)"
    )
    parser.add_argument("--traces", help="Comma-separated Trace IDs")
    parser.add_argument("--file", help="File with Trace IDs (one per line)")
    parser.add_argument("--out", default="contrast_analysis_report.md")
    args = parser.parse_args()

    validate_connection()

    trace_ids = load_trace_ids(args.traces, args.file)

    results = []
    for tid in trace_ids:
        print(f"🔹 Fetching trace {tid}")
        trace = fetch_trace(tid)
        results.append(analyze_trace(trace, tid))

    report = generate_report(results)
    Path(args.out).write_text(report, encoding="utf-8")

    print(f"\n✅ Report generated: {args.out}")

if __name__ == "__main__":
    main()
