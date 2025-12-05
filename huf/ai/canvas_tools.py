"""
Canvas Tools
File manipulation tools for Canvas agents
"""

import os
import json
import frappe
from frappe import _
from bs4 import BeautifulSoup
import re


def get_canvas_directory(slug):
    """Get absolute path to canvas directory"""
    app_path = frappe.get_app_path("huf")
    canvas_dir = os.path.join(app_path, "www", "canvas", slug)
    
    if not os.path.exists(canvas_dir):
        frappe.throw(f"Canvas directory not found: {slug}")
    
    return canvas_dir


def validate_file_path(path):
    """Validate file path to prevent directory traversal"""
    # Only allow specific filenames
    allowed_files = ['index.html', 'index.css', 'index.js', 'index.py', 'agents.md']
    
    if path not in allowed_files:
        frappe.throw(f"Invalid file path: {path}")
    
    return path


@frappe.whitelist()
def read_canvas_file(slug, path):
    """
    Read a file from canvas directory
    
    Args:
        slug: Canvas slug
        path: File path (relative to canvas directory)
    
    Returns:
        dict: {success, content} or {success, error}
    """
    try:
        # Validate inputs
        if not slug or not path:
            frappe.throw("Slug and path are required")
        
        # Validate file path
        path = validate_file_path(path)
        
        # Get canvas directory
        canvas_dir = get_canvas_directory(slug)
        file_path = os.path.join(canvas_dir, path)
        
        # Read file
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {path}"
            }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "success": True,
            "content": content,
            "path": path
        }
    
    except Exception as e:
        frappe.log_error(f"Failed to read canvas file: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def write_canvas_files(slug, files):
    """
    Write multiple files to canvas directory
    
    Args:
        slug: Canvas slug
        files: dict with file paths as keys and content as values
               e.g., {"index.html": "<html>...", "index.css": "..."}
    
    Returns:
        dict: {success, files_written} or {success, error}
    """
    try:
        # Validate inputs
        if not slug:
            frappe.throw("Slug is required")
        
        if not files or not isinstance(files, dict):
            frappe.throw("Files must be a dictionary")
        
        # Get canvas directory
        canvas_dir = get_canvas_directory(slug)
        
        # Write files
        files_written = []
        for path, content in files.items():
            # Validate file path
            path = validate_file_path(path)
            
            file_path = os.path.join(canvas_dir, path)
            
            # Write file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            files_written.append(path)
        
        return {
            "success": True,
            "files_written": files_written,
            "count": len(files_written)
        }
    
    except Exception as e:
        frappe.log_error(f"Failed to write canvas files: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def validate_canvas(slug):
    """
    Validate canvas HTML, CSS, and JS
    
    Args:
        slug: Canvas slug
    
    Returns:
        dict: {success, warnings, errors}
    """
    try:
        # Validate inputs
        if not slug:
            frappe.throw("Slug is required")
        
        canvas_dir = get_canvas_directory(slug)
        warnings = []
        errors = []
        
        # Validate HTML
        html_path = os.path.join(canvas_dir, "index.html")
        if os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check for basic structure
                if not soup.find('html'):
                    warnings.append("Missing <html> tag")
                if not soup.find('head'):
                    warnings.append("Missing <head> tag")
                if not soup.find('body'):
                    warnings.append("Missing <body> tag")
                
                # Check for canvas-root
                if not soup.find(id='canvas-root'):
                    warnings.append("Missing #canvas-root element")
            
            except Exception as e:
                errors.append(f"HTML parsing error: {str(e)}")
        
        # Validate CSS (basic syntax check)
        css_path = os.path.join(canvas_dir, "index.css")
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            # Basic brace matching
            open_braces = css_content.count('{')
            close_braces = css_content.count('}')
            if open_braces != close_braces:
                errors.append(f"CSS brace mismatch: {open_braces} open, {close_braces} close")
        
        # Validate JS (basic syntax check)
        js_path = os.path.join(canvas_dir, "index.js")
        if os.path.exists(js_path):
            with open(js_path, 'r', encoding='utf-8') as f:
                js_content = f.read()
            
            # Basic brace/paren matching
            if js_content.count('(') != js_content.count(')'):
                errors.append("JavaScript parentheses mismatch")
            if js_content.count('{') != js_content.count('}'):
                errors.append("JavaScript brace mismatch")
            if js_content.count('[') != js_content.count(']'):
                errors.append("JavaScript bracket mismatch")
        
        return {
            "success": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "message": "Validation passed" if len(errors) == 0 else "Validation failed"
        }
    
    except Exception as e:
        frappe.log_error(f"Failed to validate canvas: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }