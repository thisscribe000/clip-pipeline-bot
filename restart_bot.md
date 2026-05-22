# Restart ShareStill Bot

```bash
pkill -f "bot.py"
nohup python3 bot.py > bot.log 2>&1 &
```

Or with venv:

```bash
cd /var/www/paperlink_os/sites/sharestill
source venv/bin/activate
pkill -f "bot.py"
nohup python bot.py > bot.log 2>&1 &
```