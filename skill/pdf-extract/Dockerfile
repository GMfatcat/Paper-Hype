# build: docker build -t pdf-extract .   (run from this dir)
# run:   docker run --rm pdf-extract "<arXiv id | PDF URL>"
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install pymupdf
COPY extract.py /app/extract.py
WORKDIR /app
ENTRYPOINT ["python", "extract.py"]
