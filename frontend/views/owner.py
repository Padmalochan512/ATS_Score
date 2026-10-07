from datetime import datetime

import requests
import streamlit as st

from frontend.services import api_client


def _show_backend_error(exc: Exception) -> None:
    if isinstance(exc, requests.ConnectionError):
        st.error("Could not reach the backend. Is it running on port 8000?")
    elif isinstance(exc, requests.HTTPError) and exc.response is not None:
        st.error(f"Backend returned {exc.response.status_code}: {exc.response.text}")
    else:
        st.error(f"Unexpected error: {exc}")


def _truncate(text: str, limit: int = 500) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _fmt_timestamp(value: str) -> str:
    if not value:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return value


def render() -> None:
    st.title("👑 Owner Dashboard")
    st.markdown("Review recent logins, saved analyses, and the text extracted from uploaded resumes.")

    access_token = st.session_state.get("access_token")
    if not access_token:
        st.warning("Sign in with the owner account to access this page.")
        return

    try:
        dashboard = api_client.get_owner_dashboard(access_token)
    except requests.RequestException as exc:
        _show_backend_error(exc)
        return

    login_events = dashboard.get("login_events", []) or []
    analyses = dashboard.get("analyses", []) or []

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Recent logins", len(login_events))
    with c2:
        st.metric("Saved resumes", len(analyses))

    st.markdown("---")

    st.subheader("Recent Logins")
    if not login_events:
        st.info("No login events recorded yet.")
    else:
        for event in login_events:
            with st.expander(
                f"{event.get('email') or event.get('user_id', 'unknown user')} "
                f"• {_fmt_timestamp(event.get('created_at', ''))}"
            ):
                st.write(f"User ID: `{event.get('user_id', '')}`")
                st.write(f"Provider: `{event.get('provider', '')}`")
                st.write(f"Event: `{event.get('event_type', 'login')}`")
                metadata = event.get("metadata") or {}
                if metadata:
                    st.json(metadata)

    st.markdown("---")

    st.subheader("Saved Resumes")
    if not analyses:
        st.info("No resume analyses have been saved yet.")
        return

    for item in analyses:
        filename = item.get("filename") or "resume"
        user_email = item.get("user_email") or item.get("user_id", "")
        score = float(item.get("ats_score", 0) or 0)
        created_at = _fmt_timestamp(item.get("created_at", ""))

        with st.expander(f"{filename} • {user_email} • Score {score:.0f}/100 • {created_at}"):
            top_cols = st.columns(4)
            top_cols[0].metric("ATS", f"{score:.0f}/100")
            top_cols[1].metric("Keyword Match", f"{float(item.get('keyword_match', 0) or 0):.0f}%")
            top_cols[2].metric("User", user_email or "Unknown")
            top_cols[3].metric("File", filename)

            resume_text = item.get("resume_text", "")
            job_description = item.get("job_description", "")
            analysis_result = item.get("analysis_result", {}) or {}

            st.markdown("**Resume Preview**")
            st.code(_truncate(resume_text, 4000) or "No resume text stored yet.", language="text")

            if job_description:
                st.markdown("**Job Description Preview**")
                st.code(_truncate(job_description, 2500), language="text")

            if analysis_result:
                st.markdown("**Analysis Snapshot**")
                st.json(
                    {
                        "ats_score": analysis_result.get("ats_score"),
                        "strengths": analysis_result.get("strengths", [])[:5],
                        "critical_issues": analysis_result.get("critical_issues", [])[:5],
                        "suggestions": analysis_result.get("suggestions", [])[:5],
                    }
                )

