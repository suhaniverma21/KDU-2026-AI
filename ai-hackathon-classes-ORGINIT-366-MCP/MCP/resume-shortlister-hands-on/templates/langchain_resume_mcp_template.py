"""
Enhanced Resume Shortlister MCP Tool with LangChain

This tool extends the basic resume shortlister with LangChain capabilities for
resume analysis, skill extraction, and job matching.
"""

# To mark the functions that students are expected to implement
from _devtools import student_task

import asyncio
import os
from typing import Annotated

import mcp.server.stdio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError
from mcp.types import (
    TextContent,
    Tool,
    INVALID_PARAMS,
)
from pydantic import BaseModel, Field

from utils.resume_utils import read_resume, ensure_dir_exists

from dotenv import load_dotenv
load_dotenv()

# Initialize the server
server = Server("resume_shortlister_enhanced")

RESUME_DIR = os.environ.get("RESUME_DIR", "./assets")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Hint: Use the init_langchain_components function
embeddings, llm = student_task("Intialise the LangChain components")

@student_task("Create a resume-job matching chain")
class MatchResume(BaseModel):
    pass

@student_task("Create a skill extraction chain")
class ExtractSkills(BaseModel):
    pass

@student_task("Implement the list_tools function")
@server.list_tools()
async def list_tools():
    return [
        # STUDENT TASK: Add tool definitions for match_resume and extract_skills
    ]

@student_task("Implement the call_tool function")
@server.call_tool()
async def call_tool(name, arguments):
    
    if name == "match_resume":
        try:
            args = MatchResume(**arguments)
        except ValueError as e:
            raise McpError(INVALID_PARAMS, str(e))
            
        file_path = args.file_path
        job_description = args.job_description
        
        full_path = os.path.join(RESUME_DIR, file_path) if not file_path.startswith('/') else file_path
        if not os.path.exists(full_path):
            raise McpError(INVALID_PARAMS, f"Resume file not found: {file_path}")
        
        filename = os.path.basename(file_path)
        
        # Step 1: Read raw text
        resume_text = read_resume(file_path, RESUME_DIR)
        if not resume_text:
            raise McpError(INVALID_PARAMS, f"Failed to read resume: {file_path}")
        
        # STUDENT TASK: Implement the resume-job matching functionality
        # Hint: Use the LangChain utility functions
        
        # Step 2: Chunk and wrap in Documents (no embedding here)
        # Step 3: Find relevant sections using FAISS (embeddings happen here)
        # Step 4: Ask LLM for assessment
        # Step 5: Return the formatted response
        return [TextContent(type="text", text="Not implemented yet")]
    
    elif name == "extract_skills":
        try:
            args = ExtractSkills(**arguments)
        except ValueError as e:
            raise McpError(INVALID_PARAMS, str(e))
        
        full_path = os.path.join(RESUME_DIR, file_path) if not file_path.startswith('/') else file_path
        if not os.path.exists(full_path):
            raise McpError(INVALID_PARAMS, f"Resume file not found: {file_path}")
        
        # Read the resume
        resume_text = read_resume(file_path, RESUME_DIR)
        if not resume_text:
            raise McpError(INVALID_PARAMS, f"Failed to read resume: {file_path}")
            
        # STUDENT TASK: Implement the skill extraction functionality
        # Hint: Use the LangChain utility functions
        
        # STUDENT TASK: Return the formatted response
        return [TextContent(type="text", text="Not implemented yet")]
    
    else:
        raise McpError(INVALID_PARAMS, f"Unknown tool: {name}")

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
                    server_name="resume_shortlister_enhanced",
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