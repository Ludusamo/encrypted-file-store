# syntax=docker/dockerfile:1

FROM python:3.9.9-slim-buster

WORKDIR /app

# Copy dependency file
COPY requirements.txt requirements.txt

# Install requirements
RUN pip3 install -r requirements.txt

# Copy all source files
COPY src src

# Environment variables
ENV FLASK_APP=src
ENV DATA_FILEPATH=/data

CMD [ "flask", "run", "--host=0.0.0.0" ]
