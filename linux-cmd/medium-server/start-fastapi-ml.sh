./copy-github.sh

echo "Kill current process"

pkill -f uvicorn

echo "Setup Python Env"

source .venv/bin/activate

echo "Setup Python Env"

echo "Get latest Code"

rsync -av --delete latest-github/FastAPI-ML/ FastAPI-ML/

echo "Change Directory"
cd FastAPI-ML
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 > fastapi-ml.log 2>&1 &
echo "FastAPI-ML gestartet (PID $!), Log: fastapi-ml.log"
