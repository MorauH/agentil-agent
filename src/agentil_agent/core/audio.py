

def split_text_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences for incremental TTS.
    
    Uses simple heuristics to split on sentence boundaries.
    
    Args:
        text: Text to split
        
    Returns:
        List of sentences
    """
    import re
    
    if not text:
        return []
    
    # Split on sentence-ending punctuation followed by space or end
    # Keep the punctuation with the sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # Filter out empty strings and clean up
    return [s.strip() for s in sentences if s.strip()]


class AudioBuffer:
    """
    Buffer for accumulating audio chunks.
    
    Used to collect incoming audio data from WebSocket before processing.
    """
    
    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._total_size = 0
    
    def add(self, chunk: bytes) -> None:
        """Add a chunk to the buffer."""
        self._chunks.append(chunk)
        self._total_size += len(chunk)
    
    def get_all(self) -> bytes:
        """Get all buffered data as a single bytes object."""
        return b"".join(self._chunks)
    
    def clear(self) -> None:
        """Clear the buffer."""
        self._chunks.clear()
        self._total_size = 0
    
    @property
    def size(self) -> int:
        """Total size of buffered data in bytes."""
        return self._total_size
    
    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self._total_size == 0

