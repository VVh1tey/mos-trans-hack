FROM python:3.12-slim
WORKDIR /app
COPY app.py scaffold.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "app.py"]
