"""
Enhanced Resume Shortlister MCP Tool with LangChain

This tool extends the basic resume shortlister with LangChain capabilities for
resume analysis, skill extraction, and job matching.
"""

import asyncio
import os
from typing import Annotated

# MCP imports
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

from utils.langchain_utils import (
    init_langchain_components,
    prepare_resume_documents,
    find_relevant_sections,
    extract_skills_with_langchain,
    assess_resume_for_job
)

from dotenv import load_dotenv
load_dotenv()

# Initialize the server
server = Server("resume_shortlister_enhanced")

# Directories and configuration
RESUME_DIR = os.environ.get("RESUME_DIR", "./assets")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Initialize LangChain components
embeddings, llm = init_langchain_components(OPENAI_API_KEY)

# Pydantic models for tool inputs
class MatchResume(BaseModel):
    file_path: Annotated[str, Field(description="Path to the resume PDF file")]
    job_description: Annotated[str, Field(description="Job description to match against")]

class ExtractSkills(BaseModel):
    file_path: Annotated[str, Field(description="Path to the resume PDF file")]


# MCP Tool implementation
@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="match_resume",
            description="Match a resume against a job description",
            inputSchema=MatchResume.model_json_schema(),
        ),
        Tool(
            name="extract_skills",
            description="Extract skills from a resume",
            inputSchema=ExtractSkills.model_json_schema(),
        ),
    ]

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
        
        # Step 2: Chunk and wrap in Documents (no embedding here)
        processed_resume = prepare_resume_documents(resume_text, filename)
        
        # Step 3: Find relevant sections using FAISS (embeddings happen here)
        relevant_sections = find_relevant_sections(processed_resume, job_description, embeddings)
        
        # Step 4: Ask LLM for assessment
        assessment = assess_resume_for_job(resume_text, job_description, llm)
        
        # Step 5: Format response
        response = f"Resume-Job Match Analysis for '{file_path}':\n\n"
        
        if relevant_sections:
            response += "LangChain identified these resume sections as most relevant to the job:\n\n"
            
            for i, (section, similarity) in enumerate(relevant_sections, 1):
                match_score = int(similarity * 100)
                response += f"Relevant Section {i} (Match: {match_score}%):\n{section}\n\n"
        
        response += "Full Assessment:\n\n"
        response += assessment
            
        return [TextContent(type="text", text=assessment)]
    
    elif name == "extract_skills":
        try:
            args = ExtractSkills(**arguments)
        except ValueError as e:
            raise McpError(INVALID_PARAMS, str(e))
            
        file_path = args.file_path
        
        # Check if file exists
        full_path = os.path.join(RESUME_DIR, file_path) if not file_path.startswith('/') else file_path
        if not os.path.exists(full_path):
            raise McpError(INVALID_PARAMS, f"Resume file not found: {file_path}")
        
        # Read the resume
        resume_text = read_resume(file_path, RESUME_DIR)
        if not resume_text:
            raise McpError(INVALID_PARAMS, f"Failed to read resume: {file_path}")
        
        # Extract skills using LangChain
        skills = extract_skills_with_langchain(resume_text, llm)
        
        # Format response
        response = f"Skills Extracted from '{file_path}':\n\n"
        response += skills
            
        return [TextContent(type="text", text=response)]
    
    else:
        raise McpError(INVALID_PARAMS, f"Unknown tool: {name}")

async def main():
    """Main entry point for the MCP server."""
    try:        
        # Create resume directory if it doesn't exist
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