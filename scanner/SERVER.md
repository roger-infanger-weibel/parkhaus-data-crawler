# Server Start Test

Check .env file
```bash
sftp://root@87.106.222.137/root/scanner-test
cp scheduler.py scheduler-test.py 
nohup python3 scheduler-test.py >scheduler-test.log 2>scheduler-test.err &
```

# Server Start Prod
Check .env file
```bash
sftp://root@87.106.222.137/root/scanner-prod
cp scheduler.py scheduler-prod.py 
nohup python3 scheduler-prod.py >scheduler-prod.log 2>scheduler-prod.err &
```
