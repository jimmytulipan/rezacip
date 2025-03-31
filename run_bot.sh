source venv/bin/activate
mkdir -p logs
python bot.py >> logs/bot_log.txt 2>&1 &
echo $! > bot.pid
echo "Bot spustený s PID $(cat bot.pid)"
