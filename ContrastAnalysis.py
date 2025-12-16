import requests
import argparse
import json
from datetime import datetime
from pathlib import Path
import uuid

# ==============================
# CONTRAST CONFIG
# ==============================
CONTRAST_BASE_URL = "https://app.contrastsecurity.com/Contrast/api/ng"
ORG_ID = "YOUR_ORG_ID"
API_KEY = "YOUR_API_KEY"
AUTH_HEADER = "YOUR_USERNAME:YOUR_SERVICE_KEY"

HEADERS = {
    "Authorization": AUTH_HEADER,
    "API-Key": API_KEY,
    "Content-Type": "application/json"
}

# ==============================
# LLM CONFIG (PLACEHOLDER)
# ==============================
def call_llm(prompt: str) -> str:
    """
    Replace this function with:
    - OpenAI API
    - Azure OpenAI
    - Internal LLM gateway

    This placeholder represents a REAL LLM call.
    """
    # ---- EXAMPLE ONLY ----
    return f"""
### Why this is Vulnerable
The application accepts untrusted input and propagates it without validation.
Because the data reaches a security-sensitive sink, an attacker can manipulate
execution flow.

### Exploit Scenario
An attacker crafts a malicious payload that bypasses input validation and
reaches the sink, allowing unintended behavior.

### Secure Fix
Apply strict input validation and use safe framework APIs to neutralize
attacker-controlled data.

### Risk Justification
The vulnerability is exploitable in normal execution paths and does not
require special privileges.
"""

# ==============================
# INPUT HANDLING
# ==============================
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

# ==============================
# FETCH TRACE
# ==============================
def fetch_trace(trace_id):
    url = f"{CONTRAST_BASE_URL}/{ORG_ID}/traces/{trace_id}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        raise Exception(f"Failed to fetch trace {trace_id}")
    return r.json()

# ==============================
# LLM ANALYSIS
# ==============================
def analyze_trace(trace):
    analysis_id = f"ANL-{trace['uuid'][:8].upper()}"

    source = trace.get("sourceLocation", {})
    sink = trace.get("sinkLocation", {})

    prompt = f"""
You are a senior Application Security expert.

Analyze the following Contrast vulnerability trace.

Analysis ID: {analysis_id}

Vulnerability Type:
{trace.get('title')}

Source (Input):
File: {source.get('file')}
Line: {source.get('line')}

Sink (Output):
File: {sink.get('file')}
Line: {sink.get('line')}

Source → Sink Flow:
{trace.get('source')} → {trace.get('sink')}

Explain clearly:
1. Why this is exploitable
2. How an attacker can abuse it
3. What security boundary is violated
4. How to fix it properly
"""

    explanation = call_llm(prompt)

    return analysis_id, explanation

# ==============================
# MARKDOWN REPORT
# ==============================
def generate_report(traces):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = [
        "# 🔐 Automated Contrast LLM Analysis Report",
        "",
        f"Generated: {now}",
        "",
        "## How to Use This Report in Codex",
        "- Each finding has a unique **Analysis ID**",
        "- Ask Codex: *Explain Analysis-ID ANL-XXXXXXX in more detail*",
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
            "### 🧠 LLM Security Analysis",
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
# MAIN
# ==============================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces")
    parser.add_argument("--file")
    parser.add_argument("--out", default="final_llm_analysis.md")
    args = parser.parse_args()

    trace_ids = load_trace_ids(args.traces, args.file)

    traces = []
    for tid in trace_ids:
        traces.append(fetch_trace(tid))

    report = generate_report(traces)
    Path(args.out).write_text(report, encoding="utf-8")

    print(f"✔ LLM analysis complete: {args.out}")

if __name__ == "__main__":
    main()
