#!/bin/bash
# Boshqa joylarda bot ishlayotganini tekshirish

echo "🔍 Boshqa joylarda bot ishlayotganini tekshirish..."
echo ""
echo "⚠️  Eslatma: Agar sizning local kompyuteringizda yoki boshqa serverda"
echo "    bot ishlayotgan bo'lsa, conflict xatosi chiqadi!"
echo ""

echo "1. Serverdagi barcha bot jarayonlari:"
ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep || echo "✅ Serverda hech qanday bot jarayoni yo'q"
echo ""

echo "2. Telegram API'da polling session holati:"
cd /opt/cdquizbot
source venv/bin/activate
python3 << 'PYEOF'
import asyncio
from telegram import Bot

async def check_polling():
    bot = Bot(token='8450348603:AAFluXVOO99MevP6MfdT9UkbsSXqf3WvPIg')
    try:
        # Try to get updates - bu conflict bo'lsa xato chiqadi
        try:
            updates = await bot.get_updates(offset=-1, limit=1, timeout=2)
            print("✅ get_updates() muvaffaqiyatli - polling mumkin")
            print("   Demak, hech qanday active polling session yo'q")
        except Exception as e:
            error_msg = str(e)
            if "Conflict" in error_msg:
                print("❌ Conflict xatosi!")
                print("   Demak, qayerdadur (local yoki boshqa server) bot ishlayapti")
                print("   Yoki Telegram API serverda eski polling session active")
            else:
                print(f"⚠️  Boshqa xatolik: {e}")
    except Exception as e:
        print(f"Xatolik: {e}")
    finally:
        try:
            await bot.close()
        except:
            pass

asyncio.run(check_polling())
PYEOF

echo ""
echo "✅ Tekshiruv yakunlandi!"
echo ""
echo "📋 Keyingi qadamlar:"
echo "1. Agar conflict xatosi chiqsa, local kompyuteringizda botni to'xtating"
echo "2. Yoki boshqa serverda bot ishlayotgan bo'lsa, uni to'xtating"
echo "3. Yoki uzoq kutish (bir necha daqiqa) - Telegram API serverda eski session to'liq yopilishi uchun"
