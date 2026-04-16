# Claude MCP Resume Shortlister Workshop

Welcome to the Claude MCP Resume Shortlister workshop! In this hands-on session, you'll learn how to create a Model Completion Protocol (MCP) server that works with Claude to process resumes and help with candidate shortlisting.

## Workshop Structure

This workshop is divided into two phases:

1. **Phase 1**: Building a basic MCP resume tool
2. **Phase 2**: Enhancing the tool with LangChain capabilities

## Prerequisites

- Python 3.8+
- Basic understanding of Python and APIs
- Familiarity with Claude (no MCP experience required)

## Setup Instructions

1. Create a new virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

2. Install required packages:

```bash
pip install -r requirements.txt      
```

3. Maintain your project directory structure:

```
resume-shortlister-hands-on/
├── assets/            # Store sample resume PDFs here
├── utils/
│   ├── __init__.py
│   ├── resume_utils.py
│   ├──langchain_utils.py
├── basic_resume_mcp.py
├── langchain_resume_mcp.py
```

4. Set up your environment variables:

```bash
# On Unix/Linux/Mac:
export OPENAI_API_KEY="your-openai-api-key"
export RESUME_DIR="./assets"

# On Windows:
set OPENAI_API_KEY=your-openai-api-key
set RESUME_DIR=./assets
```

## Phase 1: Building a Basic MCP Resume Tool

In this phase, we'll create a simple MCP server that can:
- List available resume files
- Read and extract text from resume PDFs

Your task is to complete the `basic_resume_mcp_template.py` file by implementing the missing parts.

**NOTE** : _All code fragements that you have to implement are annotated by `@student_task`_

### Key Concepts to Understand

- MCP Tool definition
- Pydantic models for input validation
- Tool implementation with `list_tools()` and `call_tool()`

## Phase 2: Enhancing with LangChain

In the second phase, we'll add LangChain capabilities to:
- Extract skills from resumes
- Match resumes to job descriptions

You'll need to complete the `langchain_utils_template.py` and `langchain_resume_mcp_template.py` files.

**NOTE** : _All code fragements that you have to implement are annotated by `@student_task`_

### Key Concepts to Understand

- LangChain embeddings and LLMs
- Document chunking and vectorization
- Creating LangChain pipelines for specific tasks

### How to Run

Connect to it from Claude Desktop by setting up an MCP connection.
- Open Claude Desktop
- Navigate to Settings → Configuration
- Locate the config.json file in the directory.
- Replace the current config with your new settings.

#### Sample Config File
```json
{
  "mcpServers": {
    "resume_shortlister": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/basic_resume_mcp.py"],
      "env": {
        "RESUME_DIR": "/path/to/assets"
      }
    }
  }
}
```

## Solution Files
If you get stuck, reference files are available under `/solutions`

## Bonus Steps
After completing the workshop, consider these extensions:
- Implement resume comparison features
- Create a resume scoring system
- Add visualization capabilities for resume analysis