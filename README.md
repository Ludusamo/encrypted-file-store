# file-store

## Running Locally

`source FLASK_APP=src`

## Running Docker

### Build

`docker build -t encrypted-file-store .`

### Run with binded mount

`docker run --publish 5000:5000 -v "$(pwd)"/data:/data --name encrypted-file-store encrypted-file-store`
