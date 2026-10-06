import re
import html
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

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

st.set_page_config(
    page_title="CodeLens AI - GitHub Repository Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Professional CodeLens AI Branding
st.markdown("""
    <style>
        :root {
            --primary: #4f46e5;
            --primary-gradient: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            --sidebar-bg: #0f172a;
            --sidebar-text: #f8fafc;
            --bg-color: #f1f5f9;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
        }
        
        /* Global Styles */
        html, body, [data-testid="stAppViewContainer"] {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: var(--sidebar-bg) !important;
            border-right: 1px solid #1e293b;
        }
        [data-testid="stSidebar"] * {
            color: var(--sidebar-text) !important;
        }
        .sidebar-brand {
            font-size: 1.5rem;
            font-weight: 800;
            margin-bottom: 5px;
            background: -webkit-linear-gradient(45deg, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .sidebar-sub {
            font-size: 0.8rem;
            color: #94a3b8 !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
            margin-bottom: 30px;
        }
        
        /* Hero Section */
        .hero {
            background: var(--primary-gradient);
            padding: 3.5rem 2rem;
            border-radius: 16px;
            text-align: center;
            color: white;
            box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.4);
            margin-bottom: 2rem;
        }
        .hero h1 {
            font-size: 2.75rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            color: white;
        }
        .hero p {
            font-size: 1.1rem;
            opacity: 0.9;
            max-width: 600px;
            margin: 0 auto;
        }
        
        /* Cards */
        .metric-card {
            background: var(--card-bg);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            text-align: center;
        }
        .metric-value {
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 4px;
        }
        .metric-label {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        
        /* Input & Buttons */
        div[data-testid="stTextInput"] input {
            border-radius: 8px !important;
            border: 1px solid #cbd5e1 !important;
            padding: 12px 16px !important;
            font-size: 1.05rem !important;
            box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05) !important;
        }
        div[data-testid="stButton"] button {
            background: var(--primary) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 10px 24px !important;
            font-weight: 600 !important;
            transition: all 0.2s ease !important;
            width: 100%;
        }
        div[data-testid="stButton"] button:hover {
            background: #4338ca !important;
            box-shadow: 0 4px 12px rgba(67, 56, 202, 0.3) !important;
        }
        
        /* Status Badges */
        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-bottom: 12px;
        }
        .status-online { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
        .status-offline { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .dot-green { background-color: #10b981; }
        .dot-red { background-color: #ef4444; }

        /* Tabs styling */
        [data-testid="stTabs"] button {
            font-weight: 600;
        }
        
        /* Hide unnecessary Streamlit elements */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        
        /* File Tree */
        .tree-pre {
            background: #1e293b;
            color: #e2e8f0;
            border-radius: 8px;
            padding: 1rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.9rem;
            overflow-x: auto;
        }
    </style>
""", unsafe_allow_html=True)

def extract_section(explanation, header):
    """Extract a specific markdown section from the AI explanation."""
    pattern = rf"(?im)^#\s*{re.escape(header)}\s*\n(.*?)(?=\n#\s|\Z)"
    match = re.search(pattern, explanation, re.DOTALL)
    if match:
        val = match.group(1).strip()
        return val if val else "No significant information provided."
    return "This could not be determined from the available repository content."

def generate_file_tree(structures):
    """Generate a clean ASCII file tree from the inspected structures."""
    if not structures:
        return "No structure found."
    
    # Sort files to ensure folders/files look ordered
    paths = sorted(structures.keys())
    tree_lines = []
    
    # A simple pseudo-tree formatting for Streamlit presentation
    for p in paths:
        parts = p.split('/')
        depth = len(parts) - 1
        indent = "│   " * depth
        icon = "📄 "
        name = parts[-1]
        tree_lines.append(f"{indent}{icon}{name}")
        
    return "\n".join(tree_lines)

# Sidebar
with st.sidebar:
    st.markdown('<div class="sidebar-brand">CodeLens AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">GitHub Repository Intelligence</div>', unsafe_allow_html=True)
    
    st.markdown("### System Status")
    
    # Fake checks for UI presentation of Cloud status
    st.markdown("""
        <div class="status-badge status-online">
            <div class="status-dot dot-green"></div> APPLICATION Online
        </div><br>
        <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Hosted on Streamlit Cloud</div>
        
        <div class="status-badge status-online">
            <div class="status-dot dot-green"></div> CLOUD AI Ready
        </div><br>
        <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Inference endpoints available</div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. Enter a GitHub URL
    2. CodeLens performs a shallow clone
    3. Structural analysis & filtering
    4. AI processes the context
    5. Detailed report generated
    """)
    
    st.markdown("---")
    st.markdown("### ☁️ Cloud AI vs 🖥️ Local Ollama")
    st.markdown("""
    **Cloud AI (Streamlit Cloud):**
    When deployed publicly, CodeLens uses ultra-fast cloud inference (Groq/HuggingFace). This means *anyone* can use your app without installing anything! The Cloud AI securely reads your repository structure and explains it instantly.
    
    **Local Ollama (Offline Mode):**
    If you run this project locally on your own laptop, you can switch it to use `Qwen 2.5 3B` via your local Ollama server. This means 100% of the code stays on your machine and works completely without internet!
    """)

# Main Layout
st.markdown("""
    <div class="hero">
        <h1>Understand Any GitHub Repository</h1>
        <p>Turn any public GitHub repository into a clear, structured explanation using Cloud AI.</p>
    </div>
""", unsafe_allow_html=True)

st.markdown("### Enter Repository URL")
col1, col2 = st.columns([4, 1])

with col1:
    github_url = st.text_input(
        "GitHub URL", 
        placeholder="https://github.com/username/project",
        label_visibility="collapsed",
        key="repo_input"
    )

with col2:
    analyze_btn = st.button("✨ Analyze Repository", use_container_width=True)

@st.cache_data(show_spinner=False)
def perform_analysis(url):
    started_at = time.perf_counter()
    validate_github_url(url)

    with tempfile.TemporaryDirectory() as temporary_folder:
        repository = clone_repository(
            url, str(Path(temporary_folder) / "repository")
        )
        with repository:
            file_entries = list_repository_files(repository)
            if not file_entries:
                raise ValueError("The GitHub repository contains no tracked files.")

            structures, content_items, analysis_notes = inspect_repository_files(file_entries)
            repository_type = detect_repository_type(file_entries, content_items)
            context, analyzed_paths = build_model_context(file_entries, content_items, structures)
            
            if len(file_entries) >= MAX_DISCOVERED_FILES:
                analysis_notes.append("File discovery safety limit reached. Inventory may be incomplete.")

            binary_files = get_binary_inventory(file_entries)
            
            repository_name = urlparse(url).path.rstrip("/").split("/")[-1]
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
                "repository_url": url,
                "repository_name": repository_name,
                "repository_type": repository_type,
                "files_found": len(file_entries),
                "analyzed_paths": list(analyzed_paths),
                "binary_files": len(binary_files),
                "file_type_summary": summarize_file_types(file_entries),
                "analysis_notes": analysis_notes,
                "tree": generate_file_tree(structures),
                "analysis_time_seconds": round(time.perf_counter() - started_at, 2),
                "explanation": explanation,
            }

