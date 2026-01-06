#!/bin/bash
# Generate Python files from proto definition

cd "$(dirname "$0")"

python -m grpc_tools.protoc \
    -I./app/grpc \
    --python_out=./app/grpc \
    --grpc_python_out=./app/grpc \
    ./app/grpc/photo_service.proto

echo "Proto files generated!"

