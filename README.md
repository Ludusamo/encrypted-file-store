# file-store

## Running Docker

### Build

`docker build -t encrypted-file-store .`

### Run with binded mount

`docker run --publish 5000:5000 -v "$(pwd)"/data:/data --name encrypted-file-store encrypted-file-store`

### Deploying to Registry Repo

`docker build . -t <registry_ip>:32000/efs:latest`
`docker push <registry_ip>:32000/efs`
