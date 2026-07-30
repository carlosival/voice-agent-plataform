from workflows.steps.llm.config import url_provider

def get_provider_url(provider: str):
    return url_provider[provider]