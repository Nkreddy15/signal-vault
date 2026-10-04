FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY paper_final_view.py /app/paper_final_view.py
COPY paper_v10_view.py /app/paper_v10_view.py
COPY paper_v11_view.py /app/paper_v11_view.py
COPY templates /app/templates
COPY static /app/static

EXPOSE 8090
CMD ["gunicorn", "--bind", "0.0.0.0:8090", "--workers", "1", "--threads", "4", "app:app"]
