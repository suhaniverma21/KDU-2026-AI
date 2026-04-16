"""
Common resume utilities for the MCP tools
"""

import logging
import os
import fitz

logger = logging.getLogger(__name__)

def read_resume(file_path, base_dir="./assets"):
    """Extract text from a resume PDF file.
    
    Args:
        file_path: Path to the resume PDF file
        base_dir: Base directory for relative paths
        
    Returns:
        str: The extracted text, or None if there was an error
    """
    try:
        # If path doesn't start with '/', assume it's relative to base_dir
        if not file_path.startswith('/'):
            file_path = os.path.join(base_dir, file_path)
            
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"Error reading resume {file_path}: {e}")
        return None

def ensure_dir_exists(directory):
    """Ensure a directory exists, creating it if necessary.
    
    Args:
        directory: Path to the directory
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")