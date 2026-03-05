FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/
EXPOSE 8080
CMD ["python", "backend/app.py"]
