# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MemoryRecordTag(Document):
    """
    Child table for tagging Memory Records.
    
    Tags provide flexible categorization of memories beyond the
    rigid memory_type field, allowing for multi-dimensional
    classification and filtering.
    """
    
    # Valid tag categories
    VALID_CATEGORIES = ["topic", "type", "priority", "status", "custom"]
    
    def validate(self):
        """Validate and normalize tag values."""
        self._normalize_tag()
        self._validate_category()
        self._validate_tag_not_empty()
    
    def _normalize_tag(self):
        """Normalize tag value (lowercase, strip whitespace)."""
        if self.tag:
            self.tag = self.tag.strip().lower()
    
    def _validate_category(self):
        """Validate tag category is one of the allowed values."""
        if self.category and self.category not in self.VALID_CATEGORIES:
            frappe.throw(
                f"Invalid tag category '{self.category}'. "
                f"Must be one of: {', '.join(self.VALID_CATEGORIES)}"
            )
    
    def _validate_tag_not_empty(self):
        """Ensure tag value is not empty after normalization."""
        if not self.tag:
            frappe.throw("Tag cannot be empty")
    
    def before_insert(self):
        """Handle pre-insert operations."""
        # Ensure parent document is set
        if not self.parent or not self.parenttype:
            frappe.throw("Memory Record Tag must be associated with a parent document")
    
    def get_tag_key(self) -> str:
        """
        Generate a unique key for this tag (category:value).
        
        Returns:
            String key in format "category:tag" or just "tag" if no category
        """
        if self.category:
            return f"{self.category}:{self.tag}"
        return self.tag
    
    @staticmethod
    def validate_tags(tags: list) -> tuple[bool, list]:
        """
        Validate a list of tag dictionaries.
        
        Args:
            tags: List of dicts with 'tag' and optionally 'category' keys
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        seen = set()
        
        for idx, tag_data in enumerate(tags):
            tag = tag_data.get("tag", "").strip().lower()
            category = tag_data.get("category", "")
            
            # Check for empty tags
            if not tag:
                errors.append(f"Tag at index {idx} is empty")
                continue
            
            # Check for duplicates
            key = f"{category}:{tag}" if category else tag
            if key in seen:
                errors.append(f"Duplicate tag '{tag}' at index {idx}")
            seen.add(key)
            
            # Validate category
            if category and category not in MemoryRecordTag.VALID_CATEGORIES:
                errors.append(
                    f"Invalid category '{category}' for tag '{tag}' at index {idx}"
                )
        
        return len(errors) == 0, errors
    
    @staticmethod
    def normalize_tags(tags: list) -> list:
        """
        Normalize a list of tag dictionaries.
        
        Args:
            tags: List of dicts with 'tag' and optionally 'category' keys
            
        Returns:
            List of normalized tag dictionaries
        """
        normalized = []
        seen = set()
        
        for tag_data in tags:
            tag = tag_data.get("tag", "").strip().lower()
            category = tag_data.get("category", "").strip().lower()
            
            if not tag:
                continue
            
            # Skip duplicates
            key = f"{category}:{tag}" if category else tag
            if key in seen:
                continue
            seen.add(key)
            
            # Validate category
            if category and category not in MemoryRecordTag.VALID_CATEGORIES:
                category = "custom"
            
            normalized.append({
                "tag": tag,
                "category": category or "custom"
            })
        
        return normalized
    
    @staticmethod
    def get_tags_by_category(tags: list, category: str) -> list:
        """
        Filter tags by category.
        
        Args:
            tags: List of MemoryRecordTag documents or dicts
            category: Category to filter by
            
        Returns:
            List of tags matching the category
        """
        result = []
        for tag in tags:
            if hasattr(tag, 'category'):
                if tag.category == category:
                    result.append(tag.tag if hasattr(tag, 'tag') else tag.get('tag'))
            elif isinstance(tag, dict) and tag.get('category') == category:
                result.append(tag.get('tag'))
        return result
    
    @staticmethod
    def tags_to_dict(tags: list) -> dict:
        """
        Convert list of tags to a dictionary grouped by category.
        
        Args:
            tags: List of MemoryRecordTag documents or dicts
            
        Returns:
            Dict with categories as keys and lists of tags as values
        """
        result = {cat: [] for cat in MemoryRecordTag.VALID_CATEGORIES}
        
        for tag in tags:
            if hasattr(tag, 'category') and hasattr(tag, 'tag'):
                cat = tag.category or "custom"
                result.setdefault(cat, []).append(tag.tag)
            elif isinstance(tag, dict):
                cat = tag.get('category', 'custom')
                result.setdefault(cat, []).append(tag.get('tag'))
        
        # Remove empty categories
        return {k: v for k, v in result.items() if v}
    
    @staticmethod
    def tags_to_string(tags: list, separator: str = ", ") -> str:
        """
        Convert tags to a readable string.
        
        Args:
            tags: List of MemoryRecordTag documents or dicts
            separator: Separator between tags
            
        Returns:
            String representation of tags
        """
        parts = []
        for tag in tags:
            if hasattr(tag, 'tag'):
                if hasattr(tag, 'category') and tag.category:
                    parts.append(f"{tag.tag} ({tag.category})")
                else:
                    parts.append(tag.tag)
            elif isinstance(tag, dict):
                tag_val = tag.get('tag', '')
                cat_val = tag.get('category', '')
                if cat_val:
                    parts.append(f"{tag_val} ({cat_val})")
                else:
                    parts.append(tag_val)
        
        return separator.join(parts)
