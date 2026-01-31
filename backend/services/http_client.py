import httpx
from typing import Optional, Dict, Any

class HTTPClient:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        response = self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def post(self, url: str, json: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        response = self.client.post(url, json=json, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def patch(self, url: str, json: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        response = self.client.patch(url, json=json, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        self.client.close()
