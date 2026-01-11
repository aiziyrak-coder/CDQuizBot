#!/bin/bash
# Uzoq kutish va qayta sinash

echo "⏳ Telegram API polling session to'liq yopilishi uchun 120 soniya kutish..."
echo "Bu juda muhim - Telegram API serverda eski polling session to'liq yopilishi uchun vaqt kerak"
echo ""

# Uzoq kutish
for i in {120..1}; do
    echo -ne "\r⏳ Qolgan vaqt: ${i} soniya..."
    sleep 1
done
echo ""
echo ""

echo "🧹 Webhook'ni qayta o'chirish..."
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
echo "🔄 Endi botni qo'lda ishga tushiring:"
echo "cd /opt/cdquizbot && source venv/bin/activate && python bot.py"
echo ""
echo "Agar hali ham conflict xatosi chiqsa, ehtimol boshqa joyda (local yoki boshqa server) bot ishlayapti!"
