import pytest
from unittest.mock import patch, MagicMock
from backend.repo_processor import validate_github_url
from backend.llm_service import _call_cloud_llm, OllamaResponseError, OllamaUnavailableError, explain_repository_contents
import backend.llm_service
from app import analyze_github_repository

def test_validate_github_url():
    with pytest.raises(ValueError):
        validate_github_url("https://google.com")
    assert validate_github_url("https://github.com/user/repo") is None

@patch("backend.llm_service.requests.post")
def test_cloud_llm_groq_success(mock_post, monkeypatch):
    monkeypatch.setattr(backend.llm_service, "PRIMARY_PROVIDER", "groq")
    monkeypatch.setattr(backend.llm_service, "GROQ_API_KEY", "test-key")
    
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"choices": [{"message": {"content": "Test response"}}]}
    mock_post.return_value = mock_response
    
    result = _call_cloud_llm("test prompt")
    assert result == "Test response"

@patch("backend.llm_service.requests.post")
def test_cloud_llm_hf_success(mock_post, monkeypatch):
    monkeypatch.setattr(backend.llm_service, "PRIMARY_PROVIDER", "huggingface")
    monkeypatch.setattr(backend.llm_service, "HF_TOKEN", "test-token")
    
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = [{"generated_text": "HF response"}]
    mock_post.return_value = mock_response
    
    result = _call_cloud_llm("test prompt")
    assert result == "HF response"

@patch("backend.llm_service.requests.post")
def test_cloud_llm_fallback(mock_post, monkeypatch):
    monkeypatch.setattr(backend.llm_service, "PRIMARY_PROVIDER", "groq")
    monkeypatch.setattr(backend.llm_service, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(backend.llm_service, "HF_TOKEN", "test-token")
    
    mock_groq_fail = MagicMock()
    mock_groq_fail.ok = False
    mock_groq_fail.status_code = 500
    mock_groq_fail.text = "Error"
    
    mock_hf_success = MagicMock()
    mock_hf_success.ok = True
    mock_hf_success.json.return_value = [{"generated_text": "Fallback HF response"}]
    
    mock_post.side_effect = [mock_groq_fail, mock_hf_success]
    
    result = _call_cloud_llm("test prompt")
    assert result == "Fallback HF response"

@patch("backend.llm_service.requests.post")
def test_cloud_llm_empty_response(mock_post, monkeypatch):
    monkeypatch.setattr(backend.llm_service, "PRIMARY_PROVIDER", "groq")
    monkeypatch.setattr(backend.llm_service, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(backend.llm_service, "HF_TOKEN", "test-token")
    
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {}
    mock_post.return_value = mock_response
    
    with pytest.raises(OllamaResponseError):
        _call_cloud_llm("test prompt")

@patch("backend.llm_service._call_cloud_llm")
def test_explain_repository_contents(mock_call):
    mock_call.return_value = "Full Report"
    explanation, count = explain_repository_contents("test-repo", "python", "context", ["note1"])
    assert explanation == "Full Report"
    assert count == 1
    mock_call.assert_called_once()
    
@patch("app.clone_repository")
@patch("app.list_repository_files")
@patch("app.inspect_repository_files")
@patch("app.detect_repository_type")
@patch("app.build_model_context")
@patch("app.get_binary_inventory")
@patch("app.explain_repository_contents")
def test_analyze_github_repository(mock_explain, mock_binary, mock_build, mock_detect, mock_inspect, mock_list, mock_clone):
    mock_clone.return_value.__enter__.return_value = MagicMock()
    mock_list.return_value = [{"path": "main.py", "name": "main.py", "type": "blob", "size_bytes": 100, "extension": ".py", "category": "Source Code"}]
    mock_inspect.return_value = ({"main.py": {"structure": {}, "size_bytes": 100}}, [{"path": "main.py"}], [])
    mock_detect.return_value = "Python"
    mock_build.return_value = ("Context", {"main.py"})
    mock_binary.return_value = []
    mock_explain.return_value = ("Final Report", 1)
    
    result = analyze_github_repository("https://github.com/test/repo")
    assert result["success"] is True
    assert result["explanation"] == "Final Report"
    assert result["llm_provider"] == "Cloud AI"
    assert result["llm_requests"] == 1
