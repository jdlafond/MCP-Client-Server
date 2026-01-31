import hashlib
import json

def hash_tool_call(tool_name: str, args: dict) -> str:
    """Generate hash for tool call dedupe"""
    normalized = json.dumps({"tool": tool_name, "args": args}, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
