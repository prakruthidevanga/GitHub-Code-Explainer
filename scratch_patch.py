import uuid

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add component import
code = code.replace("import tempfile", "import tempfile\nimport uuid\nfrom frontend.ollama_connector import ollama_connector")

# 2. Modify check_ollama_status usage in SIDEBAR
status_target = """        # Check Local Ollama
        ollama_status = check_ollama_status()"""
status_replacement = """        # Check Local Ollama via Browser
        if "check_id" not in st.session_state:
            st.session_state["check_id"] = str(uuid.uuid4())
        
        status_res = ollama_connector(action="check_status", request_id=st.session_state["check_id"], key="ollama_status_sidebar")
        if status_res is None:
            ollama_status = {"running": False, "has_model": False}
        else:
            ollama_status = {"running": status_res.get("running", False), "has_model": status_res.get("has_model", False)}
"""
code = code.replace(status_target, status_replacement)

# Error handling block
status_target_2 = """        # Professional Error Handling for Ollama mode before starting
        if "Ollama" in ai_mode:
            ollama_status = check_ollama_status()"""
status_replacement_2 = """        # Professional Error Handling for Ollama mode before starting
        if "Ollama" in ai_mode:
            # We already have ollama_status from the sidebar component execution above
            pass"""
code = code.replace(status_target_2, status_replacement_2)

# Tab block
status_target_3 = """    elif selected_tab == "Local Ollama":
        st.markdown("### Local Ollama")
        
        ollama_status = check_ollama_status()"""
status_replacement_3 = """    elif selected_tab == "Local Ollama":
        st.markdown("### Local Ollama")
        
        if "check_id_tab" not in st.session_state:
            st.session_state["check_id_tab"] = str(uuid.uuid4())
        
        status_res_tab = ollama_connector(action="check_status", request_id=st.session_state["check_id_tab"], key="ollama_status_tab")
        if status_res_tab is None:
            ollama_status = {"running": False, "has_model": False}
        else:
            ollama_status = {"running": status_res_tab.get("running", False), "has_model": status_res_tab.get("has_model", False)}"""
code = code.replace(status_target_3, status_replacement_3)


# 3. Modify perform_analysis to NOT call LLM if mode is Ollama
perform_analysis_target = """            t3 = time.perf_counter()
            explanation, req_count = explain_repository_contents(
                repository_name,
                repository_type,
                context,
                analysis_notes,
                mode
            )
            timings["llm_request"] = time.perf_counter() - t3
            timings["total"] = time.perf_counter() - started_at

            return {"""
            
perform_analysis_replacement = """            t3 = time.perf_counter()
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
                "timings": timings,"""

code = code.replace(perform_analysis_target, perform_analysis_replacement)

# 4. Handle the analyze_btn flow
analyze_target = """                # The actual function call is cached, so it runs quickly if already done
                result = perform_analysis(github_url.strip(), ai_mode)
                
                if "Ollama" in ai_mode:
                    st.write("🧠 Context preparation complete. Querying Local Ollama (Qwen 2.5 3B)...")
                else:
                    st.write("🧠 Context preparation complete. Generating Cloud AI explanation...")
                
                st.session_state["last_result"] = result
                status.update(label="Analysis Complete!", state="complete", expanded=False)
            except Exception as e:"""

analyze_replacement = """                # The actual function call is cached, so it runs quickly if already done
                result = perform_analysis(github_url.strip(), ai_mode)
                
                if "Ollama" in ai_mode:
                    st.write("🧠 Context preparation complete. Querying Local Ollama (Qwen 2.5 3B) via browser...")
                    st.session_state["pending_ollama_result"] = result
                    st.session_state["ollama_gen_id"] = str(uuid.uuid4())
                else:
                    st.write("🧠 Context preparation complete. Generating Cloud AI explanation...")
                    st.session_state["last_result"] = result
                    
                status.update(label="Analysis Complete!", state="complete", expanded=False)
            except Exception as e:"""
code = code.replace(analyze_target, analyze_replacement)

# 5. Put the generation connector call at the top level
gen_component_code = """
# If there is a pending Ollama generation, render the component
if "pending_ollama_result" in st.session_state:
    st.info("Generating explanation with Local Qwen 2.5 3B via your browser... (This may take a minute depending on your hardware)")
    
    from backend.llm_service import SYSTEM_PROMPT
    r = st.session_state["pending_ollama_result"]
    prompt = f"{SYSTEM_PROMPT}\\n\\nRepository Name: {r['repository_name']}\\nType: {r['repository_type']}\\n\\nNotes:\\n" + "\\n".join(r['analysis_notes']) + f"\\n\\nContext:\\n{r['context_for_ollama']}"
    
    gen_result = ollama_connector(
        action="generate", 
        payload={"model": "qwen2.5:3b", "prompt": prompt, "stream": False, "keep_alive": "5m", "options": {"num_ctx": 4096}}, 
        request_id=st.session_state["ollama_gen_id"], 
        key="ollama_gen_comp"
    )
    if gen_result is not None:
        if gen_result.get("status") == "success":
            r["explanation"] = gen_result.get("response", "")
            st.session_state["last_result"] = r
        else:
            st.error(f"Browser Ollama Error: {gen_result.get('error')}")
        del st.session_state["pending_ollama_result"]
        st.experimental_rerun()

# Results Display
if "last_result" in st.session_state:
"""
code = code.replace("# Results Display\nif \"last_result\" in st.session_state:", gen_component_code)

# 6. EXACT Setup Replacement string match
old_setup = """        if not ollama_status["running"] or not ollama_status["has_model"]:
            st.markdown("---")
            st.markdown("#### Setup Instructions")
            st.markdown(\"\"\"
            **Step 1** — Install Ollama (from ollama.com)  
            **Step 2** — Start Ollama  
            **Step 3** — Install the required model:  
            `ollama pull qwen2.5:3b`  
            **Step 4** — Verify:  
            `ollama list`  
            **Step 5** — Return to CodeLens AI and select **Local Ollama + Qwen 2.5 3B**
            \"\"\")"""

new_setup = """        if not ollama_status["running"] or not ollama_status["has_model"]:
            st.markdown("---")
            st.markdown("#### How to install and use Local Ollama")
            st.markdown(\"\"\"
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
            \"\"\")"""

code = code.replace(old_setup, new_setup)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)
