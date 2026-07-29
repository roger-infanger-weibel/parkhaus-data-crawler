pkill -f web_server.py 
cp latest-github/flask/* flask
cd flask/
nohup python3 web_server.py >web_server.log 2>web_server.err &
