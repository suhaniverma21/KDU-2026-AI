"""
LangChain utilities for resume processing
"""

# To mark the functions that students are expected to implement
from _devtools import student_task

# LangChain imports
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS

def init_langchain_components(api_key):
    """Initialize LangChain components.
    
    Args:
        api_key: OpenAI API key
        
    Returns:
        tuple: (embeddings, llm) or (None, None) if error
    """
    embeddings = OpenAIEmbeddings(api_key=api_key)
    llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo", api_key=api_key)
    return embeddings, llm

def prepare_resume_documents(resume_text, filename):
    """
    Split resume text into chunks and wrap them as LangChain Document objects.
    
    Args:
        resume_text: Raw resume text
        filename: Name of the resume file
    
    Returns:
        dict: Contains original text and chunked Document list
    """
    # Step 1: Chunk the resume
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_text(resume_text)

    # Step 2: Wrap each chunk in a Document with metadata
    documents = [
        Document(page_content=chunk, metadata={"source": filename, "chunk_index": i})
        for i, chunk in enumerate(chunks)
    ]

    return {
        "text": resume_text,
        "chunks": documents
    }

def find_relevant_sections(processed_resume, job_description, embeddings):
    """
    Use FAISS vector store to find top 3 resume chunks most relevant to a job description.
    
    Args:
        processed_resume: Output of process_resume_with_langchain (includes chunks)
        job_description: Job description string
        embeddings: OpenAI embeddings object
    
    Returns:
        List of (chunk_text, similarity_score) tuples
    """
    # Build FAISS index from processed chunks
    vectorstore = FAISS.from_documents(processed_resume["chunks"], embeddings)

    # Perform semantic search
    results = vectorstore.similarity_search_with_score(job_description, k=3)

    # Return list of (text, score)
    return [(doc.page_content, score) for doc, score in results]

@student_task("Create a skill extraction chain")
def extract_skills_with_langchain(resume_text, llm):
    """Extract skills from resume text using LangChain.
    
    Args:
        resume_text: Resume text content
        llm: LangChain language model
        
    Returns:
        str: Extracted skills or error message
    """
    if not llm:
        return "LangChain LLM not available for skill extraction."
    
    try:
        # Hint: Use PromptTemplate to create a prompt for skill extraction
        
        # STUDENT TASK: Run the chain and return skills
        return "Not implemented yet"
        
    except Exception as e:
        return f"Error extracting skills: {str(e)}"


@student_task("Create an assessment chain")
def assess_resume_for_job(resume_text, job_description, llm):
    """Assess how well a resume matches a job description.
    
    Args:
        resume_text: Resume text content
        job_description: Job description text
        llm: LangChain language model
        
    Returns:
        str: Assessment or error message
    """
    if not llm:
        return "LangChain LLM not available for resume assessment."
    
    try:
        # Hint: Use PromptTemplate to create a prompt for resume assessment
        
        # STUDENT TASK: Run the chain and return assessment
        return "Not implemented yet"
        
    except Exception as e:
        return f"Error assessing resume: {str(e)}"