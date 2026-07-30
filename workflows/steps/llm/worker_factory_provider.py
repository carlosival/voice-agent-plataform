''' Give the provider and model return worker '''

from workflows.steps.llm.workers.llm_openai import call_llm_openai

from workflows.steps.llm.config import handler_provider, url_provider


handler_map: dict[int, callable] = {
    1: call_llm_openai,

}


def get_provider_url(provider: str):
    return url_provider[provider]

def get_worker(provider: str, model: str):
    return handler_map[handler_provider[provider][model]]