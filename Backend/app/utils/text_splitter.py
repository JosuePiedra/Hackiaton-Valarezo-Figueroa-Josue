def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Splits text into overlapping segments, preferring to cut on a newline."""
    if len(text) <= size:
        return [text]
    segments = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            segments.append(text[start:])
            break
        newline = text.rfind("\n", start + size - overlap, end)
        if newline > start:
            end = newline
        segments.append(text[start:end])
        start = end - overlap
    return segments
