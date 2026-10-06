import streamlit.components.v1 as components
import os

_component_func = components.declare_component(
    "ollama_connector", path=os.path.join(os.path.dirname(__file__))
)

def ollama_connector(action, request_id, payload=None, key=None):
    """
    Client-side Streamlit component to bypass server localhost mapping 
    and connect directly to the user's browser-local Ollama instance.
    """
    component_value = _component_func(
        action=action, 
        request_id=request_id, 
        payload=payload, 
        key=key, 
        default=None
    )
    return component_value
