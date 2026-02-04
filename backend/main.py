from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from backend.models.agent_models import AgentRequest, AgentResponse
from backend.agent import AgentOrchestrator
from backend.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)

app = FastAPI(title="MCP-Client-Server Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agent/run", response_model=AgentResponse)
def agent_run(request: AgentRequest):
    """Main agent endpoint"""
    logger.info(f"Agent run request for project={request.project_id}, milestone={request.milestone_id}")
    logger.info(f"Request JSON: {request.model_dump_json()}")
    
    try:
        orchestrator = AgentOrchestrator()
        response = orchestrator.run(request)
        return response
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
