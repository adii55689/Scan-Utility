import requests
import argparse
from datetime import datetime
from pathlib import Path

# =====================================================
# CONFIGURATION
# =====================================================
CONTRAST_BASE_URL = "https://contrast.eclinicalworks.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"

# Use your existing Base64 value directly
AUTHORIZATION_HEADER = "Basic YOUR_BASE64_VALUE"
API_KEY = "YOUR_API_KEY"

TIMEOUT = 30

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
        "?expand=server_environments,violations"
    )
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

# =====================================================
# PARSE TRACE (NO STATUS FILTERING)
# =====================================================
def parse_trace(trace, fallback_id):
    analysis_id = f"ANL-{fallback_id.replace('-', '')[:8].upper()}"

    return {
        "analysis_id": analysis_id,
        "trace_id": trace.get("uuid", fallback_id),
        "rule_name": trace.get("rule_name"),
        "rule_title": trace.get("rule_title"),
        "title": trace.get("title"),
        "sub_title": trace.get("sub_title"),
        "severity": trace.get("severity_label", trace.get("severity")),
        "status": trace.get("status"),
        "environments": ", ".join(trace.get("server_environments", [])),
        "total_traces": trace.get("total_traces_received"),
        "total_notes": trace.get("total_notes"),
    }

# =====================================================
# MARKDOWN GENERATION (CODEX-READY)
# =====================================================
def generate_markdown(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        "# 🔐 Contrast Vulnerability Summary (Trace-Based)",
        "",
        f"Generated: {now}",
        "",
        "## How to use with Codex",
        "Paste this Markdown into Codex and ask:",
        "",
        "`Analyze Analysis ID <ID> and explain exploitability, impact, and secure remediation.`",
        "",
        "---"
    ]

    for r in results:
        md.extend([
            f"## 🆔 Analysis ID: {r['analysis_id']}",
            f"**Trace ID:** {r['trace_id']}",
            f"**Rule:** {r['rule_title']} (`{r['rule_name']}`)",
            f"**Severity:** {r['severity']}",
            f"**Status (API):** {r['status']}",
            f"**Environments:** {r['environments'] or 'N/A'}",
            "",
            "### 📌 Vulnerability Context",
            r["title"] or "N/A",
            "",
            r["sub_title"] or "",
            "",
            "### 📊 Metadata",
            f"- Total traces observed: `{r['total_traces']}`",
            f"- Notes added: `{r['total_notes']}`",
            "",
            "---"
        ])

    return "\n".join(md)

# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(
        description="Fetch Contrast Trace Details for Codex Analysis (No Status Filter)"
    )
    parser.add_argument("--traces", help="Comma-separated Trace IDs")
    parser.add_argument("--file", help="File containing Trace IDs")
    parser.add_argument("--out", default="contrast_trace_summary.md")
    args = parser.parse_args()

    trace_ids = load_trace_ids(args.traces, args.file)

    results = []
    for tid in trace_ids:
        print(f"🔹 Fetching trace {tid}")
        trace = fetch_trace(tid)
        results.append(parse_trace(trace, tid))

    Path(args.out).write_text(
        generate_markdown(results),
        encoding="utf-8"
    )

    print(f"\n✅ Markdown generated: {args.out}")

if __name__ == "__main__":
    main()
