pkill -f scheduler-prod.py 
cd scanner-prod/
cp scheduler.py scheduler-prod.py 
nohup python3 scheduler-prod.py >scheduler-prod.log 2>scheduler-prod.err &
