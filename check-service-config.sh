#!/bin/bash
# Systemd service konfiguratsiyasini tekshirish

echo "🔍 Systemd service konfiguratsiyasini tekshirish..."
echo ""

echo "1. Service fayl mavjudligi:"
ls -la /etc/systemd/system/cdquizbot.service 2>/dev/null && echo "✅ Service fayl topildi" || echo "❌ Service fayl topilmadi"

echo ""
echo "2. Service fayl mazmuni:"
cat /etc/systemd/system/cdquizbot.service 2>/dev/null || echo "❌ Service faylni o'qib bo'lmadi"

echo ""
echo "3. Working directory mavjudligi:"
ls -la /opt/cdquizbot/ 2>/dev/null | head -10 || echo "❌ Working directory topilmadi"

echo ""
echo "4. bot.py fayl mavjudligi:"
ls -la /opt/cdquizbot/bot.py 2>/dev/null && echo "✅ bot.py topildi" || echo "❌ bot.py topilmadi"

echo ""
echo "5. Virtual environment mavjudligi:"
ls -la /opt/cdquizbot/venv/bin/python 2>/dev/null && echo "✅ Virtual environment topildi" || echo "❌ Virtual environment topilmadi"

echo ""
echo "6. Service'ni systemd'dan qayta yuklash:"
systemctl daemon-reload
echo "✅ daemon-reload bajarildi"

echo ""
echo "✅ Tekshiruv yakunlandi!"
