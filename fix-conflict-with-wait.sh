#!/bin/bash
# Conflict muammosini hal qilish - uzoq kutish bilan

echo "🛑 CDQuizBot'ni to'xtatish..."
systemctl stop cdquizbot

echo "⏳ 5 soniya kutish..."
sleep 5

echo "🧹 Webhook'ni o'chirish..."
cd /opt/cdquizbot
source venv/bin/activate
python3 << 'PYEOF'
import asyncio
from telegram import Bot

async def delete_webhook():
    bot = Bot(token='8450348603:AAFluXVOO99MevP6MfdT9UkbsSXqf3WvPIg')
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print('✅ Webhook o\'chirildi')
    except Exception as e:
        print(f'⚠️  {e}')
    finally:
        try:
            await bot.close()
        except:
            pass

asyncio.run(delete_webhook())
PYEOF

echo ""
echo "⏳ 60 soniya kutish (Telegram API polling session to'liq yopilishi uchun)..."
echo "Bu Telegram API serverda eski polling session to'liq yopilishi uchun zarur"
sleep 60

echo ""
echo "🔄 CDQuizBot'ni qayta ishga tushirish..."
systemctl start cdquizbot

echo "⏳ 10 soniya kutish..."
sleep 10

echo ""
echo "📊 CDQuizBot statusi:"
systemctl status cdquizbot --no-pager -l | head -30

echo ""
echo "📝 Oxirgi 50 qator log (conflict xatosi bor-yo'qligini tekshirish):"
journalctl -u cdquizbot -n 50 --no-pager | grep -i conflict || echo "✅ Conflict xatosi yo'q!"

echo ""
echo "✅ Tugadi!"
