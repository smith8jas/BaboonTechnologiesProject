from backend.api.schemas import AgentChatRequest, AgentChatResponse
from backend.services import agent_service


async def chat_with_agent(request: AgentChatRequest) -> AgentChatResponse:
    thread_id, response = await agent_service.chat_async(
        request.message,
        thread_id=request.thread_id,
        recursion_limit=request.recursion_limit,
    )
    return AgentChatResponse(thread_id=thread_id, response=response)


async def stream_chat_with_agent(request: AgentChatRequest):
    return await agent_service.chat_stream_events_async(
        request.message,
        thread_id=request.thread_id,
        recursion_limit=request.recursion_limit,
    )
