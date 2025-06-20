FROM ghcr.io/astral-sh/uv:alpine

WORKDIR /app

COPY . /app

EXPOSE 5000

VOLUME [ "/data" ]

CMD ["uv", "run", "main.py"]