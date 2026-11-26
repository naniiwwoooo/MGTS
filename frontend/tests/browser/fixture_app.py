"""Локальное приложение для браузерных тестов с тестовым ответом модели."""

import os
import socket

import uvicorn

import llm
from backend.main import create_app


def example_analysis(prompt: str) -> str:
    if "Показатели одного стажёра" in prompt:
        return "Тестовое заключение по стажёру."
    return "Тестовое заключение по программе."


if __name__ == "__main__":
    os.environ["MGTS_GOOGLE_INTERN_SHEET_ID"] = ""
    os.environ.pop("MGTS_GOOGLE_MENTOR_SHEET_ID", None)
    llm.llm_available = lambda: True
    llm._call_model = example_analysis
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        print(listener.getsockname()[1], flush=True)
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning"))
        server.run(sockets=[listener])
