pkill -f web_server.py 
cp -rf latest-github/flask/* flask
cd flask/
nohup python3 web_server.py >web_server.log 2>&1 &
echo "Flask gestartet (PID $!), Log: web_server.log"

