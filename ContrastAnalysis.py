#!/usr/bin/env python3
import sys
import uuid as uuidlib
import argparse
import requests

def fetch_trace_metadata(org_id, trace_id, auth_header, api_key):
    """
    Fetch metadata for a single trace ID using the /orgtraces/filter endpoint.
    """
    base_url = "https://app.contrastsecurity.com/Contrast/api/ng"
    url = f"{base_url}/{org_id}/orgtraces/filter"
    params = {"expand": "server_environments"}  # include server environments in response
    headers = {
        "Authorization": auth_header,
        "API-Key": api_key,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"HTTP error fetching trace {trace_id}: {e}")
    data = response.json()
    traces = data.get("traces") or []
    for trace in traces:
        if trace.get("uuid") == trace_id:
            # Found the matching trace; extract fields
            return {
                "uuid": trace.get("uuid"),
                "rule_name": trace.get("rule_name"),
                "rule_title": trace.get("rule_title"),
                "title": trace.get("title"),
                "sub_title": trace.get("sub_title"),
                "severity": trace.get("severity"),
                "severity_label": trace.get("severity_label"),
                "status": trace.get("status"),
                "server_environments": [env.get("name") for env in trace.get("server_environments", []) if env.get("name")],
                "total_notes": trace.get("total_notes"),
                "total_traces_received": trace.get("total_traces_received")
            }
    raise RuntimeError(f"Trace {trace_id} not found in API response")

def main():
    parser = argparse.ArgumentParser(
        description="Fetch Contrast trace metadata by trace ID and output a Markdown report."
    )
    parser.add_argument("--org", required=True, help="Contrast organization UUID")
    parser.add_argument("--auth", required=True,
                        help="Base64-encoded Authorization header (username:service-key)")
    parser.add_argument("--api-key", required=True, help="Contrast API key (plaintext)")
    parser.add_argument("trace_ids", nargs='+', help="One or more trace UUIDs to fetch")
    args = parser.parse_args()

    analysis_id = str(uuidlib.uuid4())
    print("# Contrast Security Trace Metadata Report")
    print(f"Analysis ID: {analysis_id}")

    for tid in args.trace_ids:
        try:
            info = fetch_trace_metadata(args.org, tid, args.auth, args.api_key)
        except Exception as e:
            print(f"\n## Trace {tid}  _(Error)_")
            print(f"- **Error:** {e}", file=sys.stderr)
            continue

        # Format output for this trace
        status = info.get("status") or ""
        print(f"\n## Trace {info['uuid']} _(Status: {status})_")
        print(f"- **Rule Name:** {info.get('rule_name', '')}")
        print(f"- **Rule Title:** {info.get('rule_title', '')}")
        print(f"- **Title:** {info.get('title', '')}")
        sub = info.get("sub_title") or ""
        print(f"- **Sub-title:** {sub if sub else 'None'}")
        sev = info.get("severity")
        sev_lbl = info.get("severity_label")
        sev_str = f"{sev}" if sev is not None else ""
        if sev_lbl:
            sev_str += f" ({sev_lbl})"
        print(f"- **Severity:** {sev_str.strip()}")
        servers = info.get("server_environments") or []
        print(f"- **Server Environments:** {', '.join(servers) if servers else 'None'}")
        notes = info.get("total_notes")
        print(f"- **Total Notes:** {notes if notes is not None else 'None'}")
        traces = info.get("total_traces_received")
        print(f"- **Total Traces Received:** {traces if traces is not None else 'None'}")

if __name__ == "__main__":
    main()
