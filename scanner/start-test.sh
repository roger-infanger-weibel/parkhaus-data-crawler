pkill -f scheduler-test.py 
cd scanner-test/
cp scheduler.py scheduler-test.py 
nohup python3 scheduler-test.py >scheduler-test.log 2>scheduler-test.err &
