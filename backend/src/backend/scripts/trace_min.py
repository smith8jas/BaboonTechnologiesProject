from dotenv import load_dotenv
load_dotenv()

import os
from langsmith import Client
from langchain_openai import ChatOpenAI
from langchain_core.tracers.langchain import wait_for_all_tracers

print("TRACING:", os.environ.get("LANGSMITH_TRACING"))
print("Projects:", [p.name for p in Client().list_projects(limit=5)])

llm = ChatOpenAI(model="gpt-4o-mini")
print(llm.invoke("say hi").content)

wait_for_all_tracers()   # ← add this; blocks until the queue flushes