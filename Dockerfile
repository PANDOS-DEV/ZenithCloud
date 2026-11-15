FROM python:3.11-slim

WORKDIR /app

# Сервер использует только стандартную библиотеку Python (http.server, socketserver, json, hashlib)
COPY zenith_cloud_server.py .
COPY zenith_cloud_storage/ ./zenith_cloud_storage/

ENV PORT=7890
EXPOSE 7890

CMD ["python", "zenith_cloud_server.py"]
