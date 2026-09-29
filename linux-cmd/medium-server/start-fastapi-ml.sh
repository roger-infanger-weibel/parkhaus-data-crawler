./copy-github.sh

echo "Setup Python Env"
source .venv/bin/activate

echo "Get latest Code"
cp -rf latest-github/FastAPI-ML/* FastAPI-ML/

echo "Restart FastAPI-ML Service"
systemctl restart parkhaus-fastapi-ml
systemctl status parkhaus-fastapi-ml --no-pager
