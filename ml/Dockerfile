FROM python:3.12-slim
WORKDIR /app
COPY service.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["python", "service.py"]
