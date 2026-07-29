pkill -f scheduler-test.py 
cd scanner-test/
cp scheduler.py scheduler-test.py 
nohup python3 -u scheduler-prod.py > scheduler-test.log 2>&1 &