if analyze_btn:
    if not github_url.strip():
        st.error("Please enter a valid GitHub repository URL.")
    else:
        with st.status("Analyzing Repository...", expanded=True) as status:
            try:
                st.write("🔍 Validating GitHub URL...")
                st.write("📥 Cloning repository & building inventory...")
                # The actual function call is cached, so it runs quickly if already done
                result = perform_analysis(github_url.strip())
                st.write("🧠 Context preparation complete. Generating Cloud AI explanation...")
                
                st.session_state["last_result"] = result
                status.update(label="Analysis Complete!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Analysis Failed", state="error", expanded=False)
                st.error(f"Error during analysis: {str(e)}")

# Results Display
if "last_result" in st.session_state:
    res = st.session_state["last_result"]
    exp = res["explanation"]
    
    st.markdown(f"## Results: `{res['repository_name']}`")
    
    # Key Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{res["files_found"]}</div><div class="metric-label">Total Files</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{res["repository_type"]}</div><div class="metric-label">Detected Type</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{res["analysis_time_seconds"]}s</div><div class="metric-label">Processing Time</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(res["analyzed_paths"])}</div><div class="metric-label">Files Deep-Scanned</div></div>', unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📑 Analysis Navigation")
    
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Overview"

    # Row 1
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Overview", use_container_width=True, type="primary" if st.session_state.active_tab == "Overview" else "secondary"): st.session_state.active_tab = "Overview"
    if c2.button("Repository Structure", use_container_width=True, type="primary" if st.session_state.active_tab == "Repository Structure" else "secondary"): st.session_state.active_tab = "Repository Structure"
    if c3.button("Files & Folders", use_container_width=True, type="primary" if st.session_state.active_tab == "Files & Folders" else "secondary"): st.session_state.active_tab = "Files & Folders"
    if c4.button("Architecture", use_container_width=True, type="primary" if st.session_state.active_tab == "Architecture" else "secondary"): st.session_state.active_tab = "Architecture"

    # Row 2
    c5, c6, c7, c8 = st.columns(4)
    if c5.button("Technologies", use_container_width=True, type="primary" if st.session_state.active_tab == "Technologies" else "secondary"): st.session_state.active_tab = "Technologies"
    if c6.button("Code Analysis", use_container_width=True, type="primary" if st.session_state.active_tab == "Code Analysis" else "secondary"): st.session_state.active_tab = "Code Analysis"
    if c7.button("Workflow", use_container_width=True, type="primary" if st.session_state.active_tab == "Workflow" else "secondary"): st.session_state.active_tab = "Workflow"
    if c8.button("Dependencies", use_container_width=True, type="primary" if st.session_state.active_tab == "Dependencies" else "secondary"): st.session_state.active_tab = "Dependencies"

    # Row 3
    c9, c10, c11, c12 = st.columns(4)
    if c9.button("AI Explanation", use_container_width=True, type="primary" if st.session_state.active_tab == "AI Explanation" else "secondary"): st.session_state.active_tab = "AI Explanation"
    if c10.button("Technical Details", use_container_width=True, type="primary" if st.session_state.active_tab == "Technical Details" else "secondary"): st.session_state.active_tab = "Technical Details"
    if c11.button("Setup", use_container_width=True, type="primary" if st.session_state.active_tab == "Setup" else "secondary"): st.session_state.active_tab = "Setup"
    
    st.markdown("---")
    
    selected_tab = st.session_state.active_tab
    
    if selected_tab == "Overview":
        st.markdown("### Project Overview")
        st.markdown(extract_section(exp, "Overview"))
        
    elif selected_tab == "Repository Structure":
        st.markdown("### Repository Structure")
        st.markdown(f'<pre class="tree-pre">{res["tree"]}</pre>', unsafe_allow_html=True)
        
    elif selected_tab == "Files & Folders":
        st.markdown("### Files & Folders")
        st.markdown(extract_section(exp, "Files & Folders"))
        
    elif selected_tab == "Architecture":
        st.markdown("### Architecture")
        st.markdown(extract_section(exp, "Architecture"))
        
    elif selected_tab == "Technologies":
        st.markdown("### Technologies")
        st.markdown(extract_section(exp, "Technologies"))
        if res["file_type_summary"]:
            st.markdown("#### Detected File Extensions")
            st.write(res["file_type_summary"])
            
    elif selected_tab == "Code Analysis":
        st.markdown("### Code Analysis")
        st.markdown(extract_section(exp, "Code Analysis"))
        
    elif selected_tab == "Workflow":
        st.markdown("### End-to-End Workflow")
        st.markdown(extract_section(exp, "Workflow"))
        
    elif selected_tab == "Dependencies":
        st.markdown("### Dependencies")
        st.markdown(extract_section(exp, "Dependencies"))
        
    elif selected_tab == "AI Explanation":
        st.markdown("### Complete AI Explanation")
        st.markdown(extract_section(exp, "AI Explanation"))
        
    elif selected_tab == "Technical Details":
        st.markdown("### Technical & Performance Details")
        st.markdown(f"- **Binary Files Skipped**: {res['binary_files']}")
        st.markdown(f"- **Context Building & Clone Time**: ~{res['analysis_time_seconds']} seconds")
        st.markdown(f"- **Limits Reached**: {'Yes' if 'safety limit' in str(res['analysis_notes']) else 'No'}")
        if res["analysis_notes"]:
            st.markdown("#### Analysis Notes")
            for note in res["analysis_notes"]:
                st.warning(note)
        st.markdown("#### Limitations")
        st.markdown(extract_section(exp, "Limitations"))
                
    elif selected_tab == "Setup":
        st.markdown("### Setup & Deployment")
        st.markdown(extract_section(exp, "Setup"))