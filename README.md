# FX Back-End

Back-end for the FX portal.

## Prerequisites

Make sure you have the following installed on your machine:

- Python 3.x
- Virtual Environment
- PostgreSQL

## Getting Started

1. **Clone the Repository:**

    ```bash
    git clone https://github.com/appolon1908-hue/backend.git
    cd backend
    ```

2. **Copy .env.example file and create .env file**
    - Environment variables will be pickedup from .env file.

3. **Start containers (start project)**
    ```
    ./start.sh
    ```
    - (execute in git bash for windows users)

4. **Create super user**
    ```bash
    docker compose exec web python3 manage.py createsuperuser
    ```
    - (execute in git bash for windows users)

5. **Stop containers (stop project).**
    ```
    ./stop.sh
    ```
    - (execute in git bash for windows users)

## Documentation

The swagger API documentation can be accessed at: {HOST}:{PORT}/api/docs

### Development Notes

Run commands inside python (web) container

**NOTE:** If you're running the `docker-compose-dev.yaml` file Make sure to set DEBUG=1 in environment vars. Because we're using promethues exporter and it clashes with django hot reload mode, We must disable the exporter in development environment.
```
docker compose exec web python3 manage.py createsuperuser
docker compose exec web python3 manage.py makemigrations
docker compose exec web python3 manage.py migrate
docker compose exec web python3 manage.py collectstatic --no-input --clear
docker compose exec web python3 manage.py shell
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
