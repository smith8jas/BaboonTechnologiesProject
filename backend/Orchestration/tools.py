#Test tools used to test agent workflow. Can be deleted or replaced with project tools

from langchain_core.tools import tool

@tool
def calculate_value(expression: str) -> str:
    """Calculates a mathematical expression and returns the result."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"

@tool
def search_info(query: str) -> str:
    """Searches for information on a given topic and returns a mock result."""
    return f"Mock search result for: {query}. Found relevant financial data."

@tool
def analyze_result(data: str) -> str:
    """Analyzes provided data and returns a mock analysis."""
    return f"Mock analysis of: {data}. Data appears consistent with market trends."

tools = [calculate_value, search_info, analyze_result]

