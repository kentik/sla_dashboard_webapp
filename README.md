# SLA Dashboard web application
Example web application visualizing SLA adherence based on Kentik synthetic mesh test data

## Run the dashboard app (development server, debug mode ON)

Shell:
```bash
export KTAPI_AUTH_EMAIL=<your kentik api email>
export KTAPI_AUTH_TOKEN=<your kentik api token>
./generate_client.sh
pip install -r requirements.txt
python main.py
```

## Run the dashboard app (production server, debug mode OFF)

Shell:
```bash
export KTAPI_AUTH_EMAIL=<your kentik api email>
export KTAPI_AUTH_TOKEN=<your kentik api token>
./generate_client.sh
pip install -r requirements.txt
gunicorn --config=data/gunicorn.conf.py
```

## Custom API server URL

It is possible to use custom API server by providing following environment variable:
```bash
export KTAPI_URL="127.0.0.1:9050"
```

## Docker build image

Shell:
```bash
docker build . -t sla_dashboard
```

## Docker run image
Shell:
```bash
docker run \
    --name sla_dashboard \
    --rm \
    --add-host host.docker.internal:host-gateway \
    -e KTAPI_AUTH_EMAIL=<kentik account email> \
    -e KTAPI_AUTH_TOKEN=<kentik account token> \
    -v "$(pwd)/data:/app/data" \
    -p 127.0.0.1:8050:8050 \
    sla_dashboard:latest
```
**Note:** running the app as docker container requires `data/` folder with `config.yaml`, `gunicorn.conf.py` and `assets/`

## Application configuration and customization

Configuration is stored in config file [config.yaml](./data/config.yaml)  
UI customization is possible by modifying CSS files in [./data/assets](./data/assets)

## API request quota utilisation

Each instance of WebApp maintains it's own data cache.  
Running multiple instances of WebApp, for example as WSGI server workers, is safe, but may increase the API request quota impact.

## Development

1. Prepare virtual environment with `virtualenv venv`
2. Activate virtual environment with `source venv/bin/activate`
3. Install requirements with `pip install -r requirements.txt && pip install -r requirements_dev.txt`
4. Generate synthetics client with `generate_client.sh`

