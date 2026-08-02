
url_provider = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "groq": "https://api.groq.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "xai": "https://api.xai.com/v1",
}


handler_provider = {
    "openai": {
        "gpt-3.5-turbo": 1,
        
    },
    "groq": {
        "llama3.1:8b": 1,
    },
    "anthropic": 2,
    "google": 3,
    "xai": 4,
}


