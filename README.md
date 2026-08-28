# Trading backend

Back-end for the FX portal.

## Prerequisites

Make sure you have the following installed on your machine:

- Docker Engine with the Docker Compose plugin
- Python 3.x and PostgreSQL only if you want to run the backend outside Docker

## Getting Started

1. **Clone the Repository:**

    ```bash
    git clone https://github.com/appolon1908-hue/trading-backend.git
    cd trading-backend
    ```

2. **Create the Docker environment file**
    ```bash
    cp .env.docker.example .env
    ```
    - Replace placeholder secrets before using shared or production environments.

3. **Start containers (start project)**
    ```
    docker compose -f docker-compose.local.yaml up -d --build
    ```
    - (execute in git bash for windows users)

4. **Create super user**
    ```bash
    docker compose -f docker-compose.local.yaml exec web python3 manage.py createsuperuser
    ```
    - (execute in git bash for windows users)

5. **Stop containers (stop project).**
    ```
    docker compose -f docker-compose.local.yaml down
    ```
    - (execute in git bash for windows users)

## Documentation

The swagger API documentation can be accessed at: {HOST}:{PORT}/api/docs

### Development Notes

Run commands inside python (web) container:

```
docker compose -f docker-compose.local.yaml exec web python3 manage.py createsuperuser
docker compose -f docker-compose.local.yaml exec web python3 manage.py makemigrations --check --dry-run
docker compose -f docker-compose.local.yaml exec web python3 manage.py migrate
docker compose -f docker-compose.local.yaml exec web python3 manage.py collectstatic --no-input --clear
docker compose -f docker-compose.local.yaml exec web python3 manage.py shell
```
To test stripe payments in developement, following commands can be useful:

In order to listen to stripe webhook events, setup stripe in machine and run following command:
```
stripe listen --forward-to http://127.0.0.1:8080/api/payment/stripe_webhook/
```

## Development Guidelines

- Branches: Follow the Git Flow branching strategy.
- Commits: Make meaningful and well-documented commits.
- Pull Requests: Create PRs for feature development or bug fixes.
- Don't push directly on master branch
- Checkout new branches for features from dev branch
- Keep the dev branch updated
- it's recommended to run all pre-commit hooks before push to avoid errors. Run this: `pre-commit run --all-files`

## Additional Notes

- This project uses Django, DRF, and PostgreSQL.
- Ensure that environment variables are set for sensitive information.
- Refer to the `.gitignore` file to exclude unnecessary files from version control.
