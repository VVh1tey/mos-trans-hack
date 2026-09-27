FROM python:3.12-slim
WORKDIR /app
COPY app.py dashboard.py ndtp.py ingest.py simulation.py replay.py openapi.json swagger.html ./
COPY demo/ ./demo/
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "app.py"]
