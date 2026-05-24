# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VectorStoreProfile(Document):
    """Vector Store Profile - Configuration for vector database connections.
    
    Supports multiple backends: pgvector, chroma, weaviate, pinecone, qdrant, redis
    """
    
    def validate(self):
        """Validate the profile configuration."""
        self._validate_port()
        self._validate_vector_dimension()
        self._validate_additional_config()
    
    def _validate_port(self):
        """Validate port number based on backend type if not specified."""
        if not self.port:
            default_ports = {
                "pgvector": 5432,
                "chroma": 8000,
                "weaviate": 8080,
                "pinecone": None,  # Pinecone uses cloud API
                "qdrant": 6333,
                "redis": 6379
            }
            if self.backend_type in default_ports and default_ports[self.backend_type]:
                self.port = default_ports[self.backend_type]
    
    def _validate_vector_dimension(self):
        """Validate vector dimension is within reasonable bounds."""
        if self.vector_dimension < 1:
            frappe.throw("Vector Dimension must be at least 1")
        if self.vector_dimension > 8192:
            frappe.throw("Vector Dimension exceeds maximum allowed (8192)")
    
    def _validate_additional_config(self):
        """Validate additional_config is valid JSON if provided."""
        if self.additional_config:
            try:
                import json
                json.loads(self.additional_config)
            except json.JSONDecodeError:
                frappe.throw("Additional Config must be valid JSON")
    
    def get_connection_config(self) -> dict:
        """Get the connection configuration as a dictionary.
        
        Returns:
            dict: Connection configuration for the vector store backend
        """
        import json
        
        config = {
            "backend_type": self.backend_type,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.get_password("password") if self.password else None,
            "vector_dimension": self.vector_dimension,
            "ssl_mode": self.ssl_mode
        }
        
        # Merge additional config if provided
        if self.additional_config:
            try:
                additional = json.loads(self.additional_config)
                config.update(additional)
            except json.JSONDecodeError:
                pass
        
        return config
