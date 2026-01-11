#!/bin/bash
# Qo'lda botni ishga tushirish va test qilish

echo "🧪 Qo'lda botni ishga tushirish va test qilish..."
echo ""
echo "⚠️  Eslatma: Bu script botni 10 soniya ishlatadi va keyin to'xtatadi"
echo ""

cd /opt/cdquizbot
source venv/bin/activate

echo "📋 Hozirgi holat:"
echo "1. Service holati:"
systemctl status cdquizbot --no-pager -l | head -5

echo ""
echo "2. Hech qanday bot jarayoni yo'qmi tekshirish:"
ps aux | grep -E "cdquizbot.*bot.py|/opt/cdquizbot.*python.*bot.py" | grep -v grep || echo "✅ Hech qanday CDQuizBot jarayoni yo'q"

echo ""
echo "3. Webhook holati:"
python3 << 'PYEOF'
import asyncio
from telegram import Bot

async def check_webhook():
    bot = Bot(token='8450348603:AAFluXVOO99MevP6MfdT9UkbsSXqf3WvPIg')
    try:
        webhook_info = await bot.get_webhook_info()
        print(f"Webhook URL: {webhook_info.url or '(yo\'q)'}")
        print(f"Pending updates: {webhook_info.pending_update_count}")
    except Exception as e:
        print(f"Xatolik: {e}")
    finally:
        try:
            await bot.close()
        except:
            pass

asyncio.run(check_webhook())
PYEOF

echo ""
echo "🔄 Botni qo'lda ishga tushirish (10 soniya davomida)..."
echo "Agar conflict xatosi chiqmasa, bot ishlayapti!"
echo ""

# Botni background'da ishga tushirish
python bot.py &
BOT_PID=$!

# 10 soniya kutish
sleep 10

# Botni to'xtatish
echo ""
echo "🛑 Botni to'xtatish..."
kill $BOT_PID 2>/dev/null || true
sleep 2

# Majburiy to'xtatish
kill -9 $BOT_PID 2>/dev/null || true

echo ""
echo "✅ Test yakunlandi!"
echo ""
echo "📋 Natija:"
echo "Agar yuqorida conflict xatosi ko'rinmasa va 'Bot ishga tushmoqda...' ko'rinsa,"
echo "demak bot qo'lda ishlayapti. Muammo systemd service konfiguratsiyasida!"
