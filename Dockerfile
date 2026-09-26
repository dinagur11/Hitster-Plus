FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY general.json ./general.json
COPY rock.json ./rock.json
COPY pop.json ./pop.json

CMD ["python", "-m", "server.main"]