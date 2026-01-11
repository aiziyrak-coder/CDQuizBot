#!/bin/bash
# Botni to'liq to'xtatish va o'chirish

echo "🛑 CDQuizBot service'ni to'xtatish..."
systemctl stop cdquizbot

echo "⏳ 5 soniya kutish..."
sleep 5

echo "🔍 Barcha Python bot jarayonlarini tekshirish..."
ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep

echo ""
echo "🛑 Barcha CDQuizBot jarayonlarini majburiy to'xtatish..."
pkill -9 -f "cdquizbot.*bot.py"
pkill -9 -f "/opt/cdquizbot.*python"
killall -9 python3 2>/dev/null || true

echo "⏳ 3 soniya kutish..."
sleep 3

echo ""
echo "🔍 Qolgan jarayonlarni tekshirish..."
REMAINING=$(ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep)
if [ -n "$REMAINING" ]; then
    echo "⚠️  Hali ham qolgan jarayonlar:"
    echo "$REMAINING"
    echo "🔄 Qolgan jarayonlarni majburiy to'xtatish..."
    ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    sleep 2
else
    echo "✅ Barcha CDQuizBot jarayonlari to'xtatildi"
fi

echo ""
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
echo "⏳ 30 soniya kutish (Telegram API polling session to'liq yopilishi uchun)..."
sleep 30

echo ""
echo "✅ Bot to'liq to'xtatildi va o'chirildi!"
echo ""
echo "📋 Keyingi qadamlar:"
echo "1. Botni qo'lda ishga tushiring: cd /opt/cdquizbot && source venv/bin/activate && python bot.py"
echo "2. Agar bot ishlayotgan bo'lsa va xatolik bo'lmasa, demak qayerdadur boshqa instance ishlayapti"
echo "3. Agar bot ishlamasa va xatolik bo'lmasa, shunday qolaversin"
echo "4. Agar bot ishlayotgan bo'lsa lekin xatolik bo'lsa, qayerdadur boshqa instance ishlayapti"
echo ""
echo "🔍 Barcha jarayonlarni tekshirish:"
ps aux | grep -E "python.*bot|bot.py" | grep -v grep || echo "✅ Hech qanday bot jarayoni yo'q"
