''' Give the provider and model return worker '''

from .llm_stream_openai_worker import call_llm_stream_openai_worker

from .config import provider_models_supported, url_provider

# The number key are related to the provider_name, model_name in config.py
# Is a convienent way to map the provider and model to worker without using the handler in config.py

handler_map: dict[int, callable] = {
    1: call_llm_stream_openai_worker,
    # Add more workers here with consecutive numbers
}


def get_provider_url(provider_name: str):
    provider = url_provider.get(provider_name, None)

    if provider:
        return provider
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")

def get_llm_provider_worker(provider: str, model: str):
    return handler_map[provider_models_supported[provider][model]]