Запуск в powershell(до этого устанвоить сам питон):
1) python -m venv .venv

2) .venv\Scripts\activate
2.1) если выдает ошибку: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
далее: y (для подтверждения)

3) pip install -r requirements.txt

4) copy .env.example .env

5) python app/main.py

в браузере затем откройте http://127.0.0.1:5000
