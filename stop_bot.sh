#!/bin/bash
if [ -f bot.pid ]; then
    pid=$(cat bot.pid)
    kill $pid
    rm bot.pid
    echo "Bot s PID $pid zastavený"
else
    echo "Bot.pid nenájdený"
fi
