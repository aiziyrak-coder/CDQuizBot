#!/bin/bash
# Conflict muammosini yakuniy hal qilish

echo "🔧 Conflict muammosini yakuniy hal qilish..."
echo ""

echo "1. Barcha bot jarayonlarini to'xtatish..."
systemctl stop cdquizbot 2>/dev/null || true
pkill -9 -f "cdquizbot.*bot.py" 2>/dev/null || true
pkill -9 -f "/opt/cdquizbot.*python" 2>/dev/null || true

echo "⏳ 5 soniya kutish..."
sleep 5

echo ""
echo "2. Barcha jarayonlarni tekshirish..."
ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep || echo "✅ Hech qanday bot jarayoni yo'q"

echo ""
echo "3. Webhook'ni o'chirish..."
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
echo "4. Telegram API polling session to'liq yopilishi uchun 120 soniya kutish..."
echo "   (Bu juda muhim - Telegram API serverda eski polling session to'liq yopilishi uchun)"
for i in {120..1}; do
    echo -ne "\r⏳ Qolgan vaqt: ${i} soniya..."
    sleep 1
done
echo ""
echo ""

echo "5. Service'ni qayta ishga tushirish..."
systemctl start cdquizbot

echo "⏳ 10 soniya kutish..."
sleep 10

echo ""
echo "6. Service holati:"
systemctl status cdquizbot --no-pager -l | head -20

echo ""
echo "7. Oxirgi loglar (conflict xatosi bor-yo'qligini tekshirish):"
journalctl -u cdquizbot -n 30 --no-pager | grep -i conflict || echo "✅ Conflict xatosi yo'q!"

echo ""
echo "✅ Tugadi!"
