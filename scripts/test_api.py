from dotenv import load_dotenv
load_dotenv()

import os
from langchain_openai import ChatOpenAI

r = ChatOpenAI(
    model=os.environ["VLLM_MODEL"],
    base_url=os.environ["VLLM_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
).invoke("say hi")

print(r.content)
