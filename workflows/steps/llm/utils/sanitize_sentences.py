from workflows.steps.llm.config import BAD_PATTERNS, SENTENCE_ENDS

def sanitize_sentence(text: str) -> str:
        """
        Cleans up a complete sentence before handing it to the TTS engine.
        """
        if not text:
            return ""
        
        # 1. Remove systemic noise, tags, and markdown formatting
        cleaned = text
        for pattern in BAD_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned)
            
        # 2. Normalize text numbers or symbols that sound weird when spoken
        cleaned = cleaned.replace("%", " por ciento")
        cleaned = cleaned.replace("&", " y ")
        
        # 3. Clean up accidental double spaces left behind by removals
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        return cleaned