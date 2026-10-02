FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALPACA_IS_PAPER=true \
    STOCK_LOGICAL_BUDGET_USD=100

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY stock_bot.py /app/stock_bot.py
COPY start.sh /app/start.sh
RUN chmod 0755 /app/start.sh

CMD ["/app/start.sh"]
