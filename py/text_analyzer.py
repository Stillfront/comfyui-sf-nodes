# ABOUTME: Analyzes text input and estimates token count for LLM usage planning.
# ABOUTME: Returns word count, estimated token count, and a formatted summary string.


class SFTextAnalyzer:
    """
    Analyzes text input and returns word count and estimated token count.
    Token count is an estimation based on character count (not exact Claude tokenization).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {"multiline": True, "default": "", "tooltip": "Text to analyze"},
                ),
            },
        }

    RETURN_TYPES = ("INT", "INT", "STRING")
    RETURN_NAMES = ("word_count", "token_estimate", "summary")
    FUNCTION = "analyze_text"
    CATEGORY = "Stillfront/Utils"

    DESCRIPTION = """
Analyzes text and returns:
- **word_count**: Actual word count
- **token_estimate**: Estimated Claude token count (approximate, based on char/4 rule)
- **summary**: Formatted text summary

Note: Token count is an estimation, not exact Claude tokenization.
"""

    def analyze_text(self, text):
        # Handle empty text
        if not text or not text.strip():
            return (0, 0, "Empty text - 0 words, ~0 tokens (estimated)")

        # Word count - split by whitespace and filter empty strings
        words = [word for word in text.split() if word.strip()]
        word_count = len(words)

        # Token estimation
        # Claude tokens are roughly 1 token per 4 characters (including spaces)
        # This is a rough approximation - actual tokenization can vary
        char_count = len(text)
        token_estimate = max(1, char_count // 4)  # Ensure at least 1 token

        # Create summary string
        summary = f"Words: {word_count} | Tokens: ~{token_estimate} (estimated)"

        return (word_count, token_estimate, summary)


# Node registration
NODE_CLASS_MAPPINGS = {
    "SFTextAnalyzer": SFTextAnalyzer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFTextAnalyzer": "SF Text Analyzer",
}
