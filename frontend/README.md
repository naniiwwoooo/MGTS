# Дашборд стажёрской программы

Streamlit-дашборд в стиле apple.com: общая картина по опросам стажёров и
наставников за 6 месяцев и детальный разрез по каждому стажёру.

## Структура

```
frontend/
  app.py            # точка входа Streamlit
  data_loader.py    # чтение Excel через data.read_excel + метрики
  charts.py         # графики Plotly в стиле Apple
  style.py          # CSS и HTML-компоненты
  llm.py            # заготовка для будущей LLM-интеграции
  tests/            # pytest-тесты (данные, метрики, графики, запуск)
  requirements.txt
data/
  intern_survey.xlsx
  mentor_survey.xlsx
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

## Будущая LLM-интеграция

В `frontend/llm.py` уже есть `build_context`, `build_prompt` и точка
расширения `_call_model`. Чтобы включить анализ, реализуйте вызов модели и
задайте переменную окружения `LLM_API_KEY` (или `OPENAI_API_KEY`). Интерфейс
подхватит результат автоматически через `generate_overall_impression`.
