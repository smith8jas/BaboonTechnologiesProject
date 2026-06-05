from backend.api.schemas import AgentChatRequest, AgentChatResponse
from backend.services import agent_service


def chat_with_agent(request: AgentChatRequest) -> AgentChatResponse:
    thread_id, response = agent_service.chat(
        request.message,
        thread_id=request.thread_id,
        recursion_limit=request.recursion_limit,
    )
    return AgentChatResponse(thread_id=thread_id, response=response)
