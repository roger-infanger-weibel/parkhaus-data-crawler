pkill -f scheduler-prod.py 
cp -u latest-github/scanner/* scanner-prod
cd scanner-prod
cp scheduler.py scheduler-prod.py 
nohup python3 -u scheduler-prod.py > scheduler-prod.log 2>&1 &
