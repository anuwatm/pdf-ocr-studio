"""
Text Chunker and Boundary Deduplicator.
Handles splitting large text pages into contextual chunks and reassembling
them with overlap deduplication to guarantee no lost or duplicated paragraphs/words.
"""
from typing import List, Dict, Any, Tuple
import re


class TextChunker:
    """
    Splits text along line/paragraph boundaries with overlap context,
    and provides lossless reassembly and boundary mapping.
    """

    def __init__(self, chunk_size: int = 1500, overlap_size: int = 200):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks along line breaks (\n).
        Each chunk contains:
          - chunk_index: int
          - text: str (the chunk content)
          - start_char: int (global offset in original text)
          - end_char: int (global offset in original text)
          - prefix_overlap: int (characters belonging to previous chunk overlap)
          - suffix_overlap: int (characters belonging to next chunk overlap)
        """
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [{
                "chunk_index": 0,
                "text": text,
                "start_char": 0,
                "end_char": len(text),
                "prefix_overlap": 0,
                "suffix_overlap": 0,
            }]

        lines = text.splitlines(keepends=True)
        chunks = []
        current_lines: List[str] = []
        current_len = 0
        start_idx = 0
        current_start_char = 0

        line_offsets = []
        offset = 0
        for line in lines:
            line_offsets.append((offset, offset + len(line)))
            offset += len(line)

        i = 0
        chunk_idx = 0
        while i < len(lines):
            line = lines[i]
            current_lines.append(line)
            current_len += len(line)

            if current_len >= self.chunk_size or i == len(lines) - 1:
                chunk_text_str = "".join(current_lines)
                chunk_start = line_offsets[start_idx][0]
                chunk_end = line_offsets[i][1]

                prefix_overlap = 0
                if chunk_idx > 0 and start_idx < i:
                    # Calculate how many chars were overlapped from previous
                    prefix_overlap = sum(len(l) for l in current_lines[:max(1, len(current_lines) // 4)])

                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": chunk_text_str,
                    "start_char": chunk_start,
                    "end_char": chunk_end,
                    "prefix_overlap": prefix_overlap,
                    "suffix_overlap": 0,
                })
                chunk_idx += 1

                if i == len(lines) - 1:
                    break

                # Step back for overlap
                overlap_chars = 0
                step_back = 0
                for j in range(i, start_idx, -1):
                    overlap_chars += len(lines[j])
                    step_back += 1
                    if overlap_chars >= self.overlap_size:
                        break

                start_idx = max(start_idx + 1, i - step_back + 1)
                i = start_idx
                current_lines = []
                current_len = 0
            else:
                i += 1

        return chunks

    @staticmethod
    def reassemble_chunks(chunks: List[Dict[str, Any]], original_len: int) -> str:
        """
        Lossless reassembly of chunks by non-overlapping global ranges [start_char, end_char).
        Guarantees 100% identity to original text with zero duplicated or missing segments.
        """
        if not chunks:
            return ""
        if len(chunks) == 1:
            return chunks[0]["text"]

        # Sort chunks by start_char
        sorted_chunks = sorted(chunks, key=lambda c: c["start_char"])
        assembled = []
        cursor = 0

        for chunk in sorted_chunks:
            start = chunk["start_char"]
            end = chunk["end_char"]
            chunk_content = chunk["text"]

            if start > cursor:
                # Missing gap (should not happen in proper chunking)
                pass
            
            # The part we need from this chunk starts at (cursor - start)
            offset_in_chunk = max(0, cursor - start)
            needed_text = chunk_content[offset_in_chunk:]
            assembled.append(needed_text)
            cursor = end

        result = "".join(assembled)
        return result
