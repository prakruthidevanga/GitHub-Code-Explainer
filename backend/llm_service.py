"""Ask a cloud LLM model to explain files and summarize the repository."""
import os
import re
import logging
import time
import requests

logger = logging.getLogger(__name__)

PRIMARY_PROVIDER = os.getenv("PRIMARY_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
MAX_OUTPUT_TOKENS = 6000

class CloudLLMError(RuntimeError): pass
class OllamaUnavailableError(CloudLLMError): pass
class OllamaModelError(CloudLLMError): pass
class OllamaTimeoutError(CloudLLMError): pass
class OllamaResponseError(CloudLLMError): pass

def _call_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise OllamaUnavailableError("GROQ_API_KEY is not set.")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": MAX_OUTPUT_TOKENS}
    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    except requests.Timeout as e:
        raise OllamaTimeoutError("Groq request timed out.") from e
    except requests.RequestException as e:
        raise OllamaUnavailableError(f"Could not connect to Groq: {e}") from e

    if not response.ok:
        raise OllamaResponseError(f"Groq API error {response.status_code}: {response.text[:300]}")
    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError) as e:
        raise OllamaResponseError("Invalid response format from Groq.") from e

def _call_hf(prompt: str) -> str:
    if not HF_TOKEN:
        raise OllamaUnavailableError("HF_TOKEN is not set.")
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "model": HF_MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful repository code explainer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False
    }
    try:
        response = requests.post("https://router.huggingface.co/v1/chat/completions", headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    except requests.Timeout as e:
        raise OllamaTimeoutError("HuggingFace request timed out.") from e
    except requests.RequestException as e:
        raise OllamaUnavailableError(f"Could not connect to HuggingFace: {e}") from e

    if response.status_code == 503:
        raise OllamaUnavailableError("HuggingFace model is currently loading. Please try again shortly.")
    if not response.ok:
        raise OllamaResponseError(f"HuggingFace API error {response.status_code}: {response.text[:300]}")
    try:
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError) as e:
        raise OllamaResponseError("Invalid JSON or response format from HuggingFace.") from e

def _call_cloud_llm(prompt: str) -> str:
    providers = [("groq", _call_groq), ("huggingface", _call_hf)] if PRIMARY_PROVIDER == "groq" else [("huggingface", _call_hf), ("groq", _call_groq)]
    last_error = None
    for name, func in providers:
        try:
            logger.info("Attempting LLM generation with %s", name)
            return func(prompt)
        except CloudLLMError as e:
            logger.warning("%s provider failed: %s", name, e)
            last_error = e
    raise last_error or OllamaResponseError("No cloud LLM providers available.")

def _call_ollama(prompt: str) -> str:
    status = check_ollama_status()
    if not status["running"]:
        raise OllamaUnavailableError("Local Ollama is currently unavailable.\nPlease start Ollama and run: ollama pull qwen2.5:3b")
    if not status["has_model"]:
        raise OllamaModelError("qwen2.5:3b is not installed.\nPlease run: ollama pull qwen2.5:3b")
        
    payload = {
        "model": "qwen2.5:3b", 
        "prompt": prompt, 
        "stream": False,
        "keep_alive": "5m",
        "options": {"num_ctx": 8192}
    }
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=LLM_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.RequestException as e:
        raise OllamaResponseError(f"Ollama generation failed: {e}")

def check_ollama_status():
    """Check if local Ollama is running and has the model."""
    try:
        res = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if res.status_code == 200:
            models = [m.get("name") for m in res.json().get("models", [])]
            has_model = any(m.startswith("qwen2.5:3b") for m in models)
            return {"running": True, "has_model": has_model}
        return {"running": True, "has_model": False}
    except requests.RequestException:
        return {"running": False, "has_model": False}

def explain_repository_contents(repository_name, repository_type, context, notes, ai_mode="Cloud AI (Default)"):
    prompt_started = time.perf_counter()
    prompt = f"""You are CodeLens AI, an expert software architecture and repository explainer.
Analyze this public GitHub repository deeply and explain it using ONLY the provided evidence.
Do NOT generate generic descriptions. Explain the ACTUAL contents of this specific repository.
Never invent files, functions, APIs, or architectures. If something cannot be determined, explicitly state: "This could not be determined from the available repository content."

Repository name: {repository_name}
Repository type: {repository_type}

Analysis notes:
{chr(10).join(notes) if notes else "None"}

Repository evidence (file inventory, structural summaries, and selected excerpts):
{context}

Return a MASSIVE, highly detailed Markdown report strictly following these exact headings. Do not include any extra chat text.

# Overview
What is this specific project and what problem does it solve? What are its major features?

# Architecture
Explain the ACTUAL architecture of this submitted repository. Show the relationship between major components (e.g., User -> UI -> Backend -> DB).

# Files & Folders
For EACH important file discovered, provide:
1. File name & path
2. Purpose of the file
3. What the file contains
4. Important classes and functions
5. How it connects to other files and its overall role.

# Technologies
Detect and list the specific programming languages, frameworks, libraries, databases, and tools used in this repository. Cite the evidence (e.g., "FastAPI found in requirements.txt").

# Code Analysis
Identify ACTUAL classes, functions, methods, and modules. For each important function/class, explain:
- What it is and what it does
- How it works
- What it receives (Inputs) and what it returns (Outputs)
- What it calls and why it matters

# Workflow
Explain the complete end-to-end workflow step by step, from user input to final output, based on the ACTUAL implementation in the code.

# Dependencies
List actual dependencies found in requirements.txt, package.json, etc. Explain the purpose of each key dependency and where it is used.

# Setup
How is the project configured, run, and deployed based on the evidence?

# AI Explanation
Provide a comprehensive, beginner-friendly but technically accurate explanation of the ENTIRE repository covering its overview, purpose, problem solved, features, structure, architecture, data flow, error handling, and technical decisions. Write this so a BCA student could use it for a project viva.

# Limitations
What important information cannot be determined from this repository content?
"""
    logger.info("Cloud LLM prompt prepared in %.2fs (%d chars)", time.perf_counter() - prompt_started, len(prompt))
    
    if "Ollama" in ai_mode:
        answer = _call_ollama(prompt)
    else:
        answer = _call_cloud_llm(prompt)
        
    return answer, 1

