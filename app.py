import html
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from git.exc import GitCommandError
from streamlit.errors import StreamlitSecretNotFoundError

from backend.repo_processor import (
    MAX_DISCOVERED_FILES,
    build_model_context,
    clone_repository,
    detect_repository_type,
    get_binary_inventory,
    inspect_repository_files,
    list_repository_files,
    summarize_file_types,
    validate_github_url,
)
from backend.llm_service import explain_repository_contents

def analyze_github_repository(github_url):
    """Clone and inspect a public repository, then explain it using the Cloud LLM."""
    started_at = time.perf_counter()
    validate_github_url(github_url)

    with tempfile.TemporaryDirectory() as temporary_folder:
        repository = clone_repository(
            github_url, str(Path(temporary_folder) / "repository")
        )
        with repository:
            file_entries = list_repository_files(repository)
            if not file_entries:
                raise ValueError("The GitHub repository contains no tracked files.")

            structures, content_items, analysis_notes = inspect_repository_files(
                file_entries
            )
            repository_type = detect_repository_type(file_entries, content_items)
            context, analyzed_paths = build_model_context(
                file_entries, content_items, structures
            )
            if len(file_entries) >= MAX_DISCOVERED_FILES:
                analysis_notes.append(
                    "File discovery reached its safety limit, so the repository "
                    "inventory may be incomplete."
                )

            analyzed_files = sorted(analyzed_paths)
            summarized_paths = set(structures) - analyzed_paths
            summarized_paths.update(
                item["path"]
                for item in content_items
                if item["path"] not in analyzed_paths
            )
            summarized_files = sorted(summarized_paths)
            processed_paths = analyzed_paths | set(summarized_files)
            skipped_files = [
                entry["path"]
                for entry in file_entries
                if entry["path"] not in processed_paths
            ]

            binary_files = get_binary_inventory(file_entries)
            if binary_files:
                context += (
                    "\n\nBinary and special files (internal contents not inspected):\n"
                )
                context += "\n".join(
                    f"- {item['path']} [{item['type']}, {item['size_bytes']} bytes]"
                    for item in binary_files[:40]
                )
                if len(binary_files) > 40:
                    context += (
                        f"\n- ... {len(binary_files) - 40} more binary/special files"
                    )

            repository_name = urlparse(github_url).path.rstrip("/").split("/")[-1]
            if repository_name.endswith(".git"):
                repository_name = repository_name[:-4]
                
            explanation, req_count = explain_repository_contents(
                repository_name,
                repository_type,
                context,
                analysis_notes,
            )

            return {
                "success": True,
                "repository_url": github_url,
                "repository_type": repository_type,
                "files_found": len(file_entries),
                "files_analyzed": len(analyzed_files),
                "files_summarized": len(summarized_files),
                "files_skipped": len(skipped_files),
                "analyzed_files": analyzed_files,
                "summarized_files": summarized_files,
                "skipped_files": skipped_files,
                "binary_files": binary_files,
                "file_type_summary": summarize_file_types(file_entries),
                "analysis_notes": analysis_notes,
                "analysis_time_seconds": round(time.perf_counter() - started_at, 2),
                "llm_provider": "Cloud AI",
                "llm_requests": req_count,
                "explanation": explanation,
            }

