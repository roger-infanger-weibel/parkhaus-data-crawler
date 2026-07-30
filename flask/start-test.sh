pkill -f scheduler-test.py 
cp -u latest-github/scanner/* scanner-test
cd scanner-test/
cp scheduler.py scheduler-test.py 
nohup python3 -u scheduler-test.py > scheduler-test.log 2>&1 &
echo "Test Crawler gestartet (PID $!), Log: scheduler-test.log"

