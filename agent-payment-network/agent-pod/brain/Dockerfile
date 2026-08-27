FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY sdk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy sdk code and proto files
COPY sdk/ /app/sdk/
COPY proto/ /app/proto/

# Generate gRPC python code (in a real scenario we'd do this here)
# RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app/sdk --grpc_python_out=/app/sdk /app/proto/kuberbolt.proto

ENV PYTHONPATH=/app

CMD ["uvicorn", "sdk.main:app", "--host", "0.0.0.0", "--port", "7000"]
