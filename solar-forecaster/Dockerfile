FROM python:3.11 as builder

RUN apt-get update && apt-get install -y build-essential curl

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY setup.py *.pyx ./

RUN python setup.py build_ext --inplace


FROM python:3.11-slim

WORKDIR /app

RUN mkdir -p /app/uploads /app/logs /app/data
EXPOSE 4545

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY optimized_forecaster.py .
COPY run.py .
COPY prom.py .

COPY --from=builder /build/*.so ./

CMD ["python", "-u", "run.py", "api"]

