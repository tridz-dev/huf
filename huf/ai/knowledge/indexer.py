"""Knowledge ingestion and indexing pipeline."""

import os
import frappe
from frappe import _
from frappe.utils import now_datetime

from .backends import get_backend
from .extractors import TextExtractor, ExtractedText
from .chunkers.sentence import chunk_text


def process_knowledge_input(knowledge_input: str) -> dict:
	"""
	Process a single knowledge input and add to index.
	
	This function is designed to run in a background job.
	"""
	doc = frappe.get_doc("Knowledge Input", knowledge_input)
	source = frappe.get_doc("Knowledge Source", doc.knowledge_source)
	
	try:
		# Update status
		doc.status = "Processing"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		
		# Acquire lock for this knowledge source
		lock_key = f"knowledge_index_{source.name}"
		if not frappe.cache().set(lock_key, 1, ex=300, nx=True):
			raise Exception(_("Another indexing operation is in progress"))
		
		try:
			# Update source status
			if source.status != "Indexing" and source.status != "Rebuilding":
				source.status = "Indexing"
				source.save(ignore_permissions=True)
				frappe.db.commit()
			
			# Extract text
			extracted = _extract_text(doc)
			
			# Chunk text
			chunks = chunk_text(
				text=extracted.text,
				chunk_size=source.chunk_size or 512,
				chunk_overlap=source.chunk_overlap or 50,
			)
			
			# Prepare chunk data
			chunk_data = []
			for chunk in chunks:
				chunk_data.append({
					"input_id": doc.name,
					"input_type": doc.input_type,
					"source_title": extracted.title or doc.file_name,
					"chunk_index": chunk.chunk_index,
					"text": chunk.text,
					"char_start": chunk.char_start,
					"char_end": chunk.char_end,
					"metadata": extracted.metadata or {},
				})
			
			# Initialize backend and add chunks
			backend_class = get_backend(source.knowledge_type)
			backend = backend_class()
			backend.initialize(source.name, {
				"chunk_size": source.chunk_size,
				"chunk_overlap": source.chunk_overlap,
			})
			
			# Delete existing chunks for this input (for reprocessing)
			backend.delete_chunks(doc.name)
			
			# Add new chunks
			chunks_added = backend.add_chunks(chunk_data)
			
			# Update input status
			doc.status = "Indexed"
			doc.chunks_created = chunks_added
			doc.character_count = extracted.character_count
			doc.processed_at = now_datetime()
			doc.error_message = None
			doc.save(ignore_permissions=True)
			
			# Update source stats
			update_source_stats(source, backend)
			
			# Update source status to Ready if not rebuilding
			if source.status != "Rebuilding":
				source.status = "Ready"
				source.last_indexed_at = now_datetime()
				source.save(ignore_permissions=True)
			
			frappe.db.commit()
			
			return {
				"status": "success",
				"chunks_created": chunks_added,
				"character_count": extracted.character_count,
			}
			
		finally:
			frappe.cache().delete(lock_key)
			
	except Exception as e:
		frappe.db.rollback()
		
		doc.reload()
		doc.status = "Error"
		doc.error_message = str(e)[:500]
		doc.save(ignore_permissions=True)
		
		source.reload()
		source.status = "Error"
		source.error_message = str(e)[:500]
		source.save(ignore_permissions=True)
		
		frappe.db.commit()
		
		frappe.log_error(
			f"Knowledge Input Processing Error: {doc.name}",
			frappe.get_traceback()
		)
		
		return {
			"status": "error",
			"error": str(e),
		}


def rebuild_knowledge_index(knowledge_source: str) -> dict:
	"""
	Rebuild entire index for a knowledge source.
	
	This function is designed to run in a background job.
	"""
	source = frappe.get_doc("Knowledge Source", knowledge_source)
	
	try:
		# Acquire exclusive lock
		lock_key = f"knowledge_index_{source.name}"
		if not frappe.cache().set(lock_key, 1, ex=600, nx=True):
			raise Exception(_("Another indexing operation is in progress"))
		
		try:
			source.status = "Rebuilding"
			source.save(ignore_permissions=True)
			frappe.db.commit()
			
			# Initialize backend and clear
			backend_class = get_backend(source.knowledge_type)
			backend = backend_class()
			backend.initialize(source.name, {
				"chunk_size": source.chunk_size,
				"chunk_overlap": source.chunk_overlap,
			})
			backend.clear()
			
			# Reset all input statuses
			frappe.db.sql("""
				UPDATE `tabKnowledge Input`
				SET status = 'Pending', chunks_created = 0
				WHERE knowledge_source = %s
			""", source.name)
			frappe.db.commit()
			
			# Process each input
			inputs = frappe.get_all(
				"Knowledge Input",
				filters={"knowledge_source": source.name},
				pluck="name"
			)
			
			total_chunks = 0
			for input_name in inputs:
				result = process_knowledge_input(input_name)
				if result.get("status") == "success":
					total_chunks += result.get("chunks_created", 0)
			
			# Update source status
			update_source_stats(source, backend)
			source.reload()
			source.status = "Ready"
			source.last_indexed_at = now_datetime()
			source.save(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"status": "success",
				"total_chunks": total_chunks,
				"inputs_processed": len(inputs),
			}
			
		finally:
			frappe.cache().delete(lock_key)
			
	except Exception as e:
		frappe.db.rollback()
		
		source.reload()
		source.status = "Error"
		source.error_message = str(e)[:500]
		source.save(ignore_permissions=True)
		frappe.db.commit()
		
		frappe.log_error(
			f"Knowledge Index Rebuild Error: {source.name}",
			frappe.get_traceback()
		)
		
		return {
			"status": "error",
			"error": str(e),
		}


def _extract_text(doc) -> ExtractedText:
	"""Extract text from a Knowledge Input document."""
	if doc.input_type == "Text":
		return ExtractedText(
			text=doc.text,
			title="Pasted Text",
			character_count=len(doc.text or ""),
		)
	
	elif doc.input_type == "File":
		# Get file path
		file_doc = frappe.get_doc("File", {"file_url": doc.file})
		file_path = file_doc.get_full_path()
		
		# Get appropriate extractor
		extractor = TextExtractor.get_extractor(doc.file_type)
		return extractor.extract(file_path)
	
	elif doc.input_type == "URL":
		# Get URL extractor
		from .extractors.url import URLExtractor
		extractor = URLExtractor()
		return extractor.extract(doc.url)
	
	raise ValueError(f"Unknown input type: {doc.input_type}")


def update_source_stats(source, backend):
	"""Update knowledge source statistics."""
	stats = backend.get_stats()
	
	source.reload()
	source.total_chunks = stats.get("chunk_count", 0)
	source.total_inputs = stats.get("input_count", 0)
	source.index_size_bytes = stats.get("size_bytes", 0)
	source.sqlite_file_path = backend.db_path
	
	# Update SQLite file reference
	if backend.db_path and os.path.exists(backend.db_path):
		# Create or update file reference
		from frappe.utils import get_files_path
		files_path = get_files_path(is_private=True)
		relative_path = os.path.relpath(backend.db_path, files_path)
		file_url = f"/private/files/{relative_path.replace(os.sep, '/')}"
		
		# Check if file doc exists
		existing_file = frappe.db.exists("File", {"file_url": file_url})
		if not existing_file:
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": os.path.basename(backend.db_path),
				"file_url": file_url,
				"is_private": 1,
			})
			file_doc.insert(ignore_permissions=True)
		
		source.sqlite_file = file_url
	
	source.save(ignore_permissions=True)
