def make_tts_payload(
    provider: str,
    model: str,
    voice: str,
    text: str,
    sample_rate: int,
) -> dict:
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
    }

    if provider == "speaches":
        payload.update({
            "response_format": "pcm",
            "sample_rate": sample_rate,
        })

    elif provider == "groq":
        payload.update({
            "response_format": "wav",
            "sample_rate": sample_rate,
        })

    elif provider == "openai":
        payload.update({
            "response_format": "pcm",
        })

    else:
        raise ValueError(f"Unsupported provider: {provider}")

    return payload