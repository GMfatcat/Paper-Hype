# build: docker build -t paper-verify .   (run from this dir)
# run:   docker run --rm paper-verify "<DOI|arXiv id|title>"
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
COPY verify.py /app/verify.py
WORKDIR /app
ENTRYPOINT ["python", "verify.py"]
