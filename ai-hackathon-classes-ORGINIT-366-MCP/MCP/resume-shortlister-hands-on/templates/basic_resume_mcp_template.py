"""
Basic Resume Shortlister MCP Tool

This tool allows Claude to view and access resume PDFs for shortlisting candidates.
"""

# To mark the functions that students are expected to implement
from _devtools import student_task

import asyncio
import os
from typing import Annotated

import mcp.server.stdio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    TextContent,
    Tool,
    INVALID_PARAMS,
)
from pydantic import BaseModel, Field

from utils.resume_utils import read_resume, ensure_dir_exists

# Initialize the server
server = Server("resume_shortlister")

RESUME_DIR = os.environ.get("RESUME_DIR", "./assets")

@student_task("Define the ReadResume model")
class ReadResume(BaseModel):
    pass

@student_task("Define the ListResumes model")
class ListResumes(BaseModel):
    pass

@student_task("Implement the list_tools function")
@server.list_tools()
async def list_tools():
    # STUDENT TASK: Return a list of Tool objects for read_resume and list_resumes
    return []

@student_task("Implement the call_tool function")
@server.call_tool()
async def call_tool(name, arguments):    
    if name == "read_resume":
        try:
            args = ReadResume(**arguments)
        except ValueError as e:
            raise Exception(INVALID_PARAMS, str(e))
            
        file_path = args.file_path
        
        # STUDENT TASK: Extract text from resume PDF
        # Hint: Use the read_resume function from resume_utils
        
        # STUDENT TASK: Return the resume content
        # Hint: Return a list with TextContent
        pass
    
    elif name == "list_resumes":
        # STUDENT TASK: Implement listing all resume files in the directory
        # Hint: Check if directory exists, then list PDF files
        pass
    
    else:
        raise Exception(INVALID_PARAMS, f"Unknown tool: {name}")

async def main():
    """Main entry point for the MCP server."""
    try:        
        ensure_dir_exists(RESUME_DIR)
        
        # Start the server
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="resume_shortlister",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        raise

if __name__ == "__main__":
    asyncio.run(main())