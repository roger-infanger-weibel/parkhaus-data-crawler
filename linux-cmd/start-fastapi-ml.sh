pkill -f uvicorn
cp -rf latest-github/FastAPI-ML/* FastAPI-ML 
cd FastAPI-ML
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1 > fastapi-ml.log 2>&1 &
echo "FastAPI-ML gestartet (PID $!), Log: fastapi-ml.log"
