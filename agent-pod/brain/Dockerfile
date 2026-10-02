FROM python:3.12-slim

WORKDIR /app
<<<<<<< HEAD
RUN pip install --no-cache-dir fastapi uvicorn
COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
=======

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app/main.py"]
>>>>>>> db30eb5 (docker files fixed)
