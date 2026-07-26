"""Sentence-aware text chunking."""

from typing import List
from dataclasses import dataclass


@dataclass
class Chunk:
	"""A text chunk with position information."""
	text: str
	chunk_index: int
	char_start: int
	char_end: int


def chunk_text(
	text: str,
	chunk_size: int = 512,
	chunk_overlap: int = 50,
) -> List[Chunk]:
	"""
	Split text into overlapping chunks, respecting sentence boundaries.
	
	Uses LlamaIndex's SentenceSplitter under the hood for optimal chunking.
	"""
	try:
		from llama_index.core.node_parser import SentenceSplitter
		
		splitter = SentenceSplitter(
			chunk_size=chunk_size,
			chunk_overlap=chunk_overlap,
		)
		
		# LlamaIndex expects Document objects
		from llama_index.core import Document
		doc = Document(text=text)
		nodes = splitter.get_nodes_from_documents([doc])
		
		chunks = []
		for i, node in enumerate(nodes):
			chunks.append(Chunk(
				text=node.text,
				chunk_index=i,
				char_start=node.start_char_idx or 0,
				char_end=node.end_char_idx or len(node.text),
			))
		
		return chunks
		
	except ImportError:
		# Fallback to simple chunking if LlamaIndex not available
		return _simple_chunk(text, chunk_size, chunk_overlap)


def _simple_chunk(
	text: str,
	chunk_size: int,
	chunk_overlap: int,
) -> List[Chunk]:
	"""Simple fallback chunker without sentence awareness."""
	chunks = []
	start = 0
	chunk_index = 0
	
	while start < len(text):
		end = min(start + chunk_size, len(text))
		
		# Try to break at sentence boundary
		if end < len(text):
			for sep in [". ", "! ", "? ", "\n\n", "\n"]:
				last_sep = text.rfind(sep, start, end)
				if last_sep > start + chunk_size // 2:
					end = last_sep + len(sep)
					break
		
		chunk_text = text[start:end].strip()
		if chunk_text:
			chunks.append(Chunk(
				text=chunk_text,
				chunk_index=chunk_index,
				char_start=start,
				char_end=end,
			))
			chunk_index += 1
		
		start = end - chunk_overlap
		if start >= len(text) - chunk_overlap:
			break
	
	return chunks
