import re

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

setup_replacement = """        if not ollama_status["running"] or not ollama_status["has_model"]:
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

# Regex substitution
code = re.sub(r'if not ollama_status\["running"\].*?\"\"\"\)', setup_replacement, code, flags=re.DOTALL)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)
