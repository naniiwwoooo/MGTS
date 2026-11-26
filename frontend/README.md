# Дашборд стажёрской программы

Новый HTML/CSS-интерфейс запускается через FastAPI. См. [инструкцию запуска](../backend/README.md).
Ниже описана версия Streamlit.

Резервный интерфейс на Streamlit использует те же Excel-книги и расчёты, что и FastAPI. Синхронизация Google Forms и чат доступны в веб-версии FastAPI.

## Структура

```
frontend/
  app.py            # точка входа Streamlit
  data_loader.py    # чтение Excel через data.read_excel + метрики
  charts.py         # графики Plotly в стиле Apple
  style.py          # CSS и HTML-компоненты
  llm.py            # обёртка для обратной совместимости
  tests/            # pytest-тесты (данные, метрики, графики, запуск)
  requirements.txt
llm/
  core.py           # запросы к модели и подготовка контекста
data/
  interns.xlsx
  mentors.xlsx
  read_excel.py     # общий модуль чтения Excel
```

## Запуск

Из корня проекта:

```bash
.venv/bin/streamlit run frontend/app.py
```

Откроется браузер на `http://localhost:8501`.

Если зависимости ещё не установлены:

```bash
.venv/bin/pip install -r frontend/requirements.txt
```

## Тесты

```bash
.venv/bin/python -m pytest frontend/tests -q
```

## Навигация

В верхней строке можно открыть «Обзор программы» или профиль любого стажёра. В профиле видны оценки, статус анкет, сигналы и комментарии.

## ИИ-анализ

Для графиков и метрик ключ API не нужен. Если ключ настроен, откройте
«ИИ-анализ» и нажмите «Сформировать вывод». Конфигурация провайдера
описана в `llm/.env.example`. По умолчанию используется GigaChat.
