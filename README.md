#проект hr-intern-insights-gigachat.zip
1. Разархивировать в папку на компе, например "C:/hr-intern-insights-gigachat"
2. в Powershell перейти в корневую папку "cd C:/hr-intern-insights-gigachat"
3. python -m venv .venv

4. .venv\Scripts\activate
4.1) если выдает ошибку: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
далее: y (для подтверждения)

5) pip install -r requirements.txt

6) copy .env.example .env

6) python app/main.py

в браузере затем откройте http://127.0.0.1:5000
