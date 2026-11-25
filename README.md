# МГТС · Дашборд стажёрской программы

Дашборд показывает результаты опросов стажёров и наставников. В обзоре видна динамика программы, в профиле — оценки и отзывы по конкретному стажёру. FastAPI запускает и сервер, и веб-интерфейс.

## Запуск после скачивания с GitHub

Понадобится Python 3.11 или новее. Если скачали ZIP, распакуйте его и откройте терминал в папке, где находятся `backend`, `frontend` и `data`. Если скачиваете через Git, выполните:

```bash
git clone https://github.com/naniiwwoooo/MGTS.git
cd MGTS
```

### macOS и Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Откройте [дашборд](http://127.0.0.1:8000). Для остановки сервера нажмите `Ctrl+C` в терминале. Если порт занят, замените `8000` на `8001` и откройте адрес с новым портом.

Данные загружаются из листа «Данные» в файлах `data/intern_survey.xlsx` и `data/mentor_survey.xlsx`. Для таблиц и графиков достаточно этих файлов и установленных зависимостей.

## Как включить выводы GigaChat-2

1. Получите ключ авторизации GigaChat API в личном кабинете провайдера.
2. Скопируйте [llm/.env.example](llm/.env.example) в `llm/.env`. В новом файле задайте свой ключ в `LLM_API_KEY`, оставьте `LLM_PROVIDER=GigaChat` и `LLM_MODEL=GigaChat-2`. Значение `LLM_SCOPE` должно соответствовать типу вашего подключения.
3. Перезапустите сервер. Вывод появится автоматически при открытии обзора или профиля.

Файл `llm/.env` содержит ключ доступа и предназначен для локального использования. При включённом анализе приложение отправляет провайдеру сводные оценки, а в профиле также использует ответы стажёра и комментарии наставников.

[Описание API](http://127.0.0.1:8000/docs) · [Настройки и тесты серверной части](backend/README.md)
