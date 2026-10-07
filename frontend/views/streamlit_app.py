import os
import sys
from pathlib import Path

import streamlit as st

# Project root (ats_score)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.services import api_client, supabase_client


def _owner_emails() -> set[str]:
    emails = set()
    owner_email = os.getenv("OWNER_EMAIL", "").strip().lower()
    if owner_email:
        emails.add(owner_email)
    extra = os.getenv("OWNER_EMAILS", "")
    for email in extra.split(","):
        cleaned = email.strip().lower()
        if cleaned:
            emails.add(cleaned)
    return emails


def _is_owner_email(email: str | None) -> bool:
    if not email:
        return False
    return email.strip().lower() in _owner_emails()


def _sync_owner_flag() -> None:
    st.session_state.is_owner = _is_owner_email(st.session_state.get("user_email"))


def _set_session(result: dict, provider: str) -> None:
    st.session_state.access_token = result["access_token"]
    st.session_state.refresh_token = result["refresh_token"]
    st.session_state.user_id = result["user_id"]
    st.session_state.user_email = result["email"]
    st.session_state.auth_provider = provider
    _sync_owner_flag()

    try:
        api_client.record_login_event(st.session_state.access_token)
    except Exception:
        # Non-blocking: authentication should succeed even if logging fails.
        pass


def load_css() -> str:
    try:
        css_path = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
        with open(css_path, "r") as f:
            return f"<style>{f.read()}</style>"
    except FileNotFoundError:
        return ""


def render_app() -> None:
    # Auth state. Populated by Supabase sign-in / sign-up / OAuth.
    # All four are None when signed out, all four are set when signed in.
    for key, default in [
        ("access_token", None),
        ("refresh_token", None),
        ("user_id", None),  # Supabase auth user id (uuid); also used by api_client
        ("user_email", None),
        ("auth_error", None),
        ("auth_info", None),
        ("auth_provider", None),
        ("is_owner", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    if supabase_client._missing_config():
        auth_error = st.session_state.get("auth_error")
        if auth_error and "Supabase is not configured" in str(auth_error):
            st.session_state.auth_error = None

    # If we just came back from Google OAuth, Supabase appends `?code=<authcode>`
    # to the redirect URL. Exchange it for a session before rendering anything.
    if not st.session_state.access_token and "code" in st.query_params:
        result = supabase_client.exchange_code_for_session(st.query_params["code"])

        # Always clear the ?code= param so a refresh doesn't try to re-exchange.
        st.query_params.clear()
        if "error" in result:
            st.session_state.auth_error = f"Google sign-in failed: {result['error']}"
        else:
            _set_session(result, provider="google")
            st.rerun()

    st.markdown(load_css(), unsafe_allow_html=True)

    if "current_view" not in st.session_state:
        st.session_state.current_view = "landing"

    with st.sidebar:
        st.markdown("## Navigation")

        if st.button("🏠 Home", use_container_width=True):
            st.session_state.current_view = "landing"
            st.rerun()

        if st.button("🎯 ATS Scorer", use_container_width=True):
            st.session_state.current_view = "scorer"
            st.rerun()

        if st.button("📊 History", use_container_width=True):
            st.session_state.current_view = "history"
            st.rerun()

        if st.button("📚 Resources", use_container_width=True):
            st.session_state.current_view = "resources"
            st.rerun()

        if st.session_state.get("is_owner"):
            if st.button("👑 Owner Dashboard", use_container_width=True):
                st.session_state.current_view = "owner"
                st.rerun()

        st.markdown("---")
        st.markdown("### 👤 Account")

        if st.session_state.access_token:
            st.caption(f"Signed in as **{st.session_state.user_email}**")
            if st.session_state.get("is_owner"):
                st.success("Owner access enabled")
            if st.button("Sign out", use_container_width=True):
                supabase_client.sign_out()
                for k in (
                    "access_token",
                    "refresh_token",
                    "user_id",
                    "user_email",
                    "auth_provider",
                    "is_owner",
                ):
                    st.session_state[k] = None if k != "is_owner" else False
                st.rerun()
        else:
            if st.session_state.auth_error:
                st.error(st.session_state.auth_error)
                st.session_state.auth_error = None
            if st.session_state.auth_info:
                st.info(st.session_state.auth_info)
                st.session_state.auth_info = None

            auth_mode = st.radio(
                "Account mode",
                ["Sign in", "Sign up"],
                horizontal=True,
                label_visibility="collapsed",
                key="auth_mode",
            )

            with st.form("auth_form", clear_on_submit=False):
                email_key = "auth_email"
                password_key = "auth_password"
                email = st.text_input("Email", key=email_key)
                password = st.text_input("Password", type="password", key=password_key)
                submit_label = "Sign in" if auth_mode == "Sign in" else "Create account"
                submitted = st.form_submit_button(submit_label, use_container_width=True)

            if submitted:
                if auth_mode == "Sign in":
                    result = supabase_client.sign_in_with_password(email, password)
                    if "error" in result:
                        st.session_state.auth_error = result["error"]
                    else:
                        _set_session(result, provider="password")
                    st.rerun()
                else:
                    result = supabase_client.sign_up_with_password(email, password)
                    if "error" in result:
                        st.session_state.auth_error = result["error"]
                    elif result.get("pending_confirmation"):
                        st.session_state.auth_info = (
                            f"Check your inbox - confirmation email sent to {result['email']}."
                        )
                    else:
                        _set_session(result, provider="password")
                    st.rerun()

            st.markdown(
                "<div style='text-align:center; margin: 8px 0; color:#94a3b8;'>or</div>",
                unsafe_allow_html=True,
            )

            if supabase_client._missing_config():
                st.info("Local demo mode is active. Sign in with any email and password.")
            else:
                oauth = supabase_client.google_oauth_url()
                if "error" in oauth:
                    st.caption(f"Google sign-in unavailable: {oauth['error']}")
                else:
                    st.link_button(
                        "Continue with Google",
                        url=oauth["url"],
                        use_container_width=True,
                    )

    if st.session_state.current_view == "landing":
        from frontend.views import landing

        landing.render()

    elif st.session_state.current_view == "scorer":
        from frontend.views import scorer

        scorer.render()

    elif st.session_state.current_view == "history":
        from frontend.views import history

        history.render()

    elif st.session_state.current_view == "resources":
        from frontend.views import resources

        resources.render()

    elif st.session_state.current_view == "owner":
        from frontend.views import owner

        owner.render()


if __name__ == "__main__":
    render_app()
