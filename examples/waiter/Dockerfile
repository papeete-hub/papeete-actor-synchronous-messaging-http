# Wheels are pre-built (examples/build-wheels.sh) rather than fetched from PyPI — neither
# papeete-actor nor papeete-actor-synchronous-messaging is published there yet. Once they are,
# this collapses to `RUN pip install papeete-actor-synchronous-messaging-http` and the wheels/
# folder goes away; nothing else about this file changes.
FROM python:3.12-slim
WORKDIR /app
COPY wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels
COPY actor.yaml actor-data.yaml actor-message.yaml actor-synchronous-messaging.yaml app.py order_book.py ./
EXPOSE 8080
CMD ["python", "app.py"]
