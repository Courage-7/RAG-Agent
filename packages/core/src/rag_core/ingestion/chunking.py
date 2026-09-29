"""Document chunking models and recursive text splitting strategies."""

from pydantic import BaseModel, ConfigDict, Field


class TextChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    content: str = Field(min_length=1)
    token_count: int | None = Field(default=None, ge=0)


class RecursiveCharacterChunker:
    """Recursively splits text using hierarchical separators to preserve semantic context."""

    def __init__(
        self,
        *,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: tuple[str, ...] = ("\n\n", "\n", ". ", " ", ""),
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators

    def _split_text(self, text: str, separators: tuple[str, ...]) -> list[str]:
        final_chunks: list[str] = []
        separator = separators[-1]
        new_separators: tuple[str, ...] = ()

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)
        good_splits: list[str] = []

        for s in splits:
            if not s:
                continue
            if len(s) < self.chunk_size:
                good_splits.append(s)
            elif new_separators:
                other_info = self._split_text(s, new_separators)
                good_splits.extend(other_info)
            else:
                good_splits.append(s)

        # Merge good_splits into chunks respecting chunk_size and chunk_overlap
        current_chunk: list[str] = []
        current_length = 0

        for piece in good_splits:
            piece_len = len(piece) + (len(separator) if current_chunk else 0)
            if current_length + piece_len <= self.chunk_size:
                current_chunk.append(piece)
                current_length += piece_len
            else:
                if current_chunk:
                    merged = separator.join(current_chunk).strip()
                    if merged:
                        final_chunks.append(merged)
                    # Handle overlap by keeping tail pieces
                    overlap_len = 0
                    overlap_chunk: list[str] = []
                    for p in reversed(current_chunk):
                        if overlap_len + len(p) <= self.chunk_overlap:
                            overlap_chunk.insert(0, p)
                            overlap_len += len(p)
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_length = sum(len(p) for p in current_chunk)
                current_chunk.append(piece)
                current_length += len(piece)

        if current_chunk:
            merged = separator.join(current_chunk).strip()
            if merged:
                final_chunks.append(merged)

        return final_chunks

    def split(self, text: str) -> list[TextChunk]:
        """Split text into an ordered list of TextChunk objects."""
        stripped = text.strip()
        if not stripped:
            return []

        raw_chunks = self._split_text(stripped, self.separators)
        return [
            TextChunk(index=i, content=chunk) for i, chunk in enumerate(raw_chunks) if chunk.strip()
        ]