st.set_page_config(
    page_title="RepoExplain",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        :root {
            --bg: #F8FAFC;
            --card: #FFFFFF;
            --border: #E2E8F0;
            --text: #172033;
            --muted: #64748B;
            --primary: #3157D5;
            --primary-hover: #2748B8;
            --primary-soft: #EEF4FF;
            --purple-soft: #F5F2FF;
            --green-soft: #EEF9F3;
            --amber-soft: #FFF8E8;
            --pink-soft: #FFEAF1;
            --gray-soft: #F1F5F9;
            --success: #2E9B68;
            --warning-bg: #FFF8E8;
            --warning-border: #F1D28A;
            --warning-text: #7A5A16;
            --danger-bg: #FFF1F2;
            --danger-border: #FECED6;
            --danger-text: #9F1239;
            --shadow: 0 10px 22px rgba(15, 23, 42, 0.05);
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: var(--bg);
            color: var(--text);
            font-family: Inter, "Segoe UI", sans-serif;
        }

        .stApp {
            background: var(--bg);
        }

        .block-container {
            max-width: 1160px !important;
            padding-top: 24px !important;
            padding-bottom: 28px !important;
            padding-left: 18px !important;
            padding-right: 18px !important;
        }

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stSidebar"] {
            display: none !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stVerticalBlock"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }

        div[data-testid="stTextInput"] > div,
        div[data-testid="stTextInput"] > div > div,
        div[data-testid="stTextInput"] > div > div > div,
        div[data-testid="stTextInput"] > div > div > div > div {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            box-shadow: none !important;
            color: var(--text) !important;
        }

        div[data-testid="stTextInput"] input {
            background: #ffffff !important;
            color: var(--text) !important;
            -webkit-text-fill-color: var(--text) !important;
            font-size: 1rem !important;
            min-height: 48px !important;
            padding: 0 14px !important;
            border: none !important;
        }

        div[data-testid="stTextInput"] input::placeholder {
            color: var(--muted) !important;
            opacity: 1 !important;
        }

        div[data-testid="stButton"] > button,
        [data-testid="stFormSubmitButton"] button,
        button[kind="primary"] {
            background: var(--primary) !important;
            color: #ffffff !important;
            border: 1px solid var(--primary) !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 20px rgba(49, 87, 213, 0.15) !important;
            font-weight: 700 !important;
            min-height: 48px !important;
            transition: background 0.2s ease, border-color 0.2s ease, transform 0.15s ease !important;
        }

        div[data-testid="stButton"] > button:hover,
        [data-testid="stFormSubmitButton"] button:hover,
        button[kind="primary"]:hover {
            background: var(--primary-hover) !important;
            border-color: var(--primary-hover) !important;
            transform: translateY(-1px);
        }

        .site-header {
            margin-bottom: 10px;
        }

        .brand {
            margin: 0;
            color: var(--text);
            font-size: 2.05rem;
            font-weight: 800;
            line-height: 1.1;
            letter-spacing: -0.06em;
        }

        .brand-sub {
            margin-top: 2px;
            color: var(--muted);
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .hero {
            text-align: center;
            background: var(--primary-soft);
            border: 1px solid #DDE9FF;
            border-radius: 18px;
            padding: 22px 20px 18px;
            margin: 10px 0 22px;
            box-shadow: var(--shadow);
        }

        .hero-label {
            color: var(--primary);
            font-size: 0.72rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-weight: 700;
            margin: 0 0 10px;
        }

        .hero-title {
            margin: 0;
            color: var(--text);
            font-size: clamp(2.1rem, 4vw, 3.5rem);
            line-height: 1.08;
            letter-spacing: -0.065em;
            font-weight: 800;
        }

        .hero-subtitle {
            margin-top: 8px;
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 600;
        }

        .hero-copy {
            margin: 10px auto 0;
            max-width: 680px;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.6;
        }

        .url-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px 18px 16px;
            box-shadow: var(--shadow);
            margin-bottom: 18px;
        }

        .field-label {
            margin-bottom: 8px;
            color: var(--text);
            font-size: 0.96rem;
            font-weight: 700;
        }

        .helper-text {
            margin: 0 0 14px;
            color: var(--muted);
            font-size: 0.95rem;
        }

        .url-row {
            display: flex;
            align-items: stretch;
            gap: 12px;
        }

        div[data-testid="stTextInput"] {
            flex: 1;
            width: 100%;
        }

        div[data-testid="stTextInput"] > div {
            background: #FFFFFF !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            min-height: 48px !important;
            box-shadow: none !important;
        }

        div[data-testid="stTextInput"]:focus-within > div {
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 3px rgba(49, 87, 213, 0.12) !important;
        }

        div[data-testid="stTextInput"] input {
            background: transparent !important;
            color: var(--text) !important;
            font-size: 0.98rem !important;
            padding: 0 14px !important;
            height: 48px !important;
        }

        div[data-testid="stTextInput"] input::placeholder {
            color: var(--muted) !important;
        }

        div[data-testid="stButton"] {
            display: flex;
        }

        div[data-testid="stButton"] > button {
            width: 100%;
            height: 48px !important;
            border-radius: 10px !important;
            border: 1px solid var(--primary) !important;
            background: var(--primary) !important;
            color: #FFFFFF !important;
            font-size: 0.96rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.01em !important;
            box-shadow: 0 8px 16px rgba(49, 87, 213, 0.18) !important;
            padding: 0 18px !important;
            transition: background 0.2s ease, border-color 0.2s ease, transform 0.12s ease !important;
        }

        div[data-testid="stButton"] > button:hover {
            background: var(--primary-hover) !important;
            border-color: var(--primary-hover) !important;
            transform: translateY(-1px);
        }

        div[data-testid="stButton"] > button:focus {
            box-shadow: 0 0 0 3px rgba(49, 87, 213, 0.2) !important;
        }

        .empty-state {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 22px 18px;
            text-align: center;
            box-shadow: var(--shadow);
        }

        .empty-state .title {
            margin: 0 0 8px;
            color: var(--text);
            font-size: 1.1rem;
            font-weight: 700;
        }

        .empty-state .text {
            margin: 0;
            color: var(--muted);
            font-size: 0.96rem;
        }

        .error-box,
        .loading-box,
        .warning-box {
            border-radius: 12px;
            padding: 12px 14px;
            margin-top: 12px;
            font-size: 0.95rem;
            line-height: 1.5;
        }

        .error-box {
            background: var(--danger-bg);
            border: 1px solid var(--danger-border);
            color: var(--danger-text);
        }

        .loading-box {
            background: rgba(49, 87, 213, 0.04);
            border: 1px solid rgba(49, 87, 213, 0.08);
            color: var(--muted);
        }

        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-top: 34px;
            margin-bottom: 14px;
        }

        .results-header h2 {
            margin: 0;
            color: var(--text);
            font-size: 1.1rem;
            font-weight: 800;
            letter-spacing: -0.03em;
        }

        .status-pill {
            color: var(--success);
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .overview-label {
            margin: 10px 0 12px;
            color: var(--text);
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            margin-bottom: 18px;
        }

        .metric-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-top: 4px solid var(--primary);
            border-radius: 14px;
            padding: 16px 18px 12px;
            min-height: 118px;
            box-shadow: var(--shadow);
        }

        .metric-card[data-card="files"] {
            background: var(--purple-soft);
            border-top-color: #7C5CFC;
        }

        .metric-card[data-card="status"] {
            background: var(--green-soft);
            border-top-color: #2E9B68;
        }

        .metric-card[data-card="type"] {
            background: var(--primary-soft);
        }

        .metric-label {
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .metric-value {
            margin: 0;
            color: var(--text);
            font-size: clamp(1.2rem, 2vw, 1.8rem);
            letter-spacing: -0.04em;
            line-height: 1.2;
            font-weight: 800;
        }

        .section-label {
            margin: 18px 0 10px;
            color: var(--text);
            font-size: 0.82rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 800;
        }

        .badge-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 14px;
        }

        .file-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 7px 10px;
            border-radius: 999px;
            border: 1px solid var(--border);
            color: var(--text);
            font-size: 0.76rem;
            font-weight: 700;
            line-height: 1;
        }

        .file-badge[data-tone="source"] { background: #EAF3FF; }
        .file-badge[data-tone="docs"] { background: #F3EEFF; }
        .file-badge[data-tone="pdf"] { background: #FFEAF1; }
        .file-badge[data-tone="unsupported"] { background: #FFF4D9; }
        .file-badge[data-tone="other"] { background: #F1F5F9; }

        .warning-box {
            background: var(--warning-bg);
            border: 1px solid var(--warning-border);
            color: var(--warning-text);
        }

        .ai-panel {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: var(--shadow);
            overflow: hidden;
            margin-top: 16px;
        }

        .ai-header {
            background: var(--purple-soft);
            border-bottom: 1px solid var(--border);
            padding: 18px 20px 14px;
        }

        .ai-header-row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
        }

        .ai-title {
            margin: 0;
            color: var(--text);
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: -0.04em;
        }

        .ai-subtitle {
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .ai-panel .stMarkdown {
            padding: 20px 20px 24px;
        }

        .ai-panel .stMarkdown h1,
        .ai-panel .stMarkdown h2,
        .ai-panel .stMarkdown h3,
        .ai-panel .stMarkdown h4,
        .ai-panel .stMarkdown h5,
        .ai-panel .stMarkdown h6 {
            color: var(--text);
            margin: 1.25rem 0 0.6rem;
            line-height: 1.3;
            letter-spacing: -0.04em;
        }

        .ai-panel .stMarkdown h1 { font-size: 1.9rem; }
        .ai-panel .stMarkdown h2 { font-size: 1.5rem; }
        .ai-panel .stMarkdown h3 { font-size: 1.2rem; }

        .ai-panel .stMarkdown p,
        .ai-panel .stMarkdown li,
        .ai-panel .stMarkdown ul,
        .ai-panel .stMarkdown ol {
            color: var(--text);
            font-size: 1rem;
            line-height: 1.72;
            margin: 0.6rem 0;
        }

        .ai-panel .stMarkdown ul,
        .ai-panel .stMarkdown ol {
            padding-left: 1.3rem;
        }

        .ai-panel .stMarkdown strong {
            color: var(--text);
        }

        .ai-panel .stMarkdown a {
            color: var(--primary);
        }

        .ai-panel .stMarkdown code {
            background: #F1F5F9;
            color: var(--text);
            border-radius: 6px;
            border: 1px solid var(--border);
            padding: 0.16rem 0.35rem;
        }

        .ai-panel .stMarkdown pre {
            background: #F8FAFC;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 16px;
            overflow-x: auto;
            color: var(--text);
        }

        .ai-panel .stMarkdown hr {
            border: none;
            border-top: 1px solid var(--border);
            margin: 1.2rem 0;
        }

        @media (max-width: 768px) {
            .brand { font-size: 1.7rem; }
            .hero-title { font-size: 2.2rem; }
            .url-row { flex-direction: column; }
            .metric-grid { grid-template-columns: 1fr; }
            .results-header { display: block; }
            .status-pill { display: inline-block; margin-top: 8px; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_value(value, fallback="N/A"):
    if value is None or value == "":
        return fallback
    return value


def tone_for_file_type(name):
    key = str(name).lower()
    if "source" in key or "code" in key:
        return "source"
    if "document" in key or "markdown" in key or "config" in key:
        return "docs"
    if "pdf" in key:
        return "pdf"
    if "binary" in key or "unsupported" in key:
        return "unsupported"
    return "other"


def format_badge_name(value):
    text = str(value).replace("_", " ")
    replacements = {
        "Pdf": "PDF",
        "Source": "Source",
        "Code": "Code",
        "Binary": "Binary",
        "Documentation": "Documentation",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.title()


st.markdown(
    """
    <div class="site-header">
        <div class="brand">RepoExplain</div>
        <div class="brand-sub">AI Repository Intelligence</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="hero-label">AI REPOSITORY INTELLIGENCE</div>
        <h1 class="hero-title">Understand Any GitHub Repository</h1>
        <div class="hero-subtitle">Analyze. Understand. Explore.</div>
        <div class="hero-copy">Turn any public GitHub repository into a clear, structured explanation using Cloud AI.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="url-card"><div class="field-label">Repository URL</div><div class="helper-text">Enter a public GitHub repository URL to begin the analysis.</div><div class="url-row">',
    unsafe_allow_html=True,
)
url_col, button_col = st.columns([5, 1.5])
with url_col:
    github_url = st.text_input(
        "",
        value=st.session_state.get("github_url", ""),
        placeholder="https://github.com/username/repository",
        label_visibility="collapsed",
        key="github_url_input",
    )
with button_col:
    analyze_clicked = st.button("Analyze Repository", use_container_width=True)
st.markdown("</div></div>", unsafe_allow_html=True)

if not st.session_state.get("last_result") and not analyze_clicked:
    st.markdown(
        """
        <div class="empty-state">
            <div class="title">Ready to analyze</div>
            <div class="text">Enter a GitHub repository URL above to get started.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if analyze_clicked:
    st.session_state["github_url"] = github_url
    if not github_url.strip():
        st.markdown("<div class='error-box'>Please enter a GitHub repository URL.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='loading-box'>Analyzing repository...</div>", unsafe_allow_html=True)
        try:
            result = analyze_github_repository(github_url.strip())
        except GitCommandError:
            st.session_state.pop("last_result", None)
            st.markdown(
                "<div class='error-box'>Could not read the public GitHub repository. "
                "Check that the URL is correct and the repository is accessible.</div>",
                unsafe_allow_html=True,
            )
        except (ValueError, OSError, RuntimeError) as error:
            st.session_state.pop("last_result", None)
            st.markdown(
                f"<div class='error-box'>{html.escape(str(error))}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.session_state["last_result"] = result

result = st.session_state.get("last_result")
if result:
    st.markdown(
        """
        <div class="results-header">
            <h2>Repository Analysis</h2>
            <div class="status-pill">Analysis Complete</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="overview-label">Repository Overview</div>', unsafe_allow_html=True)

    overview_cards = [
        ("Repository Type", safe_value(result.get("repository_type")), "type"),
        ("Files Analyzed", safe_value(result.get("files_analyzed")), "files"),
        ("Analysis Status", "Complete", "status"),
    ]

    cols = st.columns(3)
    for col, (label, value, card_type) in zip(cols, overview_cards):
        with col:
            st.markdown(
                f"""
                <div class="metric-card" data-card="{card_type}">
                    <div class="metric-label">{label}</div>
                    <p class="metric-value">{value}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    file_types = result.get("file_type_summary") or {}
    if file_types:
        st.markdown('<div class="section-label">File Types</div>', unsafe_allow_html=True)
        badges = "".join(
            f"<span class='file-badge' data-tone='{tone_for_file_type(name)}'>{format_badge_name(name)}: {value}</span>"
            for name, value in file_types.items()
        )
        st.markdown(f"<div class='badge-wrap'>{badges}</div>", unsafe_allow_html=True)

    binary_files = result.get("binary_files") or []
    if binary_files:
        st.markdown(
            f"<div class='warning-box'>Unsupported Files<br>Some binary files were identified, but their internal contents were not inspected.</div>",
            unsafe_allow_html=True,
        )

    analysis_notes = result.get("analysis_notes") or []
    for note in analysis_notes:
        st.markdown(f"<div class='warning-box'>{note}</div>", unsafe_allow_html=True)

    explanation = result.get("explanation") or ""
    st.markdown(
        """
        <div class="ai-panel">
            <div class="ai-header">
                <div class="ai-header-row">
                    <div class="ai-title">AI Repository Explanation</div>
                    <div class="ai-subtitle">Generated remotely using Cloud AI</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(explanation)
    st.markdown("</div>", unsafe_allow_html=True)