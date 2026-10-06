# CodeLens AI — AI GitHub Repository Intelligence

## Problem Statement
Understanding an unfamiliar public GitHub project can be difficult, especially when the README is sparse or the codebase is complex. Reading every file manually is time-consuming, and simply passing raw files to an LLM quickly exceeds context limits and API constraints.

## Solution
CodeLens AI is a code exploration tool that clones and locally processes a GitHub repository to build an intelligent, structural summary of the code. It then sends this compact repository evidence to a cloud LLM to generate a complete, beginner-friendly explanation of the project in a single response. 

## Features
- **Public GitHub Analysis**: Enter any public repository URL to get an instant explanation.
- **Smart Repository Processing**: Performs local static analysis to build a structural inventory (imports, classes, functions) without executing the code.
- **Secret Protection**: Automatically masks common API keys, tokens, and credentials in the source code before sending data to the cloud.
- **Single Cloud LLM Request**: Avoids sequential LLM calls by constructing one optimized prompt, resulting in fast analysis.
- **Cloud Provider Abstraction**: Seamlessly switches between Groq and Hugging Face inference based on configuration.
- **Professional UI**: Built with Streamlit for an interactive and clean user experience.

## Architecture
1. **Streamlit UI**: The user enters a GitHub URL.
2. **Repository Processor**: 
   - Clones the repository locally (shallow clone / Git object inspection).
   - Filters out ignored directories, caches, and binaries.
   - Extracts AST and metadata from supported source files.
   - Applies secret masking.
   - Prioritizes core files (e.g., entry points, README, config).
3. **Cloud LLM Client**:
   - Takes the structured repository context and selected file excerpts.
   - Sends a single structured prompt to the configured Cloud Provider (Groq or Hugging Face).
4. **Final Report**: Receives the Markdown response and displays the 1-2 minute explanation, architecture details, execution flow, and final summary.

## Cloud Inference & Performance Strategy
Instead of making one LLM request per file, CodeLens AI compresses the repository into a structured format (inventory + core excerpts) and makes **ONE** LLM request. This ensures the analysis is fast (typically 30-90 seconds) and minimizes API usage.

## Security
- **No Code Execution**: The app only reads and parses files statically.
- **Secret Masking**: Hardcoded secrets in the repository are scrubbed before reaching the LLM.
- **Prompt Injection Protection**: The LLM is instructed to treat all repository content as untrusted evidence.

## Public Deployment & Streamlit Cloud Setup
This application is designed to be hosted on Streamlit Community Cloud. 

1. Deploy the app to Streamlit Cloud.
2. Navigate to **App settings > Secrets**.
3. Add your provider credentials:

### Secrets Configuration
```toml
# .streamlit/secrets.toml
PRIMARY_PROVIDER = "groq"
GROQ_API_KEY = "YOUR_GROQ_API_KEY"
# HF_TOKEN = "YOUR_HUGGING_FACE_TOKEN"
```

## Local Development
To run the application locally:
1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Add your credentials to `.streamlit/secrets.toml`.
4. Run the app: `streamlit run frontend/app.py`

### Optional Ollama Mode
The application currently defaults to cloud inference. To use local Ollama, you would need to modify the `PRIMARY_PROVIDER` logic in `backend/llm_service.py` to route to a local `http://localhost:11434` endpoint and have `Ollama` running.

## Limitations
- **Repository Size**: Very large repositories will have their file lists truncated and only the most important files deeply analyzed due to LLM context window limits.
- **Untrusted Code**: While secrets are masked, users should avoid analyzing malicious repositories if concerned about complex prompt injection.

## Testing
Run the Python test suite if available:
```bash
python -m pytest
```

## Usage
1. Open the CodeLens AI public URL.
2. Paste a GitHub repository URL.
3. Click "Analyze Repository".
4. Read the generated 1-2 minute explanation and deep architectural insights.
