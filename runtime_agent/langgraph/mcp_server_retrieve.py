import logging
import sys
import os
import importlib.util

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

_retrieve_module_path = os.path.join(_script_dir, "mcp_retrieve.py")
_spec = importlib.util.spec_from_file_location("mcp_retrieve", _retrieve_module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load mcp_retrieve from {_retrieve_module_path}")
_mcp_retrieve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mcp_retrieve)

from mcp.server.fastmcp import FastMCP 

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("retrieve-server")

try:
    mcp = FastMCP(
        name = "mcp-retrieve",
        instructions=(
            "You are a helpful assistant. "
            "You retrieve documents in RAG."
        ),
    )
    logger.info("MCP server initialized successfully")
except Exception as e:
        err_msg = f"Error: {str(e)}"
        logger.info(f"{err_msg}")

######################################
# RAG
######################################
@mcp.tool()
def retrieve(keyword: str) -> str:
    """
    Query the keyword using RAG based on the knowledge base.
    keyword: the keyword to query
    return: the result of query
    """
    logger.info(f"search --> keyword: {keyword}")

    return _mcp_retrieve.retrieve(keyword)

if __name__ =="__main__":
    mcp.run(transport="stdio")


