FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY templates ./templates
COPY docs ./docs
COPY run.py .
ENV EARTHTWIN_DATA_DIR=/data HOST=0.0.0.0 PORT=8000
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "run.py"]
