import re
import html
import tempfile
import uuid
from frontend.ollama_connector import ollama_connector
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
from backend.llm_service import explain_repository_contents, check_ollama_status

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

        /* Warning Box */
        .warning-box {
            background-color: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 500;
            margin-bottom: 10px;
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
    
    st.markdown("### 🤖 Select AI Mode")
    ai_mode = st.radio("AI Mode", ["Cloud AI (Default)", "Local Ollama + Qwen 2.5 3B"], label_visibility="collapsed")
    
    st.markdown("### System Status")
    
    st.markdown("""
        <div class="status-badge status-online">
            <div class="status-dot dot-green"></div> APPLICATION Online
        </div><br>
        <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Hosted on Streamlit Cloud</div>
    """, unsafe_allow_html=True)
    
    if "Cloud" in ai_mode:
        st.markdown("""
            <div class="status-badge status-online">
                <div class="status-dot dot-green"></div> CLOUD AI Ready
            </div><br>
            <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Inference endpoints available</div>
        """, unsafe_allow_html=True)
    else:
        # Check Local Ollama via Browser
        if "check_id" not in st.session_state:
            st.session_state["check_id"] = str(uuid.uuid4())
        
        status_res = ollama_connector(action="check_status", request_id=st.session_state["check_id"], key="ollama_status_sidebar")
        if status_res is None:
            ollama_status = {"running": False, "has_model": False, "error": None}
        else:
            ollama_status = {
                "running": status_res.get("running", False), 
                "has_model": status_res.get("has_model", False),
                "error": status_res.get("error")
            }

        if ollama_status["running"]:
            st.markdown("""
                <div class="status-badge status-online">
                    <div class="status-dot dot-green"></div> OLLAMA Online
                </div><br>
                <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Local Ollama detected</div>
            """, unsafe_allow_html=True)
            if ollama_status["has_model"]:
                st.markdown("""
                    <div class="status-badge status-online">
                        <div class="status-dot dot-green"></div> QWEN 2.5 3B Ready
                    </div><br>
                    <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Model available locally</div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class="status-badge status-offline">
                        <div class="status-dot dot-red"></div> QWEN 2.5 3B Missing
                    </div><br>
                    <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Run: ollama pull qwen2.5:3b</div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="status-badge status-offline">
                    <div class="status-dot dot-red"></div> OLLAMA Offline
                </div><br>
                <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Local Ollama is not reachable</div>
            """, unsafe_allow_html=True)
            
            if ollama_status.get("error"):
                st.error(f"Browser Error: {ollama_status['error']}")
                
            st.markdown("""
                <div class="status-badge status-offline">
                    <div class="status-dot dot-red"></div> QWEN 2.5 3B Unavailable
                </div><br>
                <div style="font-size: 0.8rem; margin-bottom:15px; color:#94a3b8;">Start Ollama and install the model.</div>
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
def perform_analysis(url, mode):
    started_at = time.perf_counter()
    validate_github_url(url)
    
    timings = {}

    with tempfile.TemporaryDirectory() as temporary_folder:
        t0 = time.perf_counter()
        repository = clone_repository(
            url, str(Path(temporary_folder) / "repository")
        )
        timings["clone"] = time.perf_counter() - t0
        
        with repository:
            t1 = time.perf_counter()
            file_entries = list_repository_files(repository)
            if not file_entries:
                raise ValueError("The GitHub repository contains no tracked files.")

            structures, content_items, analysis_notes = inspect_repository_files(file_entries)
            repository_type = detect_repository_type(file_entries, content_items)
            timings["scanning"] = time.perf_counter() - t1
            
            t2 = time.perf_counter()
            context, analyzed_paths = build_model_context(file_entries, content_items, structures, mode)
            timings["context"] = time.perf_counter() - t2
            
            if len(file_entries) >= MAX_DISCOVERED_FILES:
                analysis_notes.append("File discovery safety limit reached. Inventory may be incomplete.")

            binary_files = get_binary_inventory(file_entries)
            
            repository_name = urlparse(url).path.rstrip("/").split("/")[-1]
            if repository_name.endswith(".git"):
                repository_name = repository_name[:-4]
                
            t3 = time.perf_counter()
            if "Ollama" in mode:
                explanation = None
                req_count = 0
            else:
                explanation, req_count = explain_repository_contents(
                    repository_name,
                    repository_type,
                    context,
                    analysis_notes,
                    mode
                )
            timings["llm_request"] = time.perf_counter() - t3
            timings["total"] = time.perf_counter() - started_at

            return {
                "context_for_ollama": context,
                "repository_name": repository_name,
                "repository_type": repository_type,
                "analysis_notes": analysis_notes,
                "timings": timings,
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
                "analysis_time_seconds": round(timings["total"], 2),
                "timings": timings,
                "explanation": explanation,
            }

if analyze_btn:
    if not github_url.strip():
        st.error("Please enter a valid GitHub repository URL.")
    else:
        # Professional Error Handling for Ollama mode before starting
        if "Ollama" in ai_mode:
            # We already have ollama_status from the sidebar component execution above
            pass
            if not ollama_status["running"]:
                st.error("⚠️ **Local Ollama is currently unavailable.**\n\n**Ollama endpoint:**\n`http://127.0.0.1:11434`\n\n**Required model:**\n`qwen2.5:3b`\n\n**Instruction:**\nStart Ollama and make sure qwen2.5:3b is installed.")
                st.stop()
            elif not ollama_status["has_model"]:
                st.error("⚠️ **Required model not found.**\n\n**Run:**\n`ollama pull qwen2.5:3b`")
                st.stop()
                
        with st.status("Analyzing Repository...", expanded=True) as status:
            try:
                st.write("🔍 Validating GitHub URL...")
                st.write("📥 Cloning repository & building inventory...")
                # The actual function call is cached, so it runs quickly if already done
                result = perform_analysis(github_url.strip(), ai_mode)
                
                if "Ollama" in ai_mode:
                    st.write("🧠 Context preparation complete. Querying Local Ollama (Qwen 2.5 3B) via browser...")
                    st.session_state["pending_ollama_result"] = result
                    st.session_state["ollama_gen_id"] = str(uuid.uuid4())
                    st.session_state["ollama_request_started_at"] = time.perf_counter()
                else:
                    st.write("🧠 Context preparation complete. Generating Cloud AI explanation...")
                    st.session_state["last_result"] = result
                    
                status.update(label="Analysis Complete!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Analysis Failed", state="error", expanded=False)
                st.error(f"Error during analysis: {str(e)}")


# If there is a pending Ollama generation, render the component
if "pending_ollama_result" in st.session_state:
    st.info("Generating explanation with Local Qwen 2.5 3B via your browser... (This may take a minute depending on your hardware)")
    
    from backend.llm_service import build_prompt
    r = st.session_state["pending_ollama_result"]
    prompt = build_prompt(
        r['repository_name'],
        r['repository_type'],
        r['context_for_ollama'],
        r['analysis_notes'],
        local_ollama=True,
    )
    
    gen_result = ollama_connector(
        action="generate", 
        payload={
            "model": "qwen2.5:3b",
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "num_predict": 1000,
                "temperature": 0.2,
                "num_ctx": 4096,
            },
        },
        request_id=st.session_state["ollama_gen_id"], 
        key="ollama_gen_comp"
    )
    if gen_result is not None:
        ollama_request_seconds = (
            time.perf_counter() - st.session_state.pop("ollama_request_started_at")
        )
        timings = r.setdefault("timings", {})
        timings["llm_request"] = ollama_request_seconds
        timings["total"] = timings.get("total", 0) + ollama_request_seconds
        r["analysis_time_seconds"] = round(timings["total"], 2)
        if gen_result.get("status") == "success":
            r["explanation"] = gen_result.get("response", "")
            st.session_state["last_result"] = r
        else:
            st.error(f"Browser Ollama Error: {gen_result.get('error')}")
        del st.session_state["pending_ollama_result"]
        st.rerun()

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
    if c12.button("Local Ollama", use_container_width=True, type="primary" if st.session_state.active_tab == "Local Ollama" else "secondary"): st.session_state.active_tab = "Local Ollama"
    
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
        st.markdown(f"- **Limits Reached**: {'Yes' if 'safety limit' in str(res['analysis_notes']) else 'No'}")
        
        st.markdown("#### Performance Breakdown")
        t = res.get("timings", {})
        if t:
            st.markdown(f"- **Repository Clone:** {t.get('clone', 0):.2f}s")
            st.markdown(f"- **Repository Scanning:** {t.get('scanning', 0):.2f}s")
            st.markdown(f"- **Context Building:** {t.get('context', 0):.2f}s")
            st.markdown(f"- **Ollama/Cloud Request:** {t.get('llm_request', 0):.2f}s")
            st.markdown(f"- **Total Analysis Time:** {t.get('total', res['analysis_time_seconds']):.2f}s")
            
        if res["analysis_notes"]:
            st.markdown("#### Analysis Notes")
            for note in res["analysis_notes"]:
                st.markdown(f'<div class="warning-box">⚠️ {html.escape(note)}</div>', unsafe_allow_html=True)
        st.markdown("#### Limitations")
        st.markdown(extract_section(exp, "Limitations"))
                
    elif selected_tab == "Setup":
        st.markdown("### Setup & Deployment")
        st.markdown(extract_section(exp, "Setup"))
        
    elif selected_tab == "Local Ollama":
        st.markdown("### Local Ollama")
        
        if "check_id_tab" not in st.session_state:
            st.session_state["check_id_tab"] = str(uuid.uuid4())
        
        status_res_tab = ollama_connector(action="check_status", request_id=st.session_state["check_id_tab"], key="ollama_status_tab")
        if status_res_tab is None:
            ollama_status = {"running": False, "has_model": False, "error": None}
        else:
            ollama_status = {
                "running": status_res_tab.get("running", False), 
                "has_model": status_res_tab.get("has_model", False),
                "error": status_res_tab.get("error")
            }
        
        st.markdown(f"**Ollama:** {'🟢 Connected' if ollama_status['running'] else '🔴 Offline'}")
        st.markdown(f"**Model (`qwen2.5:3b`):** {'🟢 Available' if ollama_status['has_model'] else '🔴 Not Found'}")
        st.markdown("**Endpoint:** `http://127.0.0.1:11434`")
        
        if ollama_status.get("error"):
            st.error(f"Diagnostic Error: {ollama_status['error']}\n\n(This usually means your browser blocked the connection due to Mixed Content / Private Network policies, or CORS is missing.)")
            
        st.markdown("---")
        st.markdown("#### How Local Ollama Works")
        st.markdown("""
        GitHub Repository  
        ↓  
        Repository Analysis  
        ↓  
        Smart Context  
        ↓  
        Local Ollama  
        ↓  
        Qwen 2.5 3B  
        ↓  
        Repository Explanation
        """)
        
        if not ollama_status["running"] or not ollama_status["has_model"]:
            st.markdown("---")
            st.markdown("#### How to install and use Local Ollama")
            st.markdown("""
**STEP 1 — INSTALL OLLAMA**  
Ollama is the local AI runtime required to run Qwen 2.5 3B directly on your own computer.  
Download and install Ollama for your operating system from the official website: [ollama.com](https://ollama.com)

**STEP 2 — START OLLAMA (IMPORTANT: CORS SETUP)**  
Because CodeLens AI is hosted on Streamlit Cloud (`https://repo-code-explainer.streamlit.app`), your browser will block it from talking to your local Ollama for security reasons (Cross-Origin Resource Sharing). 
To allow this website to use your local Ollama, you must start Ollama from your terminal with this exact command:
* **Mac/Linux:** `OLLAMA_ORIGINS="https://repo-code-explainer.streamlit.app" ollama serve`
* **Windows (Command Prompt):** `set OLLAMA_ORIGINS="https://repo-code-explainer.streamlit.app" && ollama serve`

**STEP 3 — INSTALL QWEN 2.5 3B**  
Open a *new* terminal window and download the required model locally:  
`ollama pull qwen2.5:3b`

**STEP 4 — VERIFY THE MODEL**  
Run:  
`ollama list`  
Ensure that `qwen2.5:3b` appears in the list.

**STEP 5 — TEST THE MODEL**  
Run:  
`ollama run qwen2.5:3b`  
Type a quick message like "hello" to verify that Qwen is responding locally.

**STEP 6 — RETURN TO CODELENS AI**  
Refresh this deployed CodeLens AI webpage in your browser. Select **Local Ollama + Qwen 2.5 3B**. 
You should now see:
* 🟢 Ollama ONLINE
* 🟢 Qwen 2.5 3B AVAILABLE

**STEP 7 — ANALYZE**  
Only after both checks succeed, you can enter a GitHub URL and click Analyze. Your browser will send the code directly to your local Ollama!
            """)