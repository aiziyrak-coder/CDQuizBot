#!/bin/bash
# Conflict muammosini batafsil tekshirish

echo "🔍 Conflict muammosini batafsil tekshirish..."
echo ""

echo "1. Barcha Python bot jarayonlari:"
ps aux | grep -E "python.*bot|bot.py" | grep -v grep
echo ""

echo "2. CDQuizBot jarayonlari:"
ps aux | grep "cdquizbot" | grep -v grep
echo ""

echo "3. CDQuizBot token:"
grep "BOT_TOKEN" /opt/cdquizbot/bot.py | head -1
echo ""

echo "4. Boshqa bot (smartFrontFull) token:"
if [ -f "/var/opt/smartFrontFull/bot.py" ]; then
    grep -i "token.*=" /var/opt/smartFrontFull/bot.py | head -3
else
    echo "Fayl topilmadi: /var/opt/smartFrontFull/bot.py"
fi
echo ""

echo "5. Telegram API'da webhook holati:"
cd /opt/cdquizbot
source venv/bin/activate
python3 << 'PYEOF'
import asyncio
from telegram import Bot

async def check_status():
    bot = Bot(token='8450348603:AAFluXVOO99MevP6MfdT9UkbsSXqf3WvPIg')
    try:
        # Get webhook info
        webhook_info = await bot.get_webhook_info()
        print(f"Webhook URL: {webhook_info.url or '(yo\'q)'}")
        print(f"Pending updates: {webhook_info.pending_update_count}")
        print(f"Last error date: {webhook_info.last_error_date or '(yo\'q)'}")
        print(f"Max connections: {webhook_info.max_connections or '(yo\'q)'}")
        
        # Try to get updates (this will fail if another instance is polling)
        try:
            updates = await bot.get_updates(offset=-1, limit=1, timeout=1)
            print("✅ get_updates() muvaffaqiyatli - polling mumkin")
        except Exception as e:
            print(f"❌ get_updates() xatosi: {e}")
            if "Conflict" in str(e):
                print("⚠️  Conflict! Boshqa instance polling qilmoqda")
    except Exception as e:
        print(f"Xatolik: {e}")
    finally:
        try:
            await bot.close()
        except:
            pass

asyncio.run(check_status())
PYEOF

echo ""
echo "✅ Tekshiruv yakunlandi"
