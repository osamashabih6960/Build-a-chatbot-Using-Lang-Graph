"""FastAPI bridge: serves the 3D UI and streams LangGraph replies (SSE)."""
import json
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel

from langgraph_database_backend import chatbot, retrieve_all_threads

app = FastAPI(title="LangGraph 3D Chatbot")
INDEX = Path(__file__).parent / "static" / "index.html"


class ChatIn(BaseModel):
    thread_id: str
    message: str


def _messages(thread_id: str):
    state = chatbot.get_state({"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])


@app.get("/")
def home():
    return FileResponse(INDEX)


@app.get("/api/threads")
def threads():
    out = []
    for tid in retrieve_all_threads():
        msgs = _messages(tid)
        if msgs:
            out.append({"id": tid, "title": str(msgs[0].content)[:40]})
    return out


@app.get("/api/threads/{thread_id}")
def history(thread_id: str):
    return [
        {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
        for m in _messages(thread_id)
    ]


@app.get("/api/new")
def new_thread():
    return {"id": str(uuid.uuid4())}


@app.post("/api/chat")
def chat(body: ChatIn):
    config = {"configurable": {"thread_id": body.thread_id}}

    def events():
        yield f"data: {json.dumps({'node': 'chat_node'})}\n\n"
        for chunk, _meta in chatbot.stream(
            {"messages": [HumanMessage(content=body.message)]},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield f"data: {json.dumps({'token': chunk.content})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
