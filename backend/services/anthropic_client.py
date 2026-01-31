import os
from typing import List, Dict, Any
from anthropic import Anthropic
from backend.utils.logging import get_logger

logger = get_logger(__name__)

class AnthropicClient:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required")
        self.client = Anthropic(api_key=api_key)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    
    def create_message(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: str,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Call Claude Messages API with tool use"""
        logger.info(f"Calling Claude with {len(tools)} tools, {len(messages)} messages")
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools
        )
        
        return {
            "id": response.id,
            "role": response.role,
            "content": response.content,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        }
