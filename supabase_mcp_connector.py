#!/usr/bin/env python3
"""
Supabase MCP HTTP Server

A FastMCP-based HTTP server that provides search and fetch capabilities
for Supabase knowledge bases via PostgREST API.
"""

import os
import logging
import subprocess
import threading
from typing import Dict, List, Optional, Any
import requests
from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "documents")
SEARCH_COLUMNS = os.getenv("SEARCH_COLUMNS", "title,content").split(",")
ID_COLUMN = os.getenv("ID_COLUMN", "id")
TITLE_COLUMN = os.getenv("TITLE_COLUMN", "title")
CONTENT_COLUMN = os.getenv("CONTENT_COLUMN", "content")
USE_LOCALTUNNEL = os.getenv("USE_LOCALTUNNEL", "false").lower() == "true"
LOCALTUNNEL_SUBDOMAIN = os.getenv("LOCALTUNNEL_SUBDOMAIN")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# Validate required configuration
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")

# Initialize FastMCP
mcp = FastMCP("Supabase Knowledge Base")

class SupabaseConnector:
    """Handles connections and queries to Supabase via PostgREST"""
    
    def __init__(self):
        self.base_url = f"{SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json"
        }
    
    def search_documents(self, query: str) -> List[str]:
        """
        Search documents using ILIKE across specified columns
        Returns list of document IDs
        """
        try:
            # Build OR conditions for ILIKE search across columns
            or_conditions = []
            for column in SEARCH_COLUMNS:
                or_conditions.append(f"{column}.ilike.%{query}%")
            
            # Construct the filter parameter
            filter_param = f"or=({','.join(or_conditions)})"
            
            # Make the request
            url = f"{self.base_url}/{SUPABASE_TABLE}"
            params = {
                "select": ID_COLUMN,
                filter_param.split('=')[0]: filter_param.split('=')[1]
            }
            
            response = requests.get(
                url, 
                headers=self.headers, 
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            results = response.json()
            return [str(doc[ID_COLUMN]) for doc in results]
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Search request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def fetch_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Fetch a specific document by ID
        Returns document data or error information
        """
        try:
            url = f"{self.base_url}/{SUPABASE_TABLE}"
            params = {
                "select": f"{ID_COLUMN},{TITLE_COLUMN},{CONTENT_COLUMN}",
                f"{ID_COLUMN}": f"eq.{doc_id}"
            }
            
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            results = response.json()
            if not results:
                return {
                    "id": doc_id,
                    "title": "",
                    "content": "",
                    "error": "Document not found"
                }
            
            doc = results[0]
            return {
                "id": str(doc[ID_COLUMN]),
                "title": doc.get(TITLE_COLUMN, ""),
                "content": doc.get(CONTENT_COLUMN, "")
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Fetch request failed: {e}")
            return {
                "id": doc_id,
                "title": "",
                "content": "",
                "error": f"Request failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return {
                "id": doc_id,
                "title": "",
                "content": "",
                "error": f"Fetch error: {str(e)}"
            }

# Initialize Supabase connector
connector = SupabaseConnector()

@mcp.tool()
def search(query: str) -> Dict[str, List[str]]:
    """
    Search for documents in the knowledge base
    
    Args:
        query: Search term to find relevant documents
        
    Returns:
        Dictionary with 'ids' key containing list of matching document IDs
    """
    logger.info(f"Searching for: {query}")
    doc_ids = connector.search_documents(query)
    logger.info(f"Found {len(doc_ids)} documents")
    return {"ids": doc_ids}

@mcp.tool()
def fetch(id: str) -> Dict[str, str]:
    """
    Fetch a specific document by its ID
    
    Args:
        id: Document ID to retrieve
        
    Returns:
        Dictionary containing document id, title, content, and optional error
    """
    logger.info(f"Fetching document: {id}")
    result = connector.fetch_document(id)
    return result

def start_localtunnel():
    """Start localtunnel in a separate thread"""
    try:
        cmd = ["npx", "localtunnel", "--port", "8000"]
        if LOCALTUNNEL_SUBDOMAIN:
            cmd.extend(["--subdomain", LOCALTUNNEL_SUBDOMAIN])
        
        logger.info(f"Starting localtunnel with command: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read and log output
        for line in iter(process.stdout.readline, ''):
            if line:
                logger.info(f"Localtunnel: {line.strip()}")
                
    except Exception as e:
        logger.error(f"Failed to start localtunnel: {e}")

if __name__ == "__main__":
    # Start localtunnel if enabled
    if USE_LOCALTUNNEL:
        tunnel_thread = threading.Thread(target=start_localtunnel, daemon=True)
        tunnel_thread.start()
    
    # Log configuration
    logger.info("Starting Supabase MCP HTTP Server")
    logger.info(f"Supabase URL: {SUPABASE_URL}")
    logger.info(f"Table: {SUPABASE_TABLE}")
    logger.info(f"Search columns: {SEARCH_COLUMNS}")
    logger.info(f"Localtunnel enabled: {USE_LOCALTUNNEL}")
    
    # Start the server
    mcp.run(host="0.0.0.0", port=8000)