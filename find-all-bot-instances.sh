#!/bin/bash
# Barcha bot instance'larini topish

echo "🔍 Barcha bot instance'larini qidirish..."
echo ""

echo "1. Barcha Python jarayonlari (ps aux):"
ps aux | grep -E "python.*bot|bot.py|cdquizbot" | grep -v grep
echo ""

echo "2. Screen sessionlar:"
screen -ls 2>/dev/null || echo "Screen topilmadi yoki hech qanday session yo'q"
echo ""

echo "3. Tmux sessionlar:"
tmux ls 2>/dev/null || echo "Tmux topilmadi yoki hech qanday session yo'q"
echo ""

echo "4. Nohup jarayonlar (bot bilan bog'liq):"
ps aux | grep -E "nohup.*bot|nohup.*cdquizbot" | grep -v grep || echo "Nohup jarayonlar topilmadi"
echo ""

echo "5. Systemd service holati:"
systemctl status cdquizbot --no-pager -l 2>/dev/null | head -15 || echo "Service topilmadi"
echo ""

echo "6. CDQuizBot portlarini tekshirish (ehtimol web server ishlayapti):"
netstat -tulpn 2>/dev/null | grep -E "python|bot" | grep -v grep || echo "Portlar topilmadi"
echo ""

echo "7. Barcha python jarayonlarini PID bilan:"
ps aux | grep python | grep -v grep | awk '{print "PID: " $2 " | Command: " $11 " " $12 " " $13 " " $14 " " $15}'
echo ""

echo "8. CDQuizBot kod papkasida ishlayotgan jarayonlar:"
lsof /opt/cdquizbot/bot.py 2>/dev/null | grep -v COMMAND || echo "Hech qanday jarayon fayl ochmagan"
echo ""

echo "9. Telegram bot token bilan bog'liq jarayonlar (token qidirish):"
ps aux | grep -i "8450348603" | grep -v grep || echo "Token topilmadi"
echo ""

echo "10. Root user barcha jarayonlari:"
ps aux | grep "^root" | grep -E "python|bot" | grep -v grep | head -20
echo ""

echo "✅ Tekshiruv yakunlandi!"
echo ""
echo "📋 Agar bot ishlayotgan bo'lsa, yuqoridagi ro'yxatdan PID toping va quyidagi buyruqni bajaring:"
echo "kill -9 <PID>"
